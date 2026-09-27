# Architecture actually implemented

ValeoSense separates live state, relational metadata, and analytical history. It is a single-machine demonstration of a streaming data platform, not a claim of production scalability at 100K events/sec. The registry contains 100,000 synthetic vehicles; the default demo actively samples 1,000 of them at approximately one reading per second.

See [architecture.mmd](architecture.mmd) and [er-diagram.mmd](er-diagram.mmd).

## Ingestion and streaming

`simulator/vehicle_factory.py` generates exactly 100,000 unique synthetic vehicle IDs and VINs using seed 42. OEM/model/fuel combinations are internally consistent. A supplied start timestamp plus seed makes simulator output deterministic; each normal run receives a fresh start timestamp so event IDs do not collide with prior runs.

`simulator/generator.py` holds lightweight state only for active vehicles. A single round-robin scheduler updates speed, heading, latitude/longitude, odometer, energy, and engine temperature. Time is logical event time paced against a monotonic clock. Duplicate publication preserves the entire payload. Out-of-order publication holds an actual event until the next one. Offline/recovery buffers release at most three records per vehicle tick, and flush remaining records at shutdown. All twelve requested scenarios are configurable through `--probabilities` JSON. Demo showcase scenarios are explicitly selected for the first eight vehicles.

`simulator/producer.py` uses librdkafka through confluent-kafka: 20ms linger, batched compression, idempotent producer, acks=all, 20,000-record / 32MiB queue caps, delivery callbacks, and a 35-second final flush. A full queue blocks generation and increments backpressure; 30 seconds of continuous blockage fails the run rather than silently dropping records. Kafka is keyed by vehicle_id. The topic has six partitions, one broker/replica, and a 24-hour / 256MiB-per-partition retention limit. These are laptop settings, not high availability.

## Processing and recovery

A single Python consumer owns state with a Redis lease. Multiple processor instances deliberately fail closed: horizontal processing is deferred. It consumes bounded 500-message batches and disables automatic offset commits. Pydantic validates the payload, UTC time, numeric bounds, DTC shape, and exclusive fuel/SOC representation. Invalid records increment a rejection counter and are skipped when the batch commits; there is no durable dead-letter queue yet.

The processor pipelines Redis reads for dedup markers and previous state, and uses an in-batch hash set for duplicates. Redis dedup markers use SET NX with a 24-hour TTL. Stale event-time readings are retained in analytical history but cannot change live state or trigger alerts. There is no arbitrary lateness reordering window; a late event does not repair prior idle integration.

Idling integrates consecutive engine-on readings at <=0.5 km/h. A gap over ten seconds resets continuity. An alert begins only after more than 20 seconds. A 5–10 minute threshold may be more appropriate in a real fleet. Braking/acceleration use delta-speed / delta-time in m/s²; default thresholds are -3 / +3. Speeding requires >100 km/h. Faults use DTC content, not the simulator's label. Alert episodes suppress repeated incidents, while active alerts update duration. Event labels in the activity chart describe synthetic scenarios; incident counts come from actual detectors.

History and new alerts are inserted into ClickHouse before a Redis transactional state/dedup update. Only after both succeed are Kafka offsets stored and synchronously committed. A failed sink stops the worker; Compose restarts it and Kafka replays uncommitted messages. ClickHouse uses deterministic event/alert keys and ReplacingMergeTree with FINAL read views to collapse replayed rows. This is practical prototype idempotency, **not mathematically perfect exactly-once processing**: two sinks do not share an atomic transaction, dedup expires, and Redis loss or altered replay payloads need stronger recovery design.

## Storage lifecycle

| Tier | Implemented store | Purpose and retention |
|---|---|---|
| Hot | Redis | Latest readings and alert state expire after 1 hour; online/active means event timestamp within 60 seconds; dedup expires after 24 hours |
| Metadata | PostgreSQL | 100 fleets and 100,000 vehicles; no raw telemetry; parameterized reads and COPY-based seed |
| Warm | ClickHouse | Raw validated telemetry and alert incidents; monthly partitions; vehicle/time/event ordering; 30-day TTL |
| Cold | Future | S3/MinIO Parquet export is not implemented; warm TTL currently deletes old data |

`alert_rules` is a small relational schema reserved for configuration, but detectors currently use environment/application settings; database-driven rules and rule editing are not implemented. No users, drivers, real owner information, or invented identities are stored.

## API, routing, and dashboard

FastAPI reads Redis and PostgreSQL directly. Analytical requests use an independent async semaphore (four running, sixteen waiting, five-second admission timeout) and bounded result limits. The route is explicit: `direct` or `queryflux`; failures return 503 and never silently claim QueryFlux success. There is no result cache. QueryFlux is an existing external Apache-licensed project, not ValeoSense code. Only ClickHouse is connected in this submission; multiple-engine routing is future work.

QueryFlux's Trino HTTP client polls bounded pages and checks pagination origins before forwarding credentials. ClickHouse read views encapsulate FINAL so cross-dialect translation cannot reinterpret it as an alias. Timestamps are explicitly serialized as UTC strings because raw timestamp values were observed as null on the tested QueryFlux wire path. Historical predicates qualify the source timestamp to avoid ClickHouse alias substitution.

The React dashboard polls every three seconds after the previous batch completes; requests do not overlap indefinitely. Failed panels lose their old values and show errors. Registered/online counts, measured consumption rate, active alerts, idle vehicles, estimated cost, live readings, history, activity, and routing are sourced from real API responses. No fake timeseries or throughput values are embedded in the UI.

## Observability and estimates

JSON metrics expose generated/published counts, backpressure, consumed/accepted/rejected/late/duplicate counts, incidents, committed Kafka lag, latest-batch event latency, process-local errors, API cumulative latency/requests, analytical execution latency, route counters, and concurrency gauges. Metrics have heartbeat timestamps; process restarts reset counters. API health checks Redis/PostgreSQL/ClickHouse; Kafka and processor freshness are separate metrics, and QueryFlux status is based on actual successful analytical requests.

Idling cost is an assumption: 0.8 litres/hour for ICE and INR 100/litre. EV fuel cost is zero; battery idle loss is not modeled financially. The card sums the top 20 idling vehicles for the selected seven-day view, not an unbounded fleet-wide bill. Large telemetry gaps are excluded from integration.

## CAP and workload trade-offs

Vehicle ownership, authorization, and configuration would prioritize stronger consistency. Metadata uses PostgreSQL transactions and foreign keys. Raw telemetry tolerates delayed delivery and eventual visibility across sinks; Kafka buffers while consumers fall behind, subject to its finite retention. Live requests do not queue behind analytical semaphores. There is no tested formal CAP guarantee, cross-region failover, or multi-node availability claim. Shared laptop CPU and memory still limit workload isolation.

## Algorithms and complexity

| Operation | Approach | Time / space |
|---|---|---|
| Registry generation | Seeded PRNG and sequential IDs | O(N) time, O(1) streamed CSV working space |
| Simulator update | Hash lookup + scalar physics | O(1) per reading; O(A) active state plus bounded O(A×B) buffers |
| Batch dedup | Hash set + Redis marker lookup | Expected O(1) per event; O(batch) transient space and O(rate×TTL) Redis markers |
| Stateful detectors | Prior reading + episode state | O(1) per event and O(active vehicles) retained state |
| Online/alert indexes | Redis sorted sets | O(log N) update; bounded paginated reads |
| History lookup | MergeTree ordering on vehicle/time | Sparse primary-index pruning; measured plans in sql-optimization.md |
| Admission control | Semaphore and bounded waiting count | O(1) bookkeeping per analytical request |

## Known scaling boundary

At the first 10K/sec test the producer met its target but the single processor fell behind. Backpressure is bounded at the producer, while broker lag is the measured buffer for a slower consumer. Broker retention, Redis memory, dedup TTL, and sink throughput require capacity planning. The 256MiB Redis cap with `noeviction` fails writes instead of silently discarding state; a long demo must be monitored. Replication, partition-owned consumer state, durable rejected-event storage, and archival are future work.
