# QueryFlux: ClickHouse and DuckDB

Previously, FastAPI sent every routed analytical request to ClickHouse. The Compose
demo now uses QueryFlux as the same authenticated Trino HTTP gateway to two real
engines. PostgreSQL metadata and Redis live state remain direct API dependencies;
they are not QueryFlux analytical backends. Kafka → processor → ClickHouse remains
the canonical ingestion path.

## Start and verify

After `make setup` (or `python3 scripts/setup_env.py` for Docker-only setup):

```bash
docker compose config --quiet
docker compose up --build -d
make verify-dual-engine
make integration-queryflux
make monitoring
EXPECT_QUERYFLUX=1 make monitoring-test
EXPECT_QUERYFLUX=1 make browser-test
```

The root Compose file automatically includes QueryFlux, the snapshot worker and the
simulator. `make demo-queryflux` remains supported. Both commands start a simulator;
do not start another one. Open http://localhost:3000 and use the API key from `.env`.
The **A closer look** panel submits the small workload. Existing activity, idling,
fault and history panels use ClickHouse.

`make verify-dual-engine` requires fresh streamed readings for V000001 and
`DEBUG=true`. It checks both real API paths and independent native QueryFlux
success counters. For explicit fixture lineage verification:

```bash
docker compose exec -T backend python -m scripts.verify_dual_engine --seed
```

This inserts three identified synthetic readings using the existing generator and
detector into canonical ClickHouse, waits for the scheduled snapshot, then finds
the exact event IDs through **both** QueryFlux routes. It does not insert directly
into DuckDB or claim to test Kafka. `make integration-queryflux` additionally runs
the existing real Kafka → processor → Redis/ClickHouse → API regression.

## Data and ownership

`duckdb-sync` exports a bounded query of the deduplicated
`valeosense.telemetry_read` view to Parquet every 30 seconds. Defaults:

| Setting | Default | Meaning |
|---|---:|---|
| `DUCKDB_WINDOW_MINUTES` | 120 | Maximum event-time lookback |
| `DUCKDB_VEHICLE_LIMIT` | 100 | IDs V000001 through V000100 |
| `DUCKDB_ROW_LIMIT` | 20000 | Newest readings across the entire sample, not per vehicle |
| `DUCKDB_SYNC_SECONDS` | 30 | Refresh interval |
| `DUCKDB_MAX_AGE_SECONDS` | 120 | Maximum acceptable snapshot age |

The row cap can shorten the effective time range. Results are explicitly a sample,
not complete history or a representative fleet estimate. The endpoint accepts up
to eight IDs within the sample and a 1–60 minute range within the configured window.

The worker caps export execution at 20 seconds, ClickHouse query memory at 128 MiB,
and transfer size at 32 MiB. It validates the completed Parquet file before atomic
replacement. A sentinel row in the same file supplies freshness and scope even for
an empty sample; it is excluded from API data. Failed exports preserve the last
complete snapshot without advancing its timestamp.

The `duckdb` Docker volume holds `recent.parquet`, health metadata and
`recent.duckdb`. Before QueryFlux starts, a bootstrap creates a DuckDB view over the
Parquet path. QueryFlux alone owns the persistent DuckDB database while running.
The worker uses a separate in-memory DuckDB connection to validate exports; it
does not contend for the persistent database lock. No processor dual write or
additional DuckDB server/host port is introduced.

## Exact routing rules

The digest-pinned upstream image is
`ghcr.io/lakeops-org/queryflux@sha256:1da899cddf3c95c41ac074d8dd6f3de59dd10050abc344fdd19528e874b4f2e3`.
Its binary reports `0.0.1`; its embedded DuckDB library reports `v1.5.1`. The earlier
local source checkout `5d06d83` has a `0.3.0` version file and is not claimed to be
the image's source revision. The exact running image accepts and executes this
configuration from [infra/queryflux.yaml](../infra/queryflux.yaml):

```yaml
routers:
  - type: queryRegex
    rules:
      - regex: '(?i)\bFROM\s+valeosense_recent\.telemetry\b'
        targetGroup: recent-analytics
routingFallback: analytics
```

`recent-analytics` contains only `valeosense-duckdb` (`engine: duckDb`,
`databasePath: /data/recent.duckdb`); `analytics` contains only
`valeosense-clickhouse` (`engine: clickHouse`). The first group allows one running
and eight queued queries; the second allows four running and sixteen queued.
`routingFallback` means the destination for unmatched SQL, **not failover after an
engine error**. Routing is explicit SQL-regex matching on the sample namespace,
not cost estimation, AI, semantic query analysis, or automatic size detection.
FastAPI chooses fixed workload templates, then sends both through the same client.

Example small query routed to DuckDB:

```sql
SELECT vehicle_id, AVG(speed_kmh) AS average_speed_kmh
FROM valeosense_recent.telemetry
WHERE vehicle_id IN ('V000001', 'V000002')
  AND CAST(timestamp AS TIMESTAMP) >= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
GROUP BY vehicle_id;
```

The API's production template additionally checks snapshot age and returns scope.
Example fleet query routed to ClickHouse:

```sql
SELECT event_type, COUNT(*) AS events
FROM valeosense.telemetry_read
WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '1 day'
GROUP BY event_type;
```

These are documentation examples, not a public arbitrary-SQL interface. Authenticated
API inputs remain restricted to validated IDs and integer bounds; no SQL is accepted
from the browser. ClickHouse FINAL remains encapsulated in read views.

## Observability and failures

`/api/v1/system/metrics` exposes per-workload engine requests, successes, errors and
cumulative latency. `/api/v1/system/routing` exposes counters and last successful
execution per workload. Debug `execution.engine` is the **configured workload
label**, not a native engine receipt. Independent execution evidence comes from
QueryFlux's internal `/metrics` endpoint on port 19000:

- `queryflux_queries_total{engine_type="ClickHouse",status="Success"}`
- `queryflux_queries_total{engine_type="DuckDb",status="Success"}`
- `queryflux_query_duration_seconds_sum` and `_count`, labelled by `engine_type`

Prometheus scrapes these directly. Four additional Grafana panels show native
successes, mean latency, failures and API workload failures. Native counters also
include verification queries outside the API, so they need not equal API counters.

A stale snapshot raises an engine error, becomes HTTP 503, and increments the
DuckDB workload error counter. A missing metadata row also returns 503. Existing
ClickHouse queries remain usable when only snapshot refresh fails. A QueryFlux
outage fails all routed analytics. There is no silent direct or cross-engine
fallback. Core `/health` checks Redis, PostgreSQL and ClickHouse only; it does not
certify snapshot freshness or QueryFlux execution. Startup waits for a valid
snapshot and QueryFlux health; runtime dependency failure does not restart FastAPI.

## Compatibility and limits

The thin image adds bootstrap/export scripts to the upstream image without copying
or rebuilding QueryFlux source. Credentials are generated inside the container in
`/tmp/queryflux.yaml` and are never committed. Internal gateway requests use
`http://queryflux:18080`. Port 18081 is loopback-only; host clients cannot follow
container-advertised pagination URLs, so verification runs inside the backend.

`ANALYTICS_ROUTE=direct make demo` retains the original direct ClickHouse mode;
the sample endpoint explicitly reports unavailable. `make queryflux` retains the
existing host-native ClickHouse-only launcher using
[queryflux-native.yaml](../infra/queryflux-native.yaml). Use Compose for the
automatically initialized two-engine demo. The native launcher still requires an
existing upstream binary/libraries; no new native-build portability is claimed.

This deployment does not implement federated joins, automatic workload sizing,
engine failover, result caching, durable cold archival or a throughput improvement
claim. DuckDB is an embedded engine querying a refreshable bounded file, not a
second canonical telemetry store. Redis's existing 256 MiB cap and 24-hour dedup
TTL still limit sustained demo duration; monitor memory and stop traffic when done.

## Files changed for this integration

Implementation, compatibility, documentation and fresh verification artifacts:

```text
.env.example
.gitignore
Makefile
README.md
RUN_PROJECT.md
artifacts/browser-smoke.json
artifacts/dashboard-desktop.png
artifacts/dashboard-mobile.png
artifacts/dual-engine-lineage.json
artifacts/dual-engine-stream.json
artifacts/monitoring-smoke.json
backend/analytics.py
backend/main.py
backend/monitoring.py
compose.yaml
docs/adr/004-queryflux.md
docs/architecture.md
docs/architecture.mmd
docs/demo-script.md
docs/monitoring.md
docs/open-source.md
docs/queryflux.md
docs/solution-document.md
docs/submission-checklist.md
docs/verification.md
frontend/scripts/smoke.mjs
frontend/src/main.jsx
frontend/src/style.css
infra/demo.compose.yml
infra/docker-compose.yml
infra/monitoring/dashboards/valeosense.json
infra/monitoring/prometheus.yml
infra/queryflux-native.yaml
infra/queryflux.Dockerfile
infra/queryflux.yaml
scripts/duckdb_snapshot.py
scripts/queryflux_config.py
scripts/verify_dual_engine.py
scripts/verify_monitoring.py
shared/config.py
tests/integration/test_dual_engine.py
tests/unit/test_analytics.py
tests/unit/test_api.py
tests/unit/test_duckdb_snapshot.py
tests/unit/test_monitoring.py
```
