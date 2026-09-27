# External components and AI declaration

ValeoSense implements simulation, processing rules, storage integration, APIs, dashboard, tests, and submission tooling. QueryFlux is an **existing external project**, not code authored or copied into ValeoSense. Redpanda and Redis server licensing is recorded separately from permissively licensed components; this document does not label the entire stack as permissive open source.

License checks were made against installed package license files, the local QueryFlux LICENSE, the exact ClickHouse image's bundled LICENSE, and upstream versioned license files on 2026-09-27. The Python lock and npm lock record actual resolved dependencies. This is a major-component declaration, not a complete transitive SBOM or legal certification.

| Component | Use | Confirmed license / evidence |
|---|---|---|
| [QueryFlux](https://github.com/lakeops-org/queryflux) | External analytical query router, Trino HTTP -> native ClickHouse | Apache-2.0; local upstream LICENSE at inspected checkout `5d06d83c7552208eff09a7bbfae4c57944338030`, version file `0.3.0` |
| Redpanda v25.1.9 | Kafka-compatible streaming broker | BSL-1.1 source-available; [versioned license](https://github.com/redpanda-data/redpanda/blob/v25.1.9/licenses/bsl.md) |
| Redis server 7.4 | Latest state, dedup and active alerts | RSALv2 or SSPLv1; [7.4 license](https://github.com/redis/redis/blob/7.4.0/LICENSE.txt); do not confuse with redis-py's license |
| PostgreSQL 17 | Relational metadata | PostgreSQL license; [upstream COPYRIGHT](https://raw.githubusercontent.com/postgres/postgres/REL_17_STABLE/COPYRIGHT) |
| ClickHouse 25.8 | Batched analytical storage | Apache-2.0; `/usr/share/doc/clickhouse-common-static/LICENSE` and `/usr/share/doc/clickhouse-server/LICENSE` inside the running image |
| FastAPI 0.141.1 | HTTP API | MIT; installed distribution `licenses/LICENSE` |
| Pydantic 2.13.5 | Canonical validation | MIT; installed distribution `licenses/LICENSE` |
| Uvicorn 0.54.0 | ASGI server | BSD-3-Clause; installed `licenses/LICENSE.md` |
| redis-py 8.1.0 | Python Redis client | MIT; installed `licenses/LICENSE` |
| confluent-kafka 2.15.1 | Python Kafka client | Apache-2.0 for Python source; bundled native components have their own notices in installed license files |
| Psycopg 3.3.6 | PostgreSQL access | LGPL-3.0-only; installed `licenses/LICENSE.txt`; binary distribution includes other component notices |
| HTTPX 0.28.1 | ClickHouse and QueryFlux HTTP clients | BSD-3-Clause; installed `licenses/LICENSE.md` |
| python-dotenv 1.2.3 | Local environment loading | BSD-3-Clause; installed `licenses/LICENSE` |
| React / React DOM | Dashboard | MIT; `frontend/node_modules/react/LICENSE` and react-dom LICENSE |
| Vite | Frontend build/dev tooling | MIT for core; `frontend/node_modules/vite/LICENSE.md` includes bundled notices |
| Playwright | Browser verification using installed Chromium | Apache-2.0; installed `@playwright/test/LICENSE` |
| pytest / Ruff | Testing / lint and formatting | MIT; installed distribution license files |
| psutil | Benchmark process CPU and memory sampling | BSD-3-Clause; installed LICENSE |
| Grafana OSS 12.4.1 (optional) | Provisioned operational dashboard | AGPL-3.0; `/usr/share/grafana/LICENSE` inspected in the running image |
| Prometheus 3.13.3 (optional) | Metrics scraping and retention | Apache-2.0; [versioned LICENSE](https://github.com/prometheus/prometheus/blob/v3.13.3/LICENSE) |

Python, Node.js, Nginx, Chromium, base operating-system images, and their transitive packages retain their upstream licenses. The project does not relicense those distributions. No enterprise Redpanda features, hosted paid services, or commercial SaaS integrations are claimed. Review the version-specific terms before distributing or offering this stack as a service.

## AI tools used

Codex was used for coding assistance, debugging, test development, and documentation assistance. AI-generated architecture decisions were not externally validated. Tests, actual service responses, actual plans, and recorded benchmark files provide the verification evidence. No ML model is required for the current solution. No generated screenshot, benchmark, customer validation, or fictional integration is included as evidence.
