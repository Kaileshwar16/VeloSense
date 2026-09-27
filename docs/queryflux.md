# QueryFlux integration and deployment

QueryFlux is an existing external component. ValeoSense's analytical path is
FastAPI → authenticated Trino HTTP → QueryFlux → native ClickHouse. Redis live
state and PostgreSQL metadata do not pass through QueryFlux. No multi-engine
routing or automatic fallback is implemented.

## Compose deployment

```bash
make up-queryflux
RUN_INTEGRATION=1 EXPECT_QUERYFLUX=1 .venv/bin/pytest tests/integration -q
```

The optional `queryflux` profile uses upstream image
`ghcr.io/lakeops-org/queryflux@sha256:1da899cddf3c95c41ac074d8dd6f3de59dd10050abc344fdd19528e874b4f2e3`.
The config generator creates ignored `artifacts/queryflux.compose.yaml` with
the local API key as the static user's password. Do not publish this file.
Internal connections and pagination use `http://queryflux:18080`; the host port
is `127.0.0.1:18081`. A direct host client cannot follow container-advertised
pagination URLs without a matching external-address configuration.

The image entrypoint runs the upstream binary through tini. The upstream Python
environment is explicitly selected with `PYTHONPATH`. ClickHouse is the only
configured engine, with four running and sixteen queued queries in the group.
The admin health endpoint is internal; its password comes from local configuration.

On 2026-09-27, the running image was healthy and the real Kafka/processor/API
integration test passed with `EXPECT_QUERYFLUX=1`, including a successful routed
history query, non-null UTC timestamp strings, and deduplicated history/alerts.
The original saved direct-mode suite is separate evidence; see [verification.md](verification.md).

For direct analytics again, run `make up`. This recreates the API with the default
direct route; it does not delete stored data. `make down` stops both profiles.

## Existing native build

The previously inspected native checkout was `/home/kailesh/work/queryflux` at
`5d06d83c7552208eff09a7bbfae4c57944338030`, with version file `0.3.0`.
This identifies the earlier native test, not the source revision of the image above.

```bash
make queryflux
# In another terminal, for a containerized backend using that host process:
QUERYFLUX_COMPOSE_URL=http://host.docker.internal:18080 make routed-api
```

`scripts/run_queryflux.sh` requires an existing upstream binary and libraries;
override `QUERYFLUX_REPO` / `QUERYFLUX_BINARY` if necessary. It generates ignored
`artifacts/queryflux.local.yaml` and runs the binary without editing upstream.
A local backend instead uses `ANALYTICS_ROUTE=queryflux make api` and the
`QUERYFLUX_URL` from `.env`. `QUERYFLUX_COMPOSE_URL` overrides only Compose routing.

## Behavior and limits

No QueryFlux outage is silently converted to a direct query. Dependency failures
return HTTP 503. Debug execution metadata reports the actual successful route
and wall latency. `/api/v1/system/routing` reports whether a routed query has
succeeded in the current backend process.

Read views encapsulate ClickHouse `FINAL`; analytical timestamps are explicitly
serialized to UTC strings to avoid the observed native wire-format null issue.
The client checks pagination origins, bounds row count and attempts cancellation
on failure. API input is validated and only fixed SELECT templates are available.
These measures do not imply arbitrary SQL access, query caching or engine failover.
