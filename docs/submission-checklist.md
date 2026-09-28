# Submission checklist audit

Audited against the supplied 63-section one-day brief on 2026-09-27. **Done** means
implemented and checked locally; it does not imply production qualification.
Commands, fresh results and artifacts are in [verification.md](verification.md).

| Brief sections | Requirement | Status / evidence |
|---|---|---|
| 0–7, 57–59 | Small working stack; preserve existing work | Done: Python, Compose, React; existing source retained |
| 8 | Exactly 100K deterministic synthetic vehicles | Done: regenerated CSV, unique IDs/VINs verified; `artifacts/registry-verification.json` |
| 9–17, 54, 56 | Stateful canonical events and all twelve scenarios | Done: schema/generator/detector tests; real alerts in integration |
| 12–14 | Configurable idling, braking, speeding, faults | Done: environment thresholds and DTC episodes; tests cover detector behavior |
| 18–21 | Batched generation, bounded buffering, load modes | Done: simulator CLI + progressive benchmark; low-rate pacing corrected; shutdown failures retain reports |
| 22–26 | Validation, dedup, live state, metadata, history | Done: real Kafka → processor → Redis/ClickHouse → API test; PostgreSQL fleet/vehicle metadata |
| 4, 27 | Existing QueryFlux, genuine analytical route | Done: upstream checkout/config re-inspected; digest-pinned container; ClickHouse and bounded DuckDB sample; see queryflux.md for verification |
| 28–29 | API, validation, pagination, basic authentication | Done: API key, CORS, parameterized metadata SQL, bounded templates; JWT/rate limiting optional and deferred |
| 30–31 | Dashboard, polling, query counters, health | Done: real browser verification; added live/metadata/analytical counters; unknown/stale lag shown as unavailable |
| 32–33 | Hot/warm/cold design; Iceberg | Hot/warm done; cold design documented; Parquet/MinIO and Iceberg deferred as allowed |
| 34 | Safe result caching if implemented | Not applicable: no result cache |
| 35–36 | Analytical admission, metrics and routing | Done: semaphore, bounded wait queue, cancellation test; latency totals exposed; optional Grafana validated |
| 37, 60 | Tests and actual end-to-end verification | Done: unit/API tests, real integration, registry generation, small real stream, builds and browser checks |
| 38, 61 | Progressive actual load measurements | Done: fresh staged run, stops at first unstable stage; `benchmark_results.json` |
| 39 | At least one real query optimization | Done: ClickHouse EXPLAIN and identical results before/after; `docs/sql-optimization.md` |
| 40 | One real failure demonstration | Done: duplicate Kafka publication and analytical replay tested; exact commands in `docs/failure-demo.md` |
| 41–43 | Compose, Make commands, CI | Done: safe defaults; optional profiles; GitHub Actions for lint/unit/build |
| 44–48 | Architecture, ER, 3–5 ADRs, CAP, STRIDE | Done: diagrams, five ADRs, explicit single-node/consistency limits |
| 49–50 | Dependencies, licenses, AI declaration | Done: confirmed sources and installed licenses; QueryFlux separately attributed |
| 51–53 | README and exact solution sections | Done: all requested subsections present; evidence and unimplemented capabilities labelled |
| 55, 62 | Five-minute demo and handoff | Demo script ready; final operating commands/results supplied; video recording remains a team action |

## Gaps corrected in this audit

- Harsh-braking, speeding and acceleration thresholds now read environment settings
  and reject invalid values. `SEED` is honored by the simulator CLI.
- Low-rate generation no longer publishes an oversized batch each loop. Duration
  caps generation, probability weights reject NaN/infinity, and failure/flush
  cleanup preserves a machine-readable report and the original failure.
- Benchmarks require known zero initial lag and no active simulator. Exact
  published/consumed counts and a stable processor instance are required for a
  stage to pass; overconsumption cannot inflate the stable result.
- API metrics now include analytical latency totals and the latest completed
  attempt. The UI displays workload query counts and does not turn unknown lag
  or a missing route into a reassuring value. Stopped simulator metrics are not
  exported as current throughput.
- Submission subsections now match the brief. Monitoring appears in the Mermaid
  architecture; fresh evidence replaces stale verification counts.

## Intentionally deferred

Cold archive, Iceberg, automatic cost-based routing, query caching, JWT/OIDC/RBAC/tenant
isolation, service TLS/authentication, general API rate limiting, durable rejected
events, partition-owned processors, Kubernetes/Terraform, ML and agentic AI.
These are optional/future features, not blockers for the authorized one-day demo.
`alert_rules` is a schema placeholder; runtime rules come from settings.

## Team actions before submission

Supply team/member details, the final repository URL and submission date. Record
the five-minute video, fill in actual feature timestamps and its URL, then export
the solution document to the organizer's required submission format. No video,
PDF, publication, deployment or customer validation is claimed by this audit.
