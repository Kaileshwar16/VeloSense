# Verification record

Checks below were run locally on 2026-09-27. Saved benchmark evidence is identified
separately from fresh execution. The original supplied DOCX and untracked
`artifacts/tests.txt` were preserved.

| Check | Result | Evidence / reproduction |
|---|---|---|
| Ruff check and formatting | Passed | `make lint` |
| Original unit/API suite before continuation | 37 passed, 1 integration skipped | `.venv/bin/pytest -q`, outside restricted sandbox |
| Complete updated suite with QueryFlux required | 46 passed | [tests-compose-queryflux.txt](../artifacts/tests-compose-queryflux.txt); `RUN_INTEGRATION=1 EXPECT_QUERYFLUX=1 .venv/bin/pytest -q` |
| Frontend production build | Passed | `make frontend-build` |
| Real React dashboard browser check | Passed in Chromium 146 | [browser-smoke.json](../artifacts/browser-smoke.json); `make browser-test` |
| Optional monitoring Compose startup | All three services healthy | `make monitoring` |
| Prometheus configuration | Valid, checked in running container | `promtool check config /etc/prometheus/prometheus.yml` |
| Grafana provisioning and actual scrape | Passed, 14 panels and all PromQL expressions accepted | [monitoring-smoke.json](../artifacts/monitoring-smoke.json); `make monitoring-test` |
| Grafana browser rendering | Passed with real datasource queries, no JavaScript errors | [grafana-browser-smoke.json](../artifacts/grafana-browser-smoke.json); `cd frontend && node scripts/monitoring-smoke.mjs` |

The full suite includes 45 unit/API/exporter cases and one external integration
case. The integration publishes 25 idling readings plus a duplicate through real
Kafka, waits for processor persistence, checks live/history APIs, requires the
successful QueryFlux route, verifies UTC strings, and checks ClickHouse dedup
after a deliberate replay insert. It does not prove all failure modes or sustained
capacity. Exporter cases cover authentication forwarding, upstream failures,
counter/seconds conversion and omitted stale/missing data.

The first sandboxed test run hung during asyncio teardown after a passing API
case; a bounded diagnostic reproduced it. The complete suite subsequently passed
outside the sandbox. Docker, local network and Chromium checks also required
execution outside the restricted sandbox. This is not a claim that the sandboxed
run passed.

## Earlier saved evidence

- [Direct-mode suite](../artifacts/tests-compose-direct.txt): 38 passed before the
  monitoring additions; not a fresh direct-route rerun in this continuation.
- [Benchmark](benchmark.md) and [raw data](../benchmark_results.json): two short
  stages recorded earlier on the same date; not rerun with monitoring enabled.
- [SQL optimization](sql-optimization.md): saved identical-result lookup plans and
  execution statistics; not rerun in this continuation.

## Limits

No production load soak, HA/failover qualification, p95/p99 API benchmark, security
scan campaign, coverage measurement, archive, cloud deployment or recorded video
is implied by these checks. The default CI runs lint, unit tests and frontend build;
integration, browser and monitoring checks need the real local stack.
