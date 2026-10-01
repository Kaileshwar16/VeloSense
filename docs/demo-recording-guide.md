# ValeoSense demo recording guide

Target final length: **4 minutes 50 seconds**. The supplied submission template cuts videos at 5:00. Record at 1080p with clear microphone audio; captions are recommended.

Use the exact screen actions and narration below. Replace `[team name]` with your real team name. The times are editing targets; enter the actual timestamps from your finished video in the solution document.

## 1. Prepare before recording

Run all terminal commands from this directory:

```bash
cd /home/kailesh/projects/VeloSense
```

This guide assumes Docker is running and the checkout is already configured. If `.env` does not exist, follow [the setup guide](../RUN_PROJECT.md) first. Initial builds can download images and dependencies; finish them before recording.

1. Open `.env` privately in your editor. Confirm `DEBUG=true`, which exposes analytical response metadata. Find `API_KEY` for dashboard login.
2. Start the complete two-engine demo:

   ```bash
   docker compose up --build -d
   docker compose ps -a
   curl --fail --show-error http://localhost:8000/health
   ```

   The health response should have `status: "ok"` and Redis, PostgreSQL and ClickHouse all `ok`. A completed seed container with exit code 0 is normal. The processor must not be repeatedly restarting.

3. Open **http://localhost:3000**. Enter the key and click **Open fleet overview** before recording. Close the `.env` editor tab.
4. Wait at least 30 seconds after fresh telemetry begins. Check **Stream connected**, advancing last-seen times, a nonzero measured **Events / second**, and populated history. Health alone does not prove that telemetry is flowing.
5. Check Redis capacity before a rehearsal:

   ```bash
   docker compose exec -T redis redis-cli INFO memory
   docker compose logs --tail 40 processor
   ```

   Compare `used_memory` with `maxmemory`. This demo has a 256 MiB Redis limit and retains deduplication markers for 24 hours. If memory is close to the limit or logs show `OutOfMemoryError`, use the troubleshooting section before recording. A restart does not remove the retained data.
6. Verify both analytical engines using the running stream:

   ```bash
   make verify-dual-engine
   ```

   Proceed when the JSON reports `"passed": true`, both engine entries in `native_success_count_delta` are greater than zero, and the sample contains readings. Values need not be exactly 1 because other dashboard queries can run concurrently. This verifies native engine counters as well as API responses.
7. In the dashboard, click **Analytics**, then scroll to **A closer look**. Use vehicle IDs `V000001,V000002`, time window `15`, and click **Analyse sample ↗**. Confirm rows appear and the note says `QueryFlux → duckdb` with snapshot scope. Click **Infrastructure** and confirm the query card shows route `queryflux` and engine `clickhouse`.

The startup command already starts the simulator. Do not also run `make simulator`, and do not run a benchmark alongside the demo stream.

## 2. Prepare the windows and evidence clip

Arrange these windows before recording so switching takes only a second:

| Window | Open and prepare |
|---|---|
| Browser | Dashboard at `http://localhost:3000`, signed in, scrolled to Overview, first vehicle page |
| Architecture | Rendered Markdown preview of the Architecture section in `README.md`; confirm the diagram is visible, including DuckDB |
| Terminal | Repository root, readable font, no credentials or unrelated command history visible |
| Benchmark | Markdown preview of `docs/benchmark.md`, with measurement date and table visible |
| SQL evidence | `docs/sql-optimization.md`, with the before/after timings and row counts ready to show |

If your Markdown preview does not render Mermaid, prepare a rendered architecture view before recording. Do not spend video time debugging the preview.

Use your screen recorder to make a separate, real duplicate/replay test clip. Capture the terminal while running:

```bash
docker compose exec -T -e RUN_INTEGRATION=1 -e EXPECT_QUERYFLUX=1 backend \
  python -m pytest -v tests/integration/test_stack.py
```

Wait for `test_real_wire_path_idling_dedup_and_history PASSED` and `1 passed`. Keep the command, test name and result readable. If it fails or skips, fix the problem before using this segment.

This test publishes 25 idling readings for synthetic vehicle `V100000` plus one repeated payload through real Kafka. It checks persisted live state, one incident and one copy of the repeated event in the analytical read view. It then inserts a repeated stored row into ClickHouse to simulate analytical sink replay and checks deduplicated history again. It uses synthetic fixtures and real services, not mocked storage.

Trim waiting time in the clip if necessary and label it **“Recorded integration check — waiting time shortened”**. Use this clip in the 3:20–3:50 segment below. Keep the full original recording locally. Do not describe this as a broker-crash recovery test or an exactly-once guarantee.

Before the main recording, rehearse the dashboard clicks once. Ensure `V000001` has history and at least one visible alert is available. Clear the sample result by reloading the dashboard if you want the on-camera click to visibly load a new result; login persists in the same browser tab.

## 3. Record this exact sequence

### 0:00–0:25 — Problem and fleet scale

**Screen actions:** Start on **Overview**. Keep the title, **Registered vehicles**, **Online vehicles**, **Events / second** and **Active alerts** cards visible. Let the dashboard refresh while speaking.

**Say:**

> “We are [team name], and this is ValeoSense. Fleet managers need to see current vehicle incidents and investigate their history while telemetry keeps arriving. Our prototype has 100,000 synthetic registered vehicles. This demo samples 1,000 active vehicles, and this card shows the measured processing rate.”

Point to the current displayed rate. Do not promise it will read exactly 1,000.

### 0:25–0:50 — Solution and architecture

**Screen actions:** Switch to the rendered architecture diagram. Trace simulator → Redpanda → processor, then Redis and ClickHouse. Point to PostgreSQL and QueryFlux's two engines.

**Say:**

> “Stateful telemetry flows through Kafka-compatible Redpanda into our processor. Redis serves current state, PostgreSQL holds vehicle metadata, and ClickHouse stores history. The existing QueryFlux component routes analytical queries to ClickHouse or a bounded DuckDB sample. This separates live reads from historical analysis.”

### 0:50–1:25 — Live vehicles and a real incident

**Screen actions:** Return to the dashboard. Click **Live vehicles**. Point to changing last-seen times, speed, energy and status. Click **Next →**, show the next page briefly, then **← Previous**. Click **Active alerts** and point to an actual visible incident; use an idling alert if available.

**Say:**

> “These readings come through the running pipeline. We can inspect speed, fuel or battery level, current status and the last reported time, and move through the fleet. Here is a detected incident. The processor derives alerts from telemetry and state across readings, rather than copying the simulator's scenario label.”

Name the incident and vehicle actually displayed. If it is an idling alert, point out its duration as it updates. Do not narrate a fault or speeding event that is not visible.

### 1:25–1:50 — Vehicle history

**Screen actions:** Click **Live vehicles**, then click the first-page `V000001` vehicle button. Wait for the history dialog to load. Point to timestamps, speeds and the `queryflux · clickhouse` execution note. Close with **✕** or Escape.

**Say:**

> “Opening a vehicle shows its latest twelve readings from the last day. This is persisted history served through QueryFlux and ClickHouse. We can move from the fleet view into the readings behind an incident.”

### 1:50–2:15 — Activity and idling estimates

**Screen actions:** Click **Analytics**. Show **Telemetry activity** and **Idling insights**. Point to the assumptions under the idling panel.

**Say:**

> “Activity is grouped from stored telemetry. Idling insights help identify vehicles for investigation. The displayed cost assumes 0.8 litres per hour at 100 rupees per litre for combustion vehicles, with EV fuel cost excluded. It is an estimate for the top vehicles, not measured savings or a complete fleet fuel bill.”

Read the assumptions displayed on your instance if they differ from these defaults.

### 2:15–2:50 — Execute the DuckDB query

**Screen actions:** Scroll to **A closer look**. Show vehicle IDs `V000001,V000002` and **Last minutes** `15`. Click **Analyse sample ↗** on camera. Wait for rows. Point to the reading counts, average speeds, `QueryFlux → duckdb` note and snapshot limits.

**Say:**

> “For a small selection, we run this recent-sample query through QueryFlux into DuckDB. The sample is periodically exported from canonical ClickHouse data. The panel discloses its freshness and size limits. Routing uses an explicit namespace rule, and this sample is not complete vehicle history.”

### 2:50–3:20 — Show routing and independent engine verification

**Screen actions:** Click **Infrastructure**. Show **ANALYTICS QueryFlux → ClickHouse + DuckDB** and the query card's `queryflux` / `clickhouse` values. Switch to the terminal and run:

```bash
make verify-dual-engine
```

At the bottom of the JSON output, highlight `native_success_count_delta`, its positive `ClickHouse` and `DuckDb` values, and `"passed": true`.

**Say:**

> “The fleet query uses ClickHouse, while the small sample uses DuckDB. This verification makes real API requests and checks QueryFlux's native success counters. Both engine counters advanced, providing independent evidence beyond the route labels in the dashboard.”

If the command takes longer than this slot, capture it as a separate clip and shorten only waiting time with a visible label. Use its actual result.

### 3:20–3:50 — Demonstrate duplicate and replay handling

**Screen actions:** Insert the recorded integration-test clip from section 2. Show the command, named test and passing result.

**Say:**

> “This recorded check deliberately sends a duplicate through real Kafka. It verifies one historical event and one idling incident for the repeated reading. It also reinserts an analytical row to simulate sink replay and verifies deduplicated history. This demonstrates the tested replay behavior; we do not claim exactly-once transactions across stores.”

### 3:50–4:15 — Honest benchmark results

**Screen actions:** Show the measurement date and table in `docs/benchmark.md`. Point to the 1K row, then the 10K row and its `False` stability result.

**Say:**

> “These are saved measurements from September 27, not a benchmark running during this video. The short 1K target was stable at about 1,000 generated readings per second. At 10K, the processor fell behind and needed 24.53 seconds to drain, so that stage failed stability. We stopped higher targets. A 100,000-vehicle registry is not a 100,000-events-per-second claim.”

### 4:15–4:35 — One measured SQL optimization

**Screen actions:** Show the before and after evidence in `docs/sql-optimization.md`. Point to the `substring(vehicle_id, 2)` predicate versus direct `vehicle_id` equality, then the recorded timings and row counts. Use two short screen cuts if they do not fit together at a readable size.

**Say:**

> “For the same historical lookup result, changing the predicate to use the leading ordering key reduced rows read from 515,271 to 4,096. Median execution in that saved comparison fell from about 23.7 to 2.4 milliseconds. That is evidence for this query, not a universal speedup.”

### 4:35–4:50 — Close on the working product

**Screen actions:** Return to **Overview** with current readings visible. Add a small title with the real team name if desired.

**Say:**

> “ValeoSense demonstrates the path from synthetic telemetry to live incidents and historical investigation. Next are partition-owned workers, stronger tenant security and archival. QueryFlux is an existing external dependency; our contribution is the simulator, processing, integration and dashboard. Thank you.”

Stop recording by 4:50 so there is room for small timing differences.

## 4. Optional Grafana substitution

Grafana is optional. If you want it in the video, use it within the 2:50–3:20 segment rather than extending the total duration. Keep the native-engine verification result available.

Before recording, run:

```bash
make monitoring
make verify-dual-engine
EXPECT_QUERYFLUX=1 make monitoring-test
```

Open **http://localhost:3001/d/valeosense-overview?from=now-15m&to=now**. Sign in off camera as `admin`, using the configured Grafana password; on initial setup it defaults to `API_KEY` unless overridden. Existing volumes retain their original credentials.

Find **QueryFlux completed queries by engine** and confirm both engine series are visible. You can also briefly show **Pipeline throughput** and **Kafka consumer lag**. Rates need several scrapes and real query activity; finish that preparation before recording. These panels show measured counters/rates, not proof of sustained 100K/sec capacity.

## 5. If something fails during rehearsal

| Symptom | What to do before recording again |
|---|---|
| Login rejected | Use **Update API key** and the current local `.env` value off camera. |
| **Awaiting stream**, frozen timestamps or processor restarts | Run `docker compose logs --tail 60 processor simulator` and check Redis memory. Do not use API health alone as proof of an active stream. |
| Redis OOM or almost full | Run `docker compose stop simulator` to stop adding traffic. Resolve capacity/retention before resuming; existing backlog can still consume memory. Follow [the run guide](../RUN_PROJECT.md). Do not flush Redis or remove volumes for the recording. |
| DuckDB sample empty | Check that the requested vehicles have current readings, allow a snapshot refresh, and retry **Analyse sample ↗**. |
| DuckDB sample errors | Inspect `docker compose logs --tail 60 duckdb-sync queryflux`. Restore freshness and rerun verification; do not present an old sample as a live success. |
| No visible alert | Wait for fresh telemetry and detector continuity; check the processor. Choose an actual visible alert rather than inventing one. |
| Test fails or skips | Keep the result out of the success narration; fix the failing prerequisite and record a new run. |

Do not switch to direct mode and retain the two-engine narration. This recording plan requires the routed demo to work.

## 6. Finish and hand off

1. Watch the exported video from start to finish. Confirm duration is at most **5:00**, text is readable, audio is clear, and `.env`, API keys and passwords never appear.
2. Check that the duplicate/replay clip is identified as recorded and shortened waits are disclosed. The benchmark and SQL numbers must be described as saved measurements.
3. Upload the video to the submission-supported service, such as unlisted YouTube, Vimeo or a shareable Drive link. Test reviewer access in a signed-out browser.
4. Put the final URL and actual feature timestamps in `docs/solution-document.md`. Use the finished recording's times, not this guide's planned times. Only mark features as shown when the video actually demonstrates them.
5. Stop the producer after recording to avoid unnecessary Redis growth:

   ```bash
   docker compose stop simulator
   ```

   Historical views remain available. Stream status and sample freshness will age, which is expected. To stop the complete stack while keeping its data volumes, use `make down`.

This guide is a local preparation document. Creating it does not record or upload a video, rerun validation, or stage/commit any files.
