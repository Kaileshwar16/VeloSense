"""Bounded ClickHouse -> atomic Parquet snapshots for QueryFlux's embedded DuckDB.

Uses the pinned image's DuckDB C library only for bootstrap/validation. The running
QueryFlux process alone owns the database; this worker only replaces Parquet files.
"""

import argparse
import ctypes
import json
import logging
import os
import signal
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotConfig:
    directory: Path
    clickhouse_url: str
    window_minutes: int = 120
    vehicle_limit: int = 100
    row_limit: int = 20000
    interval_seconds: int = 30
    max_age_seconds: int = 120

    def __post_init__(self):
        for name, value, maximum in (
            ("window_minutes", self.window_minutes, 1440),
            ("vehicle_limit", self.vehicle_limit, 1000),
            ("row_limit", self.row_limit, 100000),
            ("interval_seconds", self.interval_seconds, 60),
            ("max_age_seconds", self.max_age_seconds, 600),
        ):
            if not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")
        if self.max_age_seconds <= self.interval_seconds:
            raise ValueError("snapshot maximum age must exceed the refresh interval")

    @classmethod
    def from_env(cls):
        return cls(
            directory=Path(os.getenv("DUCKDB_DATA_DIR", "/data")),
            clickhouse_url=os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123"),
            **{
                name: int(os.getenv(env, str(default)))
                for name, env, default in (
                    ("window_minutes", "DUCKDB_WINDOW_MINUTES", 120),
                    ("vehicle_limit", "DUCKDB_VEHICLE_LIMIT", 100),
                    ("row_limit", "DUCKDB_ROW_LIMIT", 20000),
                    ("interval_seconds", "DUCKDB_SYNC_SECONDS", 30),
                    ("max_age_seconds", "DUCKDB_MAX_AGE_SECONDS", 120),
                )
            },
        )


def export_sql(config: SnapshotConfig, now: float) -> str:
    # One metadata row travels in the SAME atomic file, even for an empty sample.
    # It is excluded from API data, and prevents an old/empty snapshot hiding staleness.
    metadata = (
        f"toFloat64({now}) AS snapshot_epoch, "
        f"toUInt32({config.window_minutes}) AS window_minutes, "
        f"toUInt32({config.vehicle_limit}) AS vehicle_limit, "
        f"toUInt32({config.row_limit}) AS row_limit"
    )
    return (
        "SELECT toString(event_id) AS event_id, vehicle_id, fleet_id, "
        "toString(timestamp) AS timestamp, toFloat64(speed_kmh) AS speed_kmh, event_type, "
        + metadata
        + " FROM (SELECT event_id, vehicle_id, fleet_id, timestamp, speed_kmh, event_type "
        "FROM valeosense.telemetry_read "
        f"WHERE vehicle_id >= 'V000001' AND vehicle_id <= 'V{config.vehicle_limit:06d}' "
        f"AND timestamp >= fromUnixTimestamp64Milli({int(now * 1000)}) "
        f"- INTERVAL {config.window_minutes} MINUTE "
        f"AND timestamp <= fromUnixTimestamp64Milli({int(now * 1000)}) "
        f"ORDER BY timestamp DESC, event_id LIMIT {config.row_limit}) "
        "UNION ALL SELECT '', '', '', '', toFloat64(0), '', " + metadata + " FORMAT Parquet"
    )


class DuckResult(ctypes.Structure):
    # duckdb_result from the pinned v1.5.1 duckdb.h (public C API ABI).
    _fields_ = [
        ("column_count", ctypes.c_uint64),
        ("row_count", ctypes.c_uint64),
        ("rows_changed", ctypes.c_uint64),
        ("columns", ctypes.c_void_p),
        ("error", ctypes.c_void_p),
        ("internal_data", ctypes.c_void_p),
    ]


def duckdb_execute(database: Path | None, sql: str):
    """Run internal bootstrap SQL, using the exact library shipped with QueryFlux."""
    lib = ctypes.CDLL(os.getenv("DUCKDB_LIBRARY", "/usr/local/lib/libduckdb.so"))
    pointer = ctypes.POINTER(ctypes.c_void_p)
    lib.duckdb_open.argtypes = [ctypes.c_char_p, pointer]
    lib.duckdb_open.restype = ctypes.c_int
    lib.duckdb_connect.argtypes = [ctypes.c_void_p, pointer]
    lib.duckdb_connect.restype = ctypes.c_int
    lib.duckdb_query.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(DuckResult)]
    lib.duckdb_query.restype = ctypes.c_int
    lib.duckdb_result_error.argtypes = [ctypes.POINTER(DuckResult)]
    lib.duckdb_result_error.restype = ctypes.c_char_p
    lib.duckdb_destroy_result.argtypes = [ctypes.POINTER(DuckResult)]
    lib.duckdb_disconnect.argtypes = [pointer]
    lib.duckdb_close.argtypes = [pointer]
    db, conn = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if lib.duckdb_open(str(database).encode() if database else None, ctypes.byref(db)):
            raise RuntimeError("DuckDB database could not be opened; check permissions/ownership")
        if lib.duckdb_connect(db, ctypes.byref(conn)):
            raise RuntimeError("DuckDB connection failed")
        result = DuckResult()
        try:
            if lib.duckdb_query(conn, sql.encode(), ctypes.byref(result)):
                message = lib.duckdb_result_error(ctypes.byref(result))
                raise RuntimeError(message.decode() if message else "DuckDB bootstrap failed")
        finally:
            lib.duckdb_destroy_result(ctypes.byref(result))
    finally:
        if conn:
            lib.duckdb_disconnect(ctypes.byref(conn))
        if db:
            lib.duckdb_close(ctypes.byref(db))


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def publish(config: SnapshotConfig, opener=urllib.request.urlopen):
    config.directory.mkdir(parents=True, exist_ok=True)
    started = time.time()
    query = export_sql(config, started)
    params = urllib.parse.urlencode({"max_execution_time": 20, "max_memory_usage": 134217728})
    request = urllib.request.Request(
        config.clickhouse_url.rstrip("/") + "/?" + params, data=query.encode(), method="POST"
    )
    temporary = config.directory / "recent.parquet.tmp"
    try:
        with opener(request, timeout=25) as response, temporary.open("wb") as output:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 32 * 1024 * 1024:
                    raise RuntimeError("snapshot exceeds the 32 MiB transfer cap")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        # Also catches ClickHouse errors appended after an HTTP 200 streaming header.
        duckdb_execute(None, f"SELECT count(*) FROM read_parquet('{sql_path(temporary)}')")
        temporary.replace(config.directory / "recent.parquet")
        status = config.directory / "status.json.tmp"
        status.write_text(json.dumps({"snapshot_epoch": started, "bytes": total}))
        status.replace(config.directory / "status.json")
        logging.info("snapshot_published bytes=%s", total)
    finally:
        temporary.unlink(missing_ok=True)


def bootstrap(config: SnapshotConfig):
    parquet = config.directory / "recent.parquet"
    # Only called before QueryFlux starts, never concurrently against its DB file.
    duckdb_execute(
        config.directory / "recent.duckdb",
        (
            "CREATE SCHEMA IF NOT EXISTS valeosense_recent; "
            "CREATE OR REPLACE VIEW valeosense_recent.telemetry AS "
            f"SELECT * FROM read_parquet('{sql_path(parquet)}');"
        ),
    )


def healthy(config: SnapshotConfig) -> bool:
    try:
        status = json.loads((config.directory / "status.json").read_text())
        age = time.time() - status["snapshot_epoch"]
        return 0 <= age < config.max_age_seconds and (config.directory / "recent.parquet").is_file()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sync", "once", "bootstrap", "health"])
    args = parser.parse_args()
    config = SnapshotConfig.from_env()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "health":
        raise SystemExit(0 if healthy(config) else 1)
    if args.command == "bootstrap":
        bootstrap(config)
        return
    if args.command == "once":
        publish(config)
        return
    import threading

    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            publish(config)
        except Exception as error:
            # Keep the last complete file, but never advance its freshness timestamp.
            logging.error("snapshot_failed type=%s", type(error).__name__)
        stopped.wait(config.interval_seconds)


if __name__ == "__main__":
    main()
