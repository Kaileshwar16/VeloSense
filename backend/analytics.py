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
        self.routes = {"direct:clickhouse": 0, "queryflux:clickhouse": 0}

    async def execute(self, sql: str):
        # This service receives only fixed SELECT templates from validated endpoints.
        if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql:
            raise ValueError("only one SELECT template is allowed")
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
        self.routes[f"{route}:clickhouse"] += 1
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
                "engine": "clickhouse",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            self.last_execution = execution
            return {"data": data, **({"execution": execution} if self.settings.debug else {})}
        except Exception:
            self.errors += 1
            raise
        finally:
            self.running -= 1
            self.slots.release()

    async def close(self):
        await self.direct.aclose()
        await self.queryflux.close()


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
