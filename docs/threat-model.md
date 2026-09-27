# Lightweight threat model (STRIDE)

Scope: synthetic telemetry on a local laptop. This is not a penetration-tested or compliance-certified deployment.

| Threat | Category | Implemented mitigation | Remaining work |
|---|---|---|---|
| Spoofed telemetry producer | Spoofing | Broker host port bound to loopback; schema validation | Kafka SASL/mTLS, producer identities, per-fleet ACLs; master-data identity matching |
| Tampered telemetry | Tampering | Strict schema, physical bounds, event-time checks | Signed payloads, transport TLS, plausibility checks across sources |
| Undeniable event provenance | Repudiation | Event IDs, sequences, persisted history and error logs | Immutable audit log and verified producer identity |
| Unauthenticated API access | Spoofing / disclosure | Random local API key, constant-time comparison, protected /api routes | OAuth2/OIDC + JWT + RBAC; key rotation and managed secrets |
| Cross-fleet data exposure | Disclosure / elevation | Input shape validation and parameterized metadata SQL | Current key is a single demo operator with access to all fleets; NO tenant isolation claim |
| SQL injection | Tampering | No arbitrary SQL endpoint; metadata parameters; bounded integer and anchored identifier validators; fixed analytical SELECT templates | Dedicated read-only analytical credentials and authorization policy |
| Secret leakage | Disclosure | .env ignored, mode 0600 generation, no key in built frontend; browser session storage; no committed credentials | TLS, secret manager, hardened browser session lifecycle |
| Duplicate/replayed events | Tampering / denial of service | Redis dedup TTL, bounded batch set, analytical FINAL views, producer idempotence | Dedup TTL is finite; global exactly-once is not provided |
| Expensive analytical requests | Denial of service | Four running queries, sixteen waiters, admission timeout, row/time limits | Per-identity rate limiting and production workload quotas |
| Unbounded generation | Denial of service | Bounded Kafka queue, producer blocking, bounded recovery buffers | Capacity alarms, retention monitoring, horizontal workers |
| Malicious nextUri | Disclosure | QueryFlux client validates origin before polling/cancelling | TLS and proxy allow-list configuration for a remote deployment |
| Service compromise | Elevation | Application UID 10001; unprivileged frontend; loopback published ports | Full image hardening, vulnerability triage, network policies, separate DB roles |

CORS permits explicitly configured browser origins. It is not authentication. /health exposes dependency health without a key; /docs exposes the API schema. Redis and ClickHouse use local network trust; credentials and TLS for those services are not implemented. QueryFlux uses a generated static user and random admin password. Native QueryFlux binds all interfaces in the inspected version, so keep it on a trusted development host; the Compose route should publish only loopback.

No JWT, OIDC provider, RBAC, fleet authorization, generalized API rate limiter, encrypted storage, privacy compliance certification, or availability SLA is claimed. All data is synthetic. A production recommendation is OAuth2/OIDC + JWT + RBAC + tenant isolation, Kafka authentication, service TLS, read-only analytic users, and verified operational controls.
