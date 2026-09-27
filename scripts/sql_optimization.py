"""Capture actual ClickHouse plans and read statistics; never invent plan output."""

import json
import statistics
from pathlib import Path

from shared.config import Settings
from shared.storage import ClickHouse


def main():
    store = ClickHouse(Settings())
    queries = {
        "before": "SELECT timestamp, speed_kmh FROM valeosense.telemetry_read WHERE substring(vehicle_id, 2) = '000001' ORDER BY timestamp DESC LIMIT 100",
        "after": "SELECT timestamp, speed_kmh FROM valeosense.telemetry_read WHERE vehicle_id = 'V000001' ORDER BY timestamp DESC LIMIT 100",
    }
    results = {}
    for name, sql in queries.items():
        plan = store.execute("EXPLAIN indexes = 1 " + sql)
        runs = [json.loads(store.execute(sql + " FORMAT JSON")) for _ in range(5)]
        results[name] = {
            "query": sql,
            "plan": plan,
            "statistics": [r["statistics"] for r in runs],
            "rows": len(runs[-1]["data"]),
            "data": runs[-1]["data"],
            "median_elapsed_seconds": statistics.median(r["statistics"]["elapsed"] for r in runs),
        }
    assert results["before"]["data"] == results["after"]["data"], (
        "optimization changed query results"
    )
    Path("artifacts/sql-optimization.json").write_text(json.dumps(results, indent=2))
    text = [
        "# SQL optimization evidence",
        "",
        "Historical vehicle lookup over the same persisted data, with identical results.",
        "Before: substring predicate prevents direct equality on the leading ordering key.",
        "After: exact vehicle_id predicate matches the MergeTree ordering (vehicle_id, timestamp, event_id).",
        "Both read the deduplicated FINAL view; monthly partitions and 30-day TTL bound retention.",
        "",
        "Five local executions per query. Times include ClickHouse execution only, not API or network latency.",
    ]
    for name, result in results.items():
        text += [
            "",
            f"## {name.title()}",
            "",
            "```sql",
            result["query"],
            "```",
            "",
            "Actual EXPLAIN indexes = 1:",
            "```text",
            result["plan"].strip(),
            "```",
            "",
            f"Median execution: {result['median_elapsed_seconds']:.6f} seconds.",
            f"Read rows in each run: {[s['rows_read'] for s in result['statistics']]}",
        ]
    text += [
        "",
        "This demonstrates index pruning, not a universal speedup. Small datasets, caches, concurrent ingestion,",
        "and FINAL processing affect elapsed time. See raw statistics in artifacts/sql-optimization.json.",
        "Reproduce: `make sql-evidence`.",
    ]
    Path("docs/sql-optimization.md").write_text("\n".join(text) + "\n")
    store.close()
    print("Captured real plans and five runs per query; result equality verified.")


if __name__ == "__main__":
    main()
