"""Opt-in real Kafka -> PostgreSQL catalog -> Iceberg -> restart/read verification."""

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from uuid import uuid4

import pytest

pytest.importorskip("pyiceberg", reason="install requirements-iceberg.lock")

from confluent_kafka import Producer  # noqa: E402
from confluent_kafka.admin import AdminClient, NewTopic  # noqa: E402
from pyiceberg.exceptions import NoSuchTableError  # noqa: E402

from archive.config import ArchiveConfig  # noqa: E402
from archive.consumer import owner  # noqa: E402
from archive.table import catalog_for, checkpoint, open_table  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_ICEBERG_INTEGRATION") != "1",
        reason="requires Kafka and PostgreSQL; RUN_ICEBERG_INTEGRATION=1",
    ),
]


def test_kafka_catalog_archive_restart_and_exclusive_owner(event, tmp_path):
    suffix = uuid4().hex[:12]
    config = replace(
        ArchiveConfig.from_env(),
        topic=f"valeosense.iceberg_test.{suffix}",
        table=f"valeosense.archive_test_{suffix}",
        warehouse=(tmp_path / "warehouse").as_uri(),
    )
    admin = AdminClient({"bootstrap.servers": config.kafka})
    admin.create_topics([NewTopic(config.topic, num_partitions=2, replication_factor=1)])[
        config.topic
    ].result(timeout=20)
    environment = {
        **os.environ,
        "ICEBERG_CATALOG_URI": config.catalog_uri,
        "ICEBERG_WAREHOUSE": config.warehouse,
        "ICEBERG_TABLE": config.table,
        "ICEBERG_TOPIC": config.topic,
        "ICEBERG_BATCH_ROWS": "10",
        "ICEBERG_FLUSH_SECONDS": "1",
        "ICEBERG_HEALTH_PATH": str(tmp_path / "health.json"),
    }
    process = None
    log = (tmp_path / "worker.log").open("w+")

    def start():
        return subprocess.Popen(
            [sys.executable, "-m", "archive.cli", "consume"],
            env=environment,
            stdout=log,
            stderr=log,
        )

    def stop():
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise

    def await_rows(count):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                pytest.fail(f"archive worker exited: {log.read()}")
            try:
                table = open_table(config)
                if len(table.scan().to_arrow()) == count:
                    return table
            except NoSuchTableError:
                pass
            time.sleep(0.2)
        pytest.fail(f"archive did not reach {count} rows")

    try:
        producer = Producer({"bootstrap.servers": config.kafka})
        errors = []

        def delivered(error, message):
            if error:
                errors.append(error)

        payload = json.dumps(event).encode()
        producer.produce(config.topic, value=payload, partition=0, on_delivery=delivered)
        producer.produce(config.topic, value=b"{invalid", partition=1, on_delivery=delivered)
        assert producer.flush(15) == 0 and not errors
        process = start()
        table = await_rows(2)
        snapshot = table.current_snapshot().snapshot_id
        assert checkpoint(table, 0) == 1 and checkpoint(table, 1) == 1
        with pytest.raises(RuntimeError, match="another consumer"):
            with owner(config):
                pytest.fail("a second writer acquired the archive")
        stop()
        assert process.returncode == 0
        # Late duplicate is a new raw Kafka record, even though event_id is unchanged.
        producer.produce(config.topic, value=payload, partition=0, on_delivery=delivered)
        assert producer.flush(15) == 0 and not errors
        process = start()
        table = await_rows(3)
        rows = table.scan().to_arrow().to_pylist()
        assert len({(r["source_partition"], r["source_offset"]) for r in rows}) == 3
        assert sum(r["valid"] for r in rows) == 2
        assert {r["raw_payload"] for r in rows} == {payload, b"{invalid"}
        assert len(table.scan(snapshot_id=snapshot).to_arrow()) == 2
        assert checkpoint(table, 0) == 2 and checkpoint(table, 1) == 1
        stop()
        assert process.returncode == 0
    finally:
        stop()
        log.close()
        catalog = catalog_for(config)
        if catalog.table_exists(config.table):
            catalog.purge_table(config.table)
        admin.delete_topics([config.topic])[config.topic].result(timeout=20)
