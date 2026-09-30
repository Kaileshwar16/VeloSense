"""Real local Iceberg manifests/Parquet with a temporary SQLite SQL catalog."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

pytest.importorskip("pyiceberg", reason="install requirements-iceberg.lock")

from archive.cli import query_rows  # noqa: E402
from archive.config import ArchiveConfig  # noqa: E402
from archive.consumer import commit_batch, starting_offset  # noqa: E402
from archive.table import Record, append_records, checkpoint, open_table  # noqa: E402


@pytest.fixture
def config(tmp_path):
    return ArchiveConfig(f"sqlite:///{tmp_path}/catalog.db", (tmp_path / "warehouse").as_uri())


@pytest.fixture
def record(event, config):
    return Record(config.topic, 0, 0, json.dumps(event).encode(), 1790467200000)


def test_full_schema_raw_bytes_invalid_late_and_partitions(config, record):
    table = open_table(config, create=True)
    malformed = replace(record, partition=1, payload=b"not json")
    late = replace(record, offset=1, timestamp_ms=record.timestamp_ms + 86400000)
    result = append_records(table, [record, malformed, late])
    assert result["written"] == 3 and result["invalid"] == 1
    rows = table.scan().to_arrow().to_pylist()
    assert {row["raw_payload"] for row in rows} == {record.payload, b"not json"}
    valid = [row for row in rows if row["valid"]]
    source = json.loads(record.payload)
    assert len(valid) == 2  # logical duplicates at different offsets remain raw records
    for row in valid:
        for name, value in source.items():
            if name == "timestamp":
                assert row[name].isoformat() == value.replace("Z", "+00:00")
            else:
                assert row[name] == value
    assert len({task.file.partition[0] for task in table.scan().plan_files()}) == 2
    invalid = next(row for row in rows if not row["valid"])
    assert invalid["validation_error"] == "json_invalid"
    assert invalid["event_id"] is None
    assert checkpoint(table, 0) == 2 and checkpoint(table, 1) == 1


def test_restart_replay_and_snapshot_time_travel(config, record):
    table = open_table(config, create=True)
    append_records(table, [record])
    first_snapshot = table.current_snapshot().snapshot_id
    reloaded = open_table(config)
    assert append_records(reloaded, [record])["written"] == 0
    assert reloaded.current_snapshot().snapshot_id == first_snapshot
    append_records(reloaded, [record, replace(record, offset=1)])
    assert len(reloaded.scan().to_arrow()) == 2
    assert len(reloaded.scan(snapshot_id=first_snapshot).to_arrow()) == 1
    rows = query_rows(
        reloaded,
        vehicle_id=json.loads(record.payload)["vehicle_id"],
        start="2026-09-27T00:00:00Z",
        end="2026-09-28T00:00:00Z",
        snapshot_id=first_snapshot,
    )
    assert len(rows) == 1 and "raw_payload" not in rows[0]


def test_failed_catalog_commit_never_acknowledges_kafka(config, record, monkeypatch):
    table = open_table(config, create=True)
    consumer = Mock()

    def fail(*args, **kwargs):
        raise RuntimeError("injected catalog failure")

    with monkeypatch.context() as patch:
        patch.setattr(table.catalog, "commit_table", fail)
        with pytest.raises(RuntimeError, match="injected"):
            commit_batch(consumer, table, [record])
    consumer.commit.assert_not_called()
    restarted = open_table(config)
    assert restarted.current_snapshot() is None and checkpoint(restarted, 0) is None
    assert append_records(restarted, [record])["written"] == 1


def test_failed_kafka_ack_replays_without_duplicate_data(config, record):
    table = open_table(config, create=True)
    consumer = Mock()
    consumer.commit.side_effect = RuntimeError("Kafka ack failed")
    with pytest.raises(RuntimeError, match="Kafka ack"):
        commit_batch(consumer, table, [record])
    restarted = open_table(config)
    consumer.commit.side_effect = None
    assert commit_batch(consumer, restarted, [record])["replayed"] == 1
    assert len(restarted.scan().to_arrow()) == 1
    assert consumer.commit.call_args.kwargs["offsets"][0].offset == 1


def test_lost_catalog_response_recovers_committed_checkpoint(config, record, monkeypatch):
    table = open_table(config, create=True)
    commit = table.catalog.commit_table

    def commit_then_disconnect(*args, **kwargs):
        commit(*args, **kwargs)
        raise ConnectionError("response lost after commit")

    consumer = Mock()
    with monkeypatch.context() as patch:
        patch.setattr(table.catalog, "commit_table", commit_then_disconnect)
        with pytest.raises(ConnectionError, match="response lost"):
            commit_batch(consumer, table, [record])
    consumer.commit.assert_not_called()
    restarted = open_table(config)
    assert checkpoint(restarted, 0) == 1
    assert commit_batch(consumer, restarted, [record])["written"] == 0
    assert len(restarted.scan().to_arrow()) == 1


def test_batch_byte_cap_withholds_commit(config, record, monkeypatch):
    table = open_table(config, create=True)
    monkeypatch.setattr("archive.table.MAX_BATCH_BYTES", 1)
    consumer = Mock()
    with pytest.raises(ValueError, match="32 MiB"):
        commit_batch(consumer, table, [record])
    consumer.commit.assert_not_called()
    assert open_table(config).current_snapshot() is None


def test_empty_batch_does_not_create_snapshot(config):
    table = open_table(config, create=True)
    assert append_records(table, [])["written"] == 0
    assert table.current_snapshot() is None


def test_tombstone_and_out_of_range_sequence_are_preserved(config, record):
    table = open_table(config, create=True)
    huge = json.dumps({**json.loads(record.payload), "seq": 2**63}).encode()
    result = append_records(
        table, [replace(record, payload=None), replace(record, offset=1, payload=huge)]
    )
    assert result["invalid"] == 2
    assert checkpoint(table, 0) == 2
    assert {row["raw_payload"] for row in table.scan().to_arrow().to_pylist()} == {None, huge}


def test_wrong_topic_and_unordered_batch_leave_table_uncommitted(config, record):
    table = open_table(config, create=True)
    with pytest.raises(ValueError, match="topic"):
        append_records(table, [replace(record, topic="other")])
    with pytest.raises(ValueError, match="ordered"):
        append_records(table, [replace(record, offset=1), record])
    assert open_table(config).current_snapshot() is None
    with pytest.raises(ValueError, match="topic"):
        open_table(replace(config, topic="other"))


@pytest.mark.parametrize(
    "saved,low,high,expected", [(None, 10, 20, 10), (15, 10, 20, 15), (20, 10, 20, 20)]
)
def test_recovery_position(saved, low, high, expected):
    assert starting_offset(saved, low, high) == expected


@pytest.mark.parametrize("saved", [9, 21])
def test_retention_loss_or_topic_recreation_fails_closed(saved):
    with pytest.raises(RuntimeError, match="retention"):
        starting_offset(saved, 10, 20)
