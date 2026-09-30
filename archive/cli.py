"""Archive operations. Install requirements-iceberg.lock before using this module."""

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from pyiceberg.expressions import And, EqualTo, GreaterThanOrEqual, LessThan

from archive.config import ArchiveConfig
from archive.table import PREFIX, START_PREFIX, open_table


def query_rows(table, *, vehicle_id, start, end, limit=100, snapshot_id=None):
    if not re.fullmatch(r"V\d{6}", vehicle_id) or not 1 <= limit <= 1000:
        raise ValueError("a valid vehicle ID and limit between 1 and 1000 are required")
    lower, upper = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if lower.tzinfo is None or upper.tzinfo is None or lower >= upper:
        raise ValueError("start/end must be ordered timestamps with timezones")
    if snapshot_id is not None and table.snapshot_by_id(snapshot_id) is None:
        raise ValueError("snapshot does not exist")
    predicate = And(
        EqualTo("valid", True),
        EqualTo("vehicle_id", vehicle_id),
        GreaterThanOrEqual("timestamp", lower.isoformat()),
        LessThan("timestamp", upper.isoformat()),
    )
    fields = tuple(name for name in table.schema().column_names if name != "raw_payload")
    return (
        table.scan(
            row_filter=predicate, selected_fields=fields, limit=limit, snapshot_id=snapshot_id
        )
        .to_arrow()
        .to_pylist()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("consume", "status", "health"):
        commands.add_parser(name)
    query = commands.add_parser("query")
    query.add_argument("--vehicle-id", required=True)
    query.add_argument("--start", required=True)
    query.add_argument("--end", required=True)
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--snapshot-id", type=int)
    args = parser.parse_args()
    health_path = Path(os.getenv("ICEBERG_HEALTH_PATH", "/data/iceberg/health.json"))
    if args.command == "health":
        try:
            age = time.time() - json.loads(health_path.read_text())["heartbeat"]
            raise SystemExit(0 if 0 <= age < 120 else 1)
        except (OSError, ValueError, KeyError, TypeError):
            raise SystemExit(1) from None
    config = ArchiveConfig.from_env()
    if args.command == "consume":
        from archive.consumer import consume

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        try:
            consume(config, health_path)
        except Exception as error:
            # Driver errors can include credential-bearing connection strings.
            logging.error("archive_failed type=%s; restart required", type(error).__name__)
            raise SystemExit(1) from None
        return
    table = open_table(config)
    if args.command == "status":
        snapshot = table.current_snapshot()
        output = {
            "table": config.table,
            "snapshot_id": snapshot.snapshot_id if snapshot else None,
            "total_records": int(snapshot.summary.get("total-records", "0")) if snapshot else 0,
            "next_offsets": {
                k.removeprefix(PREFIX): int(v)
                for k, v in table.properties.items()
                if k.startswith(PREFIX)
            },
            "start_offsets": {
                k.removeprefix(START_PREFIX): int(v)
                for k, v in table.properties.items()
                if k.startswith(START_PREFIX)
            },
            "snapshots": [
                {"id": s.snapshot_id, "timestamp_ms": s.timestamp_ms} for s in table.snapshots()
            ],
        }
    else:
        output = query_rows(
            table,
            vehicle_id=args.vehicle_id,
            start=args.start,
            end=args.end,
            limit=args.limit,
            snapshot_id=args.snapshot_id,
        )
    print(json.dumps(output, default=str, indent=2))


if __name__ == "__main__":
    main()
