# Run the ValeoSense demo

This guide covers setup, starting the synthetic vehicle stream, opening the dashboard, and stopping the demo. Run commands from the repository root, where `Makefile` lives.

## 1. Check prerequisites

You need Python 3.11+, Node.js 22+, npm, Make, and a running Docker engine with Docker Compose 2.24+. Initial setup and container builds download dependencies and images.

```bash
python3 --version
node --version
npm --version
make --version
docker info
docker compose version
```

On this machine, the project is at:

```bash
cd /home/kailesh/projects/VeloSense
```

On another machine, use your checkout's directory instead.

## 2. Set up once

```bash
make setup
```

This creates `.env` with random local credentials if it does not exist, creates the Python virtual environment, installs Python and frontend dependencies, and generates the local QueryFlux configuration. An existing `.env` is preserved.

Open `.env` in your editor and find `API_KEY`. You will enter its value in the dashboard. Keep the key out of screenshots and recordings.

If this checkout is already set up, skip to the next step.

## 3. Start one demo mode

### Recommended demo: QueryFlux with ClickHouse and DuckDB

```bash
docker compose up --build -d
```

This root Compose command starts the simulator and automatically initializes both
engines. ClickHouse serves fleet-wide history; DuckDB queries a bounded recent
Parquet snapshot refreshed from ClickHouse. No manual DuckDB setup is needed.
For Docker-only setup, `python3 scripts/setup_env.py` creates `.env` without
installing the host development dependencies.

### Original demo: direct ClickHouse analytics

```bash
ANALYTICS_ROUTE=direct make demo
```

The explicit route overrides any previous QueryFlux setting. This starts the data services, metadata seed job, API, processor, dashboard, and continuous simulator in containers.

### Existing Make shortcut: both QueryFlux engines

Use this instead of the standard command when demonstrating QueryFlux:

```bash
make demo-queryflux
```

This is another way to start the two-engine demo. Analytical requests go through QueryFlux to ClickHouse or DuckDB according to the sample-namespace rule. Live vehicle state still comes from Redis and vehicle metadata from PostgreSQL.

All demo modes register **100,000 synthetic vehicles** and configure the simulator to sample **1,000 active vehicles** at a target of **1,000 readings per second**. Actual throughput depends on your machine and service health.

**All demo commands already start the simulator. Do not also run `make simulator`.** Allow at least 30 seconds after the processor starts receiving current telemetry before demonstrating idling alerts.

## 4. Check readiness and sign in

```bash
docker compose --env-file .env -f infra/docker-compose.yml ps -a
curl --fail --show-error http://localhost:8000/health
```

The health endpoint should return:

```json
{"status":"ok","services":{"redis":"ok","postgres":"ok","clickhouse":"ok"}}
```

The seed job finishing with `Exited (0)` is expected. The backend and frontend should be running; the processor should not be repeatedly restarting.

Open **[http://localhost:3000](http://localhost:3000)**, enter `API_KEY` from `.env`, and select **Open fleet overview**.

Before presenting, check that:

- Registered vehicles shows `1,00,000`.
- The stream badge changes to **Stream connected** and current telemetry appears.
- Online vehicles and measured events per second update.
- Historical analytics finish loading without an error banner.
- In QueryFlux mode, the successful analytical query card shows route `queryflux` and engine `clickhouse` when `DEBUG=true`.

The health endpoint checks Redis, PostgreSQL, and ClickHouse. It does **not** prove that the processor, simulator, or QueryFlux route is working; use the dashboard and logs to confirm those separately.

## 5. Walk through the dashboard

1. **Overview:** explain the difference between the registered fleet and actively reporting vehicles.
2. **Live vehicles:** show speed, fuel or battery level, status, and last-seen time. Use Next/Previous to change pages.
3. **Vehicle history:** click a vehicle ID to open its most recent events. Close with the close button or Escape.
4. **Active alerts:** show detections as they arrive. An empty list can be valid; alerts depend on current telemetry.
5. **Analytics:** show telemetry activity and idling estimates. Idling fuel cost excludes EVs and uses the assumptions displayed on the panel.
6. **A closer look:** enter `V000001,V000002` and 15 minutes, then select **Analyse sample**. The result shows QueryFlux → DuckDB and the snapshot scope. This is a bounded sample, not complete history.
7. **Infrastructure:** show the configured analytics path, response metadata, and query counters.

The dashboard refreshes panels independently. **Refresh data** requests an immediate update; **Retry now** retries after a connection failure.

For presentation timing and narration, see [the five-minute demo script](docs/demo-script.md). Use its QueryFlux narration only when running the routed mode.

## 6. Optional Grafana monitoring

With the core demo running:

```bash
make monitoring
EXPECT_QUERYFLUX=1 make monitoring-test
```

Run `make verify-dual-engine` first so both native engine counters have samples.
For direct mode, use `make monitoring-test` without `EXPECT_QUERYFLUX=1`.

Open **[http://localhost:3001](http://localhost:3001/d/valeosense-overview)**. The username is `admin`; on initial setup the password is `GRAFANA_ADMIN_PASSWORD` if configured, otherwise `API_KEY`. An existing Grafana volume retains its previously configured credentials.

Stop only the monitoring services with:

```bash
make monitoring-down
```

See [the monitoring guide](docs/monitoring.md) for details.

## 7. Troubleshoot before presenting

### Dashboard cannot fetch data

```bash
docker compose --env-file .env -f infra/docker-compose.yml ps -a
docker compose --env-file .env -f infra/docker-compose.yml logs --tail 60 backend frontend
curl --fail --show-error http://localhost:8000/health
```

If services are stopped, rerun your chosen demo command from step 3. If the API key is rejected, select **Update API key** and enter the value from the current `.env`. For analytics-only errors in QueryFlux mode, also inspect:

```bash
docker compose --env-file .env -f infra/docker-compose.yml logs --tail 60 queryflux
```

QueryFlux failures do not silently fall back to direct analytics. To deliberately switch to direct mode, use `ANALYTICS_ROUTE=direct make demo`.

### Recent sample fails while historical panels work

```bash
docker compose logs --tail 60 duckdb-sync queryflux
```

Snapshots older than `DUCKDB_MAX_AGE_SECONDS` (120 by default) fail with HTTP 503.
Restore snapshot refresh and retry; historical ClickHouse queries remain available
if QueryFlux and ClickHouse are healthy. The sample is capped at 20,000 rows from
the first 100 vehicles by default. Empty sample results can be valid.

### Dashboard loads but says “Awaiting stream”

```bash
docker compose --env-file .env -f infra/docker-compose.yml logs --tail 60 processor simulator
docker compose --env-file .env -f infra/docker-compose.yml exec -T redis redis-cli INFO memory
```

**Known issue observed on 2026-09-28:** Redis reached its configured 256 MB limit and the processor restarted with `OutOfMemoryError`. API requests and historical analytics still worked, but fresh telemetry was stalled. A working dashboard alone does not resolve this issue.

If you see that error, stop additional simulated traffic while investigating:

```bash
docker compose --env-file .env -f infra/docker-compose.yml stop simulator
```

The current configuration retains event deduplication markers for 24 hours and uses Redis `noeviction`. Capacity and retention need to be addressed before a sustained run; restarting containers alone does not clear persisted memory pressure. Stopping the simulator also does not remove an existing Kafka backlog. Do not delete volumes or flush Redis just to make the dashboard look healthy.

After resolving the processor issue, rerun your chosen demo command and verify fresh telemetry before presenting.

## 8. Optional verification

```bash
make test
make frontend-build
make verify-dual-engine
make integration-queryflux
EXPECT_QUERYFLUX=1 make browser-test
```

`make integration-queryflux` runs both the real Kafka ingestion regression and a
three-event snapshot lineage check inside the backend container. It inserts
explicit synthetic fixtures. `make verify-dual-engine` uses existing streamed
readings and native QueryFlux counters without adding fixtures. Both require the
routed demo and `DEBUG=true`.

`make browser-test` requires the running stack, local `.env`, and an installed Chromium browser. It defaults to `/usr/bin/chromium`; set `CHROMIUM_PATH` if yours is elsewhere. It checks login, history, pagination, panel loading, mobile overflow, and (with `EXPECT_QUERYFLUX=1`) a real DuckDB query, and saves:

- `artifacts/dashboard-desktop.png`
- `artifacts/dashboard-mobile.png`
- `artifacts/browser-smoke.json`

The browser report records stream status separately; passing dashboard checks does not prove a healthy live stream.

## 9. Optional Iceberg archive

```bash
make iceberg                 # independent Kafka consumer, catalog and persistent files
make iceberg-status          # snapshot IDs, row count and archived offset boundaries
make iceberg-integration     # real isolated-topic restart/read test
```

The archive begins at the oldest Kafka records still retained. It stores raw
telemetry and malformed messages independently of live processing, using daily
Iceberg/Parquet partitions and the PostgreSQL catalog. Follow the
[Iceberg guide](docs/iceberg.md) for queries, snapshot reads and recovery limits.
Use `make iceberg-down` to stop only this worker.

## 10. Stop the demo

Stop just the simulator to keep the dashboard available for historical data:

```bash
docker compose --env-file .env -f infra/docker-compose.yml stop simulator
```

Stop and remove all project containers, including optional profiles:

```bash
make down
```

`make down` preserves database, monitoring and Iceberg volumes. Start again using the same demo command from step 3; setup is only needed if dependencies or generated configuration are missing.
