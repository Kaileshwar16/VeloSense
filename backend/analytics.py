import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.queryflux.client import QueryFluxClient
from shared.config import Settings


class Analytics:
    def __init__(self, settings: Settings):
        if settings.analytics_route not in ("direct", "queryflux"):
            raise ValueError("ANALYTICS_ROUTE must be direct or queryflux")
        self.settings = settings
        self.direct = httpx.AsyncClient(base_url=settings.clickhouse_url, timeout=25)
        self.queryflux = QueryFluxClient(settings.queryflux_url, settings.api_key)
        self.slots = asyncio.Semaphore(settings.max_analytics)
        self.running = self.waiting = self.requests = self.errors = self.queryflux_requests = 0
        self.last_execution = None
        self.latency_ms_total = 0.0
        self.last_latency_ms = None
        self.routes = {"direct:clickhouse": 0, "queryflux:clickhouse": 0, "queryflux:duckdb": 0}
        self.engine_metrics = {
            engine: {"requests": 0, "successes": 0, "errors": 0, "latency_ms_total": 0.0}
            for engine in ("clickhouse", "duckdb")
        }
        self.recent_executions = {}

    async def execute(self, sql: str, *, workload: str = "historical"):
        # This service receives only fixed SELECT templates from validated endpoints.
        if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql:
            raise ValueError("only one SELECT template is allowed")
        if workload not in ("historical", "recent_sample"):
            raise ValueError("unknown analytical workload")
        # This labels the fixed workload for observability, not engine dispatch.
        # QueryFlux's SQL-regex router chooses the actual execution target.
        engine = "duckdb" if workload == "recent_sample" else "clickhouse"
        if workload == "recent_sample" and self.settings.analytics_route != "queryflux":
            raise RuntimeError("Recent sample analytics require the QueryFlux route")
        if self.waiting >= 16:
            raise TimeoutError("analytics queue is full")
        self.waiting += 1
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=5)
        finally:
            self.waiting -= 1
        self.running += 1
        started = time.perf_counter()
        self.requests += 1
        route = self.settings.analytics_route
        self.routes[f"{route}:{engine}"] += 1
        observations = self.engine_metrics[engine]
        observations["requests"] += 1
        try:
            if route == "queryflux":
                self.queryflux_requests += 1
                data = await self.queryflux.query(sql)
            else:
                response = await self.direct.post(
                    "/",
                    content=sql + " FORMAT JSON",
                    params={"max_execution_time": 20, "max_memory_usage": 134217728},
                )
                response.raise_for_status()
                data = response.json()["data"]
            execution = {
                "route": route,
                "engine": engine,
                "workload": workload,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            self.last_execution = execution
            observations["successes"] += 1
            self.recent_executions[workload] = execution
            return {"data": data, **({"execution": execution} if self.settings.debug else {})}
        except Exception:
            self.errors += 1
            observations["errors"] += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            self.latency_ms_total += self.last_latency_ms
            observations["latency_ms_total"] += self.last_latency_ms
            self.running -= 1
            self.slots.release()

    async def close(self):
        await self.direct.aclose()
        await self.queryflux.close()


def recent_sql(vehicle_ids: list[str], minutes: int, max_age_seconds: int) -> str:
    """Fixed sample query. The sentinel guarantees a freshness check for empty data too."""
    import re

    if not 1 <= len(vehicle_ids) <= 8 or any(
        not re.fullmatch(r"V\d{6}", value) for value in vehicle_ids
    ):
        raise ValueError("expected one to eight vehicle IDs")
    if not 1 <= minutes <= 60 or not 1 <= max_age_seconds <= 600:
        raise ValueError("invalid recent query time bounds")
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    quoted = ", ".join(f"'{value}'" for value in vehicle_ids)
    return (
        "SELECT vehicle_id, COUNT(*) AS readings, AVG(speed_kmh) AS average_speed_kmh, "
        "MIN(timestamp) AS first_seen, MAX(timestamp) AS last_seen, "
        f"CASE WHEN MAX(snapshot_epoch) < {now.timestamp() - max_age_seconds} "
        "THEN error('Recent telemetry snapshot is stale') "
        "ELSE MAX(snapshot_epoch) END AS snapshot_epoch, "
        "MAX(window_minutes) AS window_minutes, MAX(vehicle_limit) AS vehicle_limit, "
        "MAX(row_limit) AS row_limit "
        "FROM valeosense_recent.telemetry "
        f"WHERE vehicle_id = '' OR (vehicle_id IN ({quoted}) AND timestamp >= '{cutoff}') "
        "GROUP BY vehicle_id ORDER BY vehicle_id"
    )


def where(days: int, fleet_id: str | None = None) -> str:
    # days and fleet_id are validated by FastAPI. Timestamps are generated locally;
    # no arbitrary user SQL is accepted. Parameter binding is used on metadata reads.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    clause = f"timestamp >= TIMESTAMP '{cutoff}'"
    if fleet_id:
        import re

        if not re.fullmatch(r"F\d{3}", fleet_id):
            raise ValueError("invalid fleet_id")
        clause += f" AND fleet_id = '{fleet_id}'"
    return clause
