"""Single archive owner; Iceberg is authoritative for recovery offsets."""

import json
import logging
import signal
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from confluent_kafka import Consumer, TopicPartition

from archive.config import ArchiveConfig
from archive.table import MAX_BATCH_BYTES, Record, append_records, checkpoint, open_table


@contextmanager
def owner(config):
    if not config.catalog_uri.startswith("postgresql+psycopg://"):
        raise ValueError("the archive consumer requires a PostgreSQL catalog")
    uri = config.catalog_uri.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(uri, autocommit=True, connect_timeout=10) as connection:
        acquired = connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (f"valeosense-archive:{config.table}",),
        ).fetchone()[0]
        if not acquired:
            raise RuntimeError("another consumer owns this Iceberg archive")
        yield connection


def starting_offset(saved: int | None, low: int, high: int) -> int:
    if saved is None:
        return low
    if not low <= saved <= high:
        raise RuntimeError("archive checkpoint outside Kafka retention; recovery required")
    return saved


def commit_batch(consumer, table, records):
    result = append_records(table, records)
    # Explicit offsets avoid librdkafka's in-memory auto-store state.
    offsets = {}
    for record in records:
        offsets[record.partition] = record.offset + 1
    consumer.commit(
        offsets=[TopicPartition(records[0].topic, p, n) for p, n in offsets.items()],
        asynchronous=False,
    )
    return result


def consume(config: ArchiveConfig, health_path: Path):
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    with owner(config) as connection:
        table = open_table(config, create=True)
        consumer = Consumer(
            {
                "bootstrap.servers": config.kafka,
                "group.id": f"valeosense-iceberg-{config.table}",
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "error",
                "allow.auto.create.topics": False,
                "max.poll.interval.ms": 300000,
                "queued.max.messages.kbytes": 32768,
            }
        )
        pending = []
        pending_bytes = 0

        def clear_pending(*_):
            nonlocal pending_bytes
            pending.clear()
            pending_bytes = 0

        def assign(client, partitions):
            clear_pending()
            table.refresh()
            for partition in partitions:
                low, high = client.get_watermark_offsets(partition, timeout=10)
                partition.offset = starting_offset(
                    checkpoint(table, partition.partition), low, high
                )
            client.assign(partitions)

        consumer.subscribe([config.topic], on_assign=assign, on_revoke=clear_pending)
        last_flush = time.monotonic()
        try:
            while not stopped.is_set():
                message = consumer.poll(timeout=1)
                if message is not None:
                    if message.error():
                        raise RuntimeError("archive Kafka consumer error")
                    record = Record.from_message(message)
                    if pending and pending_bytes + len(record.payload or b"") > MAX_BATCH_BYTES:
                        connection.execute("SELECT 1")
                        logging.info(json.dumps(commit_batch(consumer, table, pending)))
                        clear_pending()
                    pending.append(record)
                    pending_bytes += len(record.payload or b"")
                if len(pending) >= config.batch_rows or (
                    time.monotonic() - last_flush >= config.flush_seconds
                ):
                    connection.execute("SELECT 1")
                    if pending:
                        logging.info(json.dumps(commit_batch(consumer, table, pending)))
                        clear_pending()
                    last_flush = time.monotonic()
                    if consumer.assignment():
                        health_path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = health_path.with_suffix(".tmp")
                        temporary.write_text(json.dumps({"heartbeat": time.time()}))
                        temporary.replace(health_path)
            if pending:
                connection.execute("SELECT 1")
                logging.info(json.dumps(commit_batch(consumer, table, pending)))
        finally:
            # No retry against a stale table after an ambiguous catalog/Kafka commit.
            health_path.unlink(missing_ok=True)
            consumer.close()
