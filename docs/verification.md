# Verification record

The original checks below were run locally on 2026-09-27. Browser and monitoring artifacts are refreshed by later runs; their embedded timestamps identify the latest evidence. Saved benchmark evidence is identified
separately from fresh execution. The original supplied DOCX and untracked
`artifacts/tests.txt` were preserved.

| Check | Result | Evidence / reproduction |
|---|---|---|
| Ruff check and formatting | Passed | `make lint` |
| Updated unit/API suite | 68 passed, 1 external integration skipped | [tests-unit-final.txt](../artifacts/tests-unit-final.txt); `.venv/bin/pytest -q` |
| Complete updated suite with QueryFlux required | 69 passed | [tests-compose-queryflux.txt](../artifacts/tests-compose-queryflux.txt); `RUN_INTEGRATION=1 EXPECT_QUERYFLUX=1 .venv/bin/pytest -q` |
| Frontend production build | Passed | `make frontend-build` |
| Real React dashboard browser check | Passed in Chromium 146 | [browser-smoke.json](../artifacts/browser-smoke.json); `make browser-test` |
| Optional monitoring Compose startup | All three services healthy | `make monitoring` |
| Prometheus configuration | Valid, checked in running container | `promtool check config /etc/prometheus/prometheus.yml` |
| Grafana provisioning and actual scrape | Passed, 14 panels and all PromQL expressions accepted | [monitoring-smoke.json](../artifacts/monitoring-smoke.json); `make monitoring-test` |
| Grafana browser rendering | Passed with real datasource queries, no JavaScript errors | [grafana-browser-smoke.json](../artifacts/grafana-browser-smoke.json); `cd frontend && node scripts/monitoring-smoke.mjs` |

The full suite includes 68 unit/API/exporter/benchmark cases and one external integration
case. The integration publishes 25 idling readings plus a duplicate through real
Kafka, waits for processor persistence, checks live/history APIs, requires the
successful QueryFlux route, verifies UTC strings, and checks ClickHouse dedup
after a deliberate replay insert. It does not prove all failure modes or sustained
capacity. Exporter cases cover authentication forwarding, upstream failures,
counter/seconds conversion and omitted stale/missing data. Added regressions cover
configurable braking, invalid weights, low-rate pacing, failure reports, cancelled
analytical waiters, no silent route fallback, and benchmark preflight/accounting.

The first sandboxed test run hung during asyncio teardown after a passing API
case; a bounded diagnostic reproduced it. The complete suite subsequently passed
outside the sandbox. Docker, local network and Chromium checks also required
execution outside the restricted sandbox. This is not a claim that the sandboxed
run passed.

## Two-engine completion (2026-09-29 local date)

The runtime clock recorded these checks on 2026-09-28 UTC. The root
`docker compose up --build -d` started the complete demo with automatic DuckDB
bootstrap and fresh streamed telemetry; no volumes were cleared. The pinned
binary reports QueryFlux `0.0.1` and bundled DuckDB `v1.5.1`.

- Python unit/API suite: **92 passed, 2 integration tests skipped** in the host
  run. The initial sandbox run stalled in async API tests and was interrupted;
  the successful run was outside the sandbox.
- Real Compose integration suite: **2 passed**. This covers the existing Kafka
  ingestion/dedup/history path and exact seeded event-ID lineage through both
  analytical engines (`make integration-queryflux`).
- [Stream routing evidence](../artifacts/dual-engine-stream.json): fresh V000001
  readings returned through the DuckDB API and fleet activity through ClickHouse;
  native success counters advanced for both engines.
- [Fixture lineage evidence](../artifacts/dual-engine-lineage.json): three explicitly
  seeded canonical events found through both gateway routes after snapshot refresh.
- Failure injection: stopped `duckdb-sync`, waited past the 120-second freshness
  bound, observed sample HTTP **503**, history HTTP **200**, and an increased API
  DuckDB error counter. Restarted the worker and verified recovery. No stale result
  was served as successful data; no automatic fallback was used.
- Python Ruff check/format, frontend production build, root and direct Compose
  configuration validation, and running Prometheus configuration check passed.
- Frontend tests: **3 request tests and 4 Playwright tests passed**. There is no
  frontend `lint` npm script; an attempted invocation reported that absence.
- Real Chromium smoke: passed with **Stream connected**, a successful DuckDB panel
  query, history/pagination, desktop/mobile screenshots and no JavaScript errors
  ([browser evidence](../artifacts/browser-smoke.json)).
- Grafana: **18 panels**, all PromQL accepted, exporter scrape up, native QueryFlux
  scrape up, and successful native observations for **ClickHouse and DuckDb**
  ([monitoring evidence](../artifacts/monitoring-smoke.json)).

API engine labels identify configured workloads; native QueryFlux counters provide
independent execution evidence. These checks demonstrate routing and correctness,
not a speedup or new throughput benchmark. Redis memory retention remains the
existing sustained-run limit; traffic is stopped after verification. See
[the run guide](../RUN_PROJECT.md) and [routing details](queryflux.md).

## Fresh submission audit evidence

- [Registry](../artifacts/registry-verification.json): regenerated exactly 100,000
  unique IDs and VINs with seed 42; deterministic CSV unchanged.
- [Small stream](../artifacts/small-run.json): 1,000 vehicles at a 1K/sec target for
  ten seconds; 10,000 generated, 10,190 published (including intentional duplicates),
  no delivery errors or undelivered records.
- [Benchmark](benchmark.md): fresh 15-second stages with optional monitoring enabled;
  1K stable, 10K unstable, larger targets not attempted. The runner initially stopped
  on an outdated inter-stage lag gauge; a bounded measured-zero wait fixed that
  preflight issue, and the rerun completed.
- [SQL optimization](sql-optimization.md): fresh EXPLAIN and five executions per
  query, with result equality checked before starting the continuous demo.
- `make demo-queryflux` built and started the core stack, seeded metadata, and
  launched the safe 1K/sec simulator. Browser checks ran against this live stack.

## Earlier saved evidence

- [Direct-mode suite](../artifacts/tests-compose-direct.txt): 38 passed before the
  monitoring additions; not a fresh direct-route rerun in this continuation.
- [Original benchmark](../artifacts/benchmark-before-audit.json): earlier short
  run retained separately; the current summary uses the fresh benchmark.

## Limits

No production load soak, HA/failover qualification, p95/p99 API benchmark, security
scan campaign, coverage measurement, archive, cloud deployment or recorded video
is implied by these checks. The default CI runs lint, unit tests and frontend build;
integration, browser and monitoring checks need the real local stack.
