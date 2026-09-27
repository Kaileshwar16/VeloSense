# SQL optimization evidence

Historical vehicle lookup over the same persisted data, with identical results.
Before: substring predicate prevents direct equality on the leading ordering key.
After: exact vehicle_id predicate matches the MergeTree ordering (vehicle_id, timestamp, event_id).
Both read the deduplicated FINAL view; monthly partitions and 30-day TTL bound retention.

Five local executions per query. Times include ClickHouse execution only, not API or network latency.

## Before

```sql
SELECT timestamp, speed_kmh FROM valeosense.telemetry_read WHERE substring(vehicle_id, 2) = '000001' ORDER BY timestamp DESC LIMIT 100
```

Actual EXPLAIN indexes = 1:
```text
Expression ((Project names + (Before ORDER BY + (Projection + (WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))) [lifted up part]))
  Limit (preliminary LIMIT (without OFFSET))
    Sorting (Sorting for ORDER BY)
      Expression ((Before ORDER BY + (Projection + (WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))))
        Filter (((WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))[split])
          ReadFromMergeTree (valeosense.telemetry)
          Indexes:
            MinMax
              Condition: true
              Parts: 8/8
              Granules: 474/474
            Partition
              Condition: true
              Parts: 8/8
              Granules: 474/474
            PrimaryKey
              Condition: true
              Parts: 8/8
              Granules: 474/474
              Ranges: 8
```

Median execution: 0.023693 seconds.
Read rows in each run: [515271, 515271, 515271, 515271, 515271]

## After

```sql
SELECT timestamp, speed_kmh FROM valeosense.telemetry_read WHERE vehicle_id = 'V000001' ORDER BY timestamp DESC LIMIT 100
```

Actual EXPLAIN indexes = 1:
```text
Expression ((Project names + (Before ORDER BY + (Projection + (WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))) [lifted up part]))
  Limit (preliminary LIMIT (without OFFSET))
    Sorting (Sorting for ORDER BY)
      Expression ((Before ORDER BY + (Projection + (WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))))
        Filter (((WHERE + (Change column names to column identifiers + (Convert VIEW subquery result to VIEW table structure + (Materialize constants after VIEW subquery + (Project names + (Projection + (Change column names to column identifiers + (Project names + (Projection + Change column names to column identifiers))))))))))[split])
          ReadFromMergeTree (valeosense.telemetry)
          Indexes:
            MinMax
              Condition: true
              Parts: 8/8
              Granules: 474/474
            Partition
              Condition: true
              Parts: 8/8
              Granules: 474/474
            PrimaryKey
              Keys:
                vehicle_id
              Condition: (vehicle_id in [\'V000001\', \'V000001\'])
              Parts: 4/8
              Granules: 4/474
              Search Algorithm: binary search
              Ranges: 4
```

Median execution: 0.002402 seconds.
Read rows in each run: [4096, 4096, 4096, 4096, 4096]

This demonstrates index pruning, not a universal speedup. Small datasets, caches, concurrent ingestion,
and FINAL processing affect elapsed time. See raw statistics in artifacts/sql-optimization.json.
Reproduce: `make sql-evidence`.
