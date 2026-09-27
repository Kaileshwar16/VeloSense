# Five-minute demo

Before recording: run the full stack, confirm all checks in [verification.md](verification.md), open http://localhost:3000, enter the local API_KEY without showing it in the video, and start `make simulator`. Leave the stream running at least 30 seconds before showing idling. Keep a second terminal ready with test and benchmark evidence. Read [queryflux.md](queryflux.md) for the verified route setup.

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Fleet registry card; title | “ValeoSense: real-time intelligence for massive connected-vehicle streams. We generated exactly 100,000 synthetic vehicles. The demo actively samples 1,000.” |
| 0:30–1:00 | Architecture diagram | “Kafka buffers ingestion; Redis serves current state; PostgreSQL holds identities; ClickHouse stores telemetry. Live reads are separated from analytical scans.” |
| 1:00–2:00 | Live feed, active alerts, measured events/sec | “Speed, location, energy and distance evolve statefully. These alerts are calculated from telemetry, not copied from labels. Idle duration persists across events.” |
| 2:00–2:30 | V000001 history and idle estimate | “Idling begins after more than 20 seconds for this demo. Cost is explicitly an ICE estimate at 0.8 L/h and INR 100/L; EV fuel cost is zero.” |
| 2:30–3:15 | Analytics and query panel | “This successful analytical response went through the existing QueryFlux component into ClickHouse. The panel shows the actual route and measured request latency. We connect one engine; multi-engine routing is future work.” |
| 3:15–3:50 | `artifacts/tests.txt`, duplicate test, lag/duplicate counters | “The real integration test sends a duplicate through Kafka. It does not create a second historical event or incident. We also simulate reordering and network recovery with bounded buffers.” |
| 3:50–4:25 | `docs/benchmark.md` | “The 1K target was stable. The generator hit nearly 10K/sec, but the single processor fell behind. We measured and reported that limit, then stopped higher load targets.” |
| 4:25–4:45 | `docs/sql-optimization.md` | “The same result required 226,112 rows read before the indexed predicate, versus 2,048 after in this captured run. These are actual ClickHouse plans.” |
| 4:45–5:00 | Architecture and future list | “Next: partition-owned workers, authenticated multi-tenant access, Parquet archive, and later Iceberg. No Kubernetes or invented ML is needed to demonstrate the core.” |

If QueryFlux is unavailable on the recording machine, explicitly use `direct` mode and say so. Never present a saved response as a live query. The generated browser screenshots are actual captures and have their capture metadata alongside them; re-capture after significant UI changes. A demo video has not been automatically recorded or uploaded; add the final video URL to the solution document after recording.
