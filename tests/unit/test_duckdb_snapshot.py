import io
import json
from pathlib import Path

import pytest

from scripts import duckdb_snapshot as snapshot


def config(tmp_path, **kwargs):
    return snapshot.SnapshotConfig(directory=tmp_path, clickhouse_url="http://clickhouse", **kwargs)


def test_export_is_bounded_deduplicated_and_contains_metadata(tmp_path):
    sql = snapshot.export_sql(config(tmp_path), 1000.5)
    assert "FROM valeosense.telemetry_read" in sql
    assert "V000100" in sql and "LIMIT 20000" in sql and "INTERVAL 120 MINUTE" in sql
    assert "UNION ALL SELECT '', '', '', ''," in sql
    assert "1000.5" in sql and sql.endswith("FORMAT Parquet")


@pytest.mark.parametrize(
    "field,value",
    [
        ("row_limit", 0),
        ("vehicle_limit", 1001),
        ("window_minutes", 1441),
        ("interval_seconds", 120),
    ],
)
def test_invalid_snapshot_bounds_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        config(tmp_path, **{field: value})


def test_atomic_publish_and_failed_validation_preserve_previous_snapshot(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    monkeypatch.setattr(snapshot.time, "time", lambda: 100)
    checked = []
    monkeypatch.setattr(snapshot, "duckdb_execute", lambda db, sql: checked.append(sql))
    snapshot.publish(cfg, opener=lambda *a, **kw: io.BytesIO(b"real-export-placeholder"))
    previous = (tmp_path / "recent.parquet").read_bytes()
    status = (tmp_path / "status.json").read_text()
    assert checked and snapshot.healthy(cfg)
    assert json.loads(status)["snapshot_epoch"] == 100

    def fail(*_):
        raise RuntimeError("invalid parquet")

    monkeypatch.setattr(snapshot, "duckdb_execute", fail)
    monkeypatch.setattr(snapshot.time, "time", lambda: 200)
    with pytest.raises(RuntimeError):
        snapshot.publish(cfg, opener=lambda *a, **kw: io.BytesIO(b"partial file"))
    assert (tmp_path / "recent.parquet").read_bytes() == previous
    assert (tmp_path / "status.json").read_text() == status
    assert not (tmp_path / "recent.parquet.tmp").exists()
    monkeypatch.setattr(snapshot.time, "time", lambda: 221)
    assert not snapshot.healthy(cfg)


def test_bootstrap_references_snapshot_and_only_runs_before_gateway(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(snapshot, "duckdb_execute", lambda *args: calls.append(args))
    snapshot.bootstrap(config(tmp_path))
    assert calls[0][0] == tmp_path / "recent.duckdb"
    assert "CREATE OR REPLACE VIEW valeosense_recent.telemetry" in calls[0][1]
    assert str(tmp_path / "recent.parquet") in calls[0][1]


def test_queryflux_config_injects_secret_and_retains_two_engine_rule(tmp_path):
    from scripts.queryflux_config import generate

    target = tmp_path / "config.yaml"
    generate(Path("infra/queryflux.yaml"), target, compose=True, api_key="test-secret")
    text = target.read_text()
    assert "engine: duckDb" in text and "engine: clickHouse" in text
    assert "targetGroup: recent-analytics" in text and "routingFallback: analytics" in text
    assert "http://queryflux:18080" in text and "http://clickhouse:8123" in text
    assert target.stat().st_mode & 0o777 == 0o600
