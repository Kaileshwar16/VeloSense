# Submission checklist — attached PDF and Word template

Reviewed **1 October 2026** against:

- [Motorq Hackathon Problem Statement](<../Motorq_Hackathon_Problem_Statement (1).pdf>) — all 10 supplied pages, especially sections 6–14, pages 6–10.
- [Filled Word solution document](<../Motorq_Hackathon_Solution_Document_Template (1).docx>) — all 17 template sections.
- Current source at `c5549e8`, `.github/workflows/ci.yml`, deployment files, saved JSON artifacts and [verification records](verification.md) from 27–30 September.

**The local prototype is substantially implemented, but it does not meet the PDF's full production-quality requirements.** The PDF explicitly requires capabilities that the older [submission checklist](submission-checklist.md) classified as deferred under the narrower one-day project scope. Use this checklist for the attached PDF. Disclosing a gap does not satisfy a mandatory requirement; obtain an organizer-approved exception if you intend to submit a smaller scope.

This was a source/document/evidence audit. Application tests, cloud deployment, remote repository access and live pipeline health were **not rerun or verified** during document preparation. “Implemented / saved verification” below refers to existing work, not new features built in this edit.

## Work completed in this edit

- [x] Read the supplied 10-page problem statement and compare its requirements with source, saved evidence and the Word template.
- [x] Fill all 17 sections in the **original Word document**, including tables, user journey, feature/code mapping, architecture, data model, algorithms, tests, declarations and limitations.
- [x] Fill the repository URL from the configured `origin`: `https://github.com/Kaileshwar16/VeloSense`. Reviewer access remains unverified.
- [x] Include existing product/Grafana screenshots and clearly identify them as saved captures.
- [x] Add context/container/ER/layer/sequence diagrams and a chart derived from the real saved benchmark.
- [x] Include the optional Iceberg archive and its atomic offset/data checkpoint contract.
- [x] Distinguish a 100K-vehicle registry from active vehicle count and actual measured processing capacity.
- [x] Add CAP/PACELC discussion, source paths, PDF requirement cross-check, AI/open-source declaration and independent-academic-exercise affiliation statement.
- [x] Highlight unknown personal/submission fields as **TEAM ACTION** instead of inventing names, dates, URLs or timestamps.
- [x] Create this checklist. No implementation changes, commit, push or external submission were made.
- [x] Validate the Word file's ZIP/XML structure and all 17 sections, export the matching 24-page PDF preview, and review the exported text and representative page layouts. These are document checks, not fresh application verification.

The companion `docs/ValeoSense-Solution-Document-preview.pdf` is a review export, **not a finalized submission**. Regenerate it after editing the remaining fields.

## Your immediate actions

- [ ] Enter the official **team name**.
- [ ] Enter every member's **name, role and email**; confirm authentic contribution/attribution details.
- [ ] Enter the **actual submission date**. Document preparation date is not automatically the submission date.
- [ ] Confirm the **deadline, timezone and submission portal** with the organizer; the supplied PDF does not specify them.
- [ ] Record/upload a **working-product demo ≤5:00**, ideally 1080p with clear audio and captions. Follow [the exact recording guide](demo-recording-guide.md).
- [ ] Add the video URL on the cover and in section 13, and add **actual timestamps for all Done features** in section 4. Include optional monitoring/archive footage if those remain labelled Done in the submitted feature list.
- [ ] Verify the final repository and video are accessible to reviewers; check the final code is actually on the remote.
- [ ] Obtain a final **passing CI run URL**, not just a link to the workflow file. Candidate Actions page: `https://github.com/Kaileshwar16/VeloSense/actions`; access and run results are unverified.
- [ ] Review the mandatory gaps below and either complete them or obtain an explicit organizer-approved scope exception.
- [ ] Review the final PDF, remove all **TEAM ACTION**/**Pending** markers where information is now available, and regenerate the PDF from the completed Word file.
- [ ] Create `v1.0-submission` on the final reviewed **pre-deadline** commit and publish that code/tag when ready. No local tag currently exists; remote tag state was not checked.
- [ ] Submit the document, repository link and video through the organizer's actual portal.

## Existing implementation with saved evidence

| Status | Requirement / capability | Evidence and boundary |
|---|---|---|
| Implemented / saved verification | Own simulator and exactly 100,000 unique synthetic vehicle IDs/VINs | `simulator/`, `scripts/generate_vehicles.py`, `artifacts/registry-verification.json`. Registry size is verified; concurrent telemetry from all 100K is not. |
| Implemented / saved verification | Stateful events, twelve scenarios, duplicates, late events, faults and recovery bursts | `shared/models.py`, `simulator/generator.py`, simulator tests. Burst scenarios do not prove 300K/sec capacity. |
| Implemented / saved verification | Real Kafka-compatible ingestion with partitions, schema validation, backpressure and manual commits | `simulator/producer.py`, `processor/consumer.py`, `processor/pipeline.py`; real integration evidence. One broker and processor owner. |
| Implemented / saved verification | Incident rules and live state | `processor/detectors.py`, Redis state/episode handling, detector/pipeline tests. Rule-based, not ML predictions. |
| Implemented / saved verification | Relational + NoSQL + analytical stores | PostgreSQL metadata, Redis hot state, ClickHouse history; source schemas and architecture docs. |
| Implemented / saved verification | Paginated API and usable dashboard | `backend/main.py`, `frontend/src/`, saved browser artifacts. API key is present; enterprise identity/rate limiting is incomplete. |
| Implemented / saved verification | Historical analytics and bounded DuckDB sample through external QueryFlux | `artifacts/dual-engine-lineage.json`: exact seeded IDs and positive native counters for both engines. No billion-row or performance superiority claim. |
| Implemented / saved verification | Raw cold archive | `archive/`, [Iceberg guide](iceberg.md), 14 component tests and separate real Kafka/PostgreSQL checks reported on 30 September. Local filesystem only. |
| Implemented / saved verification | Replay/dedup behavior and stale-sample failure/recovery | Existing integration tests and [verification](verification.md). Not a broker-kill/HA campaign or global exactly-once guarantee. |
| Present | Dockerfiles, Compose, README, environment example, setup/run commands | `infra/`, `frontend/Dockerfile`, `compose.yaml`, `Makefile`, `RUN_PROJECT.md`. Initial setup precedes the one-command configured run. |
| Present | Architecture, ER, five ADRs, STRIDE, algorithm complexity and declarations | `docs/architecture*`, `docs/er-diagram.mmd`, `docs/adr/`, `docs/threat-model.md`, filled DOCX. Catalog normalization has explicit limits. |
| Implemented / saved verification | Prometheus/Grafana metrics and native engine observations | Optional `monitoring` profile; saved monitoring/browser records. No centralized log backend or distributed tracing. |
| Saved verification | Python/API/component tests | Latest record: **106 passed, 3 opt-in integration cases skipped**. Separate earlier core/dual-engine and archive integration runs are recorded; not all are one combined run. |
| Saved verification | Frontend request/browser checks | Earlier two-engine record: 3 request tests, 4 Playwright tests, Chromium smoke and build passed. Not freshly rerun. |
| Configured | CI for lint, Python tests and frontend build | `.github/workflows/ci.yml`; no claim of a checked current hosted run. |
| Saved verification | Short real pipeline load test | `benchmark_results.json`: **1K generation target stable**, 999.87 generated/sec, 923.99 consumed/sec including startup/drain. **10K target unstable**. |
| Saved verification | One SQL optimization | `artifacts/sql-optimization.json`: median **23.693 → 2.402 ms**, rows read **515,271 → 4,096**, equal results and five executions each. |

## Missing or partial requirements from the attached PDF

| Priority / status | PDF or template requirement | Current gap | What completes it |
|---|---|---|---|
| Required — partial | At least 100K vehicles with real-time processing (§6, p6; §8, p7) | 100K registry exists; saved streams exercise 1K and 10K active subsets. | Demonstrate the required active-fleet/rate scope; do not present registry count as throughput. |
| Required — missing | **Sustain 100K+ events/sec** (§11, p9) | Short 1K target stable; 10K unstable; higher stages unattempted. | Architecture/capacity work and an actual sustained end-to-end benchmark with exact accounting. |
| Required — missing | **Survive 3× burst for five minutes without loss** (§11, p9) | No 300K/sec, five-minute burst evidence. | Controlled burst test with sent/acknowledged/consumed/persisted counts, lag and recovery measurements. |
| Required — missing/partial | Dashboard <2 s; critical alert <5 s; API p95 <200 ms and p99 <500 ms (§11, p9) | Dashboard polls every 3 seconds; no qualifying latency distribution. | Instrument event-to-visible and event-to-alert timing; benchmark API percentiles, then address measured failures. |
| Required — missing | Horizontal scale and no single point of failure; 99.9%; broker/pod recovery (§11, p9) | One host/broker/state owner; Redis lease deliberately rejects additional processors. | Partition ownership/replication/HA design, deployed scale-out and actual failure-recovery evidence; credible availability measurement. |
| Required — missing | **At least one cloud deployment**, portability without code changes (§6, p6) | Local Compose only; no verified cloud runtime. | Deploy and verify on one cloud; provide reproducible configuration and credible portability evidence. |
| Required deliverable — missing | **Helm or Kubernetes manifests + Terraform for at least one cloud** (§13, p10) | Dockerfiles and Compose are present; those other artifacts are absent. | Working infrastructure/deployment files, instructions and validation against the deployment. |
| Required — missing | OAuth2/OIDC + JWT, RBAC and tenant isolation (§11, p9) | Single static demo key grants broad fleet access. | Identity integration, tenant authorization and positive/negative authorization tests. |
| Required — missing/unverified | Device mTLS, TLS 1.3, AES-256 at rest, vault-managed secrets (§11, p9) | Local network trust and ignored credentials; requested controls not demonstrated. | Configure and verify identities, transport/storage encryption, secret management and rotation. |
| Expected — partial | Secure, paginated, **rate-limited** APIs (§7, p7) | Pagination and bounded analytical admission exist; no general per-user rate limiter. | Enforced identity-based limits and abuse/load checks. |
| Required — missing | Data-access audit trail, location masking, retention and right-to-erasure (§11–12, p9) | Operational logs and TTLs are not audit/erasure workflows; Iceberg has no automatic retention. | Implement/test access audit, masking, deletion across stores/backups/snapshots and retained-data policy. |
| Required — missing | **80%+ coverage** on core services/algorithms (§12, p9) | Test pass counts exist, no coverage report or threshold. | Measured line/branch coverage, documented scope and a CI threshold; add tests for uncovered critical behavior. |
| Required — partial | Real-service integration and service contracts (§12, p9) | Real Compose integration exists; separate consumer-driven contract coverage is absent; tests opt out in CI. | Automated real-service integration plus explicit service-contract evidence in CI. PDF names Testcontainers/Pact; equivalent tooling needs a clear justification. |
| Required — missing | BDD acceptance scenarios (§12, p9) | Browser checks exist, no formal BDD suite. | Executable Given/When/Then scenarios for main user stories and failure paths, with CI results. |
| Required — missing | Performance/load at required rate, p95/p99/lag and **one soak test** (§12, p9) | Only two 15-second custom stages; no soak or percentile report. | Run/document meaningful duration and required rate; save raw results, environment and graphs. |
| Required — missing | **SAST, DAST, dependency and image scans**, OWASP controls (§11–12, p9) | No saved scanner campaign or reports. Ruff is not this evidence. | Configure scans, triage findings, fix material issues and attach actual reports. |
| Required — missing | Audit/erasure compliance checks and **kill a broker/pod** (§12, p9) | Replay/sink/stale-sample tests cover different failures. | Real fault injection and recovery accounting; audit and erasure tests. |
| Required — partial | **All suites automatically in CI on every push**, pipeline link (§12–13, p9) | CI has Ruff, pytest with opt-in integrations skipped, and frontend build. | Add browser/BDD, integrations, security, coverage and required performance/chaos jobs; provide accessible final-run evidence. |
| Required — partial | Relational core in **3NF**, explicit denormalization (§8, p7; §13, p9) | Fleet/vehicle separation exists; repeated OEM/model catalog attributes are a disclosed shortcut. | Normalize dependencies or document a justified deliberate denormalization acceptable to the reviewers; diagram must match SQL. |
| Template requirement — partial | **Three SQL before/after comparisons** (§5.3 template; PDF §8, p7) | One comparison only. Saved plans are `EXPLAIN indexes = 1` plus real execution stats, not `EXPLAIN ANALYZE`. | Measure two further real queries with equal results and plans/timings; explain/confirm the ClickHouse equivalent. Candidate workloads: fleet idling and event activity. |
| Expected — partial | Centralized logs, metrics and traces (§7, p7) | Metrics work; logs are local/container logs; distributed tracing absent. | Central log aggregation and instrumented traces, plus troubleshooting evidence. |
| Expected — partial | Hot/warm/cold retention and **cost estimate** (§10, p8) | Retention/volume arithmetic exists; no monetary storage/compute estimate; archive maintenance manual. | Identify deployment assumptions and cost basis; document and verify archive maintenance/retention. |
| Expected — not proven | Analytics over billions of rows (§7, p7) | Historical queries work on local data; no billion-row evidence. | Dataset/scale experiment appropriate to required scope, with actual results and limits. |
| Scope clarification | ML/vector layer and agentic AI (§7–8, pp7–8) | No model, vector store or agent. Minimum bar says vector storage “where useful” (p6), but later expectations list them. | Confirm a rule-based non-AI scope is acceptable; otherwise add an evaluated model/agent with relevant storage, guardrails and audit. Do not silently label these fulfilled. |

Algorithms such as graphs, dynamic programming, Bloom filters and real VIN check digits are **examples**, not a requirement to implement every one. Use algorithms appropriate to the chosen fleet/idling problem and justify complexity. Synthetic VIN validation is implemented; real OEM VIN decoding is not claimed. Likewise, the opportunity list does not require building every listed product.

## Practical order

1. **Confirm scope/deadline with the organizer.** The gap between a laptop prototype and the PDF's production bar is substantial, particularly 100K/sec, HA, cloud/IaC and security. Get explicit acceptance for any reduced scope; documentation alone cannot close it.
2. **Finish evidence deliverables that correspond to existing work:** final test run, measured coverage, two additional real SQL comparisons, CI run link, accessible artifacts and an updated evidence record. Add missing implementation where a test reveals an actual gap.
3. **Complete required engineering work according to that confirmed scope:** CI/scans/contracts/BDD, identity/privacy/rate limits, deployment/IaC, scale/latency/soak/fault recovery and observability.
4. **Rehearse and record** only a healthy, fresh stream. The last archive verification excluded a pre-existing restarting live processor; it does not prove the live demo is healthy today. Check Redis memory, changing telemetry and native QueryFlux counters.
5. **Finalize team details, actual video timestamps, document/PDF, repository permissions and pre-deadline tag**, then submit.

No new dependency installation, cloud resources, test campaign, code implementation, tag, push or upload is implied by this checklist.
