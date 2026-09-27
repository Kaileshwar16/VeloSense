import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import psycopg
import redis
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.analytics import Analytics, where
from shared.config import Settings
from shared.storage import Metadata

VehicleID = Annotated[str, Path(pattern=r"^V\d{6}$")]
FleetFilter = Annotated[str | None, Query(pattern=r"^F\d{3}$")]


def create_app(settings: Settings | None = None, live=None, metadata=None, analytics=None):
    settings = settings or Settings()
    api_metrics = {
        "requests": 0,
        "errors": 0,
        "latency_ms_total": 0.0,
        "live_queries": 0,
        "metadata_queries": 0,
    }

    @asynccontextmanager
    async def lifespan(app):
        if not settings.api_key:
            raise RuntimeError("API_KEY must be configured; run make setup")
        yield
        await app.state.live.aclose()
        await app.state.analytics.close()

    app = FastAPI(title="ValeoSense", version="0.1.0", lifespan=lifespan)
    app.state.live = live or aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.metadata = metadata or Metadata(settings)
    app.state.analytics = analytics or Analytics(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors,
        allow_methods=["GET"],
        allow_headers=["X-API-Key"],
        allow_credentials=False,
    )

    async def authenticate(x_api_key: str = Header(default="")):
        if not settings.api_key or not hmac.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(401, "A valid X-API-Key is required")

    auth = [Depends(authenticate)]

    @app.middleware("http")
    async def measure(request: Request, call_next):
        started = time.perf_counter()
        api_metrics["requests"] += 1
        response = await call_next(request)
        api_metrics["errors"] += int(response.status_code >= 400)
        api_metrics["latency_ms_total"] += (time.perf_counter() - started) * 1000
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.status_code, "message": str(exc.detail)}},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": 422,
                    "message": "Invalid request parameters",
                    "fields": [list(e["loc"]) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    async def dependency_error(request, exc):
        logging.getLogger("valeosense").error("dependency_error type=%s", type(exc).__name__)
        return JSONResponse(
            {"error": {"code": 503, "message": "A required data service is unavailable"}},
            status_code=503,
        )

    for error in (httpx.HTTPError, redis.RedisError, psycopg.Error, TimeoutError, RuntimeError):
        app.add_exception_handler(error, dependency_error)

    async def meta(sql, params=()):
        api_metrics["metadata_queries"] += 1
        return await asyncio.to_thread(app.state.metadata.query, sql, params)

    async def known(vehicle_id):
        api_metrics["metadata_queries"] += 1
        value = await asyncio.to_thread(app.state.metadata.vehicle, vehicle_id)
        if value is None:
            raise HTTPException(404, "Vehicle not found")
        return value

    @app.get("/health")
    async def health():
        checks = {}
        for name, operation in (
            ("redis", lambda: app.state.live.ping()),
            ("postgres", lambda: meta("SELECT 1 AS ok")),
            ("clickhouse", lambda: app.state.analytics.direct.get("/ping")),
        ):
            try:
                result = await operation()
                if isinstance(result, httpx.Response):
                    result.raise_for_status()
                checks[name] = "ok"
            except Exception:
                checks[name] = "unavailable"
        ok = all(value == "ok" for value in checks.values())
        return JSONResponse(
            {"status": "ok" if ok else "degraded", "services": checks},
            status_code=200 if ok else 503,
        )

    @app.get("/api/v1/vehicles", dependencies=auth)
    async def vehicles(
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        fleet_id: FleetFilter = None,
    ):
        api_metrics["metadata_queries"] += 1
        rows = await asyncio.to_thread(app.state.metadata.vehicles, limit, offset, fleet_id)
        clause, params = ("WHERE fleet_id=%s", (fleet_id,)) if fleet_id else ("", ())
        count = (await meta(f"SELECT count(*) AS n FROM vehicles {clause}", params))[0]["n"]
        api_metrics["live_queries"] += 1
        values = (
            await app.state.live.mget([f"vehicle:{row['vehicle_id']}:latest" for row in rows])
            if rows
            else []
        )
        for row, state in zip(rows, values):
            row["live"] = json.loads(state) if state else None
        return {"data": rows, "pagination": {"limit": limit, "offset": offset, "total": count}}

    @app.get("/api/v1/vehicles/{vehicle_id}", dependencies=auth)
    async def vehicle(vehicle_id: VehicleID):
        return {"data": await known(vehicle_id)}

    @app.get("/api/v1/vehicles/{vehicle_id}/live", dependencies=auth)
    async def live_vehicle(vehicle_id: VehicleID):
        await known(vehicle_id)
        api_metrics["live_queries"] += 1
        value = await app.state.live.get(f"vehicle:{vehicle_id}:latest")
        return {"data": json.loads(value) if value else None}

    @app.get("/api/v1/vehicles/{vehicle_id}/history", dependencies=auth)
    async def history(
        vehicle_id: VehicleID,
        days: int = Query(1, ge=1, le=30),
        limit: int = Query(100, ge=1, le=1000),
    ):
        await known(vehicle_id)
        return await app.state.analytics.execute(
            "SELECT concat(CAST(timestamp AS VARCHAR), 'Z') AS timestamp, "
            "speed_kmh, lat, lon, fuel_pct, soc_pct, event_type "
            f"FROM valeosense.telemetry_read WHERE vehicle_id = '{vehicle_id}' AND {where(days)} "
            f"ORDER BY timestamp DESC LIMIT {limit}"
        )

    @app.get("/api/v1/alerts", dependencies=auth)
    async def alerts(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        api_metrics["live_queries"] += 1
        cutoff = time.time() - settings.online_seconds
        members = await app.state.live.zrevrangebyscore(
            "alerts:active", "+inf", cutoff, start=offset, num=limit
        )
        keys = list(dict.fromkeys(member.split(":")[0] for member in members))
        values = await app.state.live.mget([f"alerts:{key}" for key in keys]) if keys else []
        wanted = set(members)
        data = [
            a
            for value in values
            if value
            for a in json.loads(value)
            if f"{a['vehicle_id']}:{a['type']}" in wanted
        ]
        total = await app.state.live.zcount("alerts:active", cutoff, "+inf")
        return {"data": data, "pagination": {"limit": limit, "offset": offset, "total": total}}

    @app.get("/api/v1/fleet/summary", dependencies=auth)
    async def summary():
        registered = (await meta("SELECT count(*) AS n FROM vehicles"))[0]["n"]
        api_metrics["live_queries"] += 1
        cutoff = time.time() - settings.online_seconds
        pipe = app.state.live.pipeline(transaction=False)
        for index in ("vehicles:online", "vehicles:idling", "alerts:active"):
            pipe.zcount(index, cutoff, "+inf")
        pipe.get("metrics:processor")
        online, idling, active, raw = await pipe.execute()
        metrics = json.loads(raw) if raw else {}
        fresh = time.time() - metrics.get("updated_at", 0) < 5
        return {
            "data": {
                "registered_vehicles": registered,
                "online_vehicles": online,
                "currently_idling": idling,
                "active_alerts": active,
                "events_per_sec": round(metrics.get("consumed_per_sec", 0), 1) if fresh else 0,
                "processor_reporting": fresh,
            }
        }

    @app.get("/api/v1/analytics/idling", dependencies=auth)
    async def idling(days: int = Query(7, ge=1, le=30), fleet_id: FleetFilter = None):
        result = await app.state.analytics.execute(
            f"SELECT vehicle_id, fleet_id, SUM(idling_seconds) AS duration_seconds, "
            f"SUM(estimated_fuel_l) AS estimated_fuel_l, SUM(estimated_cost) AS estimated_cost "
            f"FROM valeosense.telemetry_read WHERE {where(days, fleet_id)} "
            "GROUP BY vehicle_id, fleet_id HAVING SUM(idling_seconds) > 0 "
            "ORDER BY duration_seconds DESC LIMIT 20"
        )
        result["assumptions"] = {
            "idle_fuel_lph": settings.fuel_lph,
            "fuel_price_per_litre": settings.fuel_price,
            "currency": "INR",
            "scope": "top 20 vehicles; sampled continuous idle intervals; ICE fuel only",
        }
        return result

    @app.get("/api/v1/analytics/events", dependencies=auth)
    async def events(days: int = Query(1, ge=1, le=30), fleet_id: FleetFilter = None):
        return await app.state.analytics.execute(
            "SELECT concat(CAST(date_trunc('minute', timestamp) AS VARCHAR), 'Z') AS minute, "
            "event_type, COUNT(*) AS events, "
            f"AVG(speed_kmh) AS average_speed_kmh FROM valeosense.telemetry_read "
            f"WHERE {where(days, fleet_id)} GROUP BY minute, event_type "
            "ORDER BY minute DESC, event_type LIMIT 240"
        )

    @app.get("/api/v1/analytics/faults", dependencies=auth)
    async def faults(days: int = Query(7, ge=1, le=30), fleet_id: FleetFilter = None):
        return await app.state.analytics.execute(
            "SELECT type, COUNT(*) AS incidents FROM valeosense.alerts_read "
            f"WHERE {where(days, fleet_id)} GROUP BY type ORDER BY incidents DESC"
        )

    @app.get("/api/v1/system/metrics", dependencies=auth)
    async def metrics():
        values = await app.state.live.mget(["metrics:processor", "metrics:simulator"])
        analytics = app.state.analytics
        return {
            "data": {
                "processor": json.loads(values[0]) if values[0] else None,
                "simulator": json.loads(values[1]) if values[1] else None,
                "api": dict(api_metrics),
                "analytics_running": analytics.running,
                "analytics_waiting": analytics.waiting,
                "analytics_requests": analytics.requests,
                "analytics_errors": analytics.errors,
                "queryflux_requests": analytics.queryflux_requests,
            }
        }

    @app.get("/api/v1/system/routing", dependencies=auth)
    async def routing():
        analytics = app.state.analytics
        return {
            "data": {
                "live": "redis",
                "metadata": "postgresql",
                "analytics_configured_route": settings.analytics_route,
                "engine": "clickhouse",
                "routing_counts": dict(analytics.routes),
                "last_successful_execution": analytics.last_execution if settings.debug else None,
                "queryflux_verified_in_process": analytics.queryflux_requests > 0
                and analytics.last_execution is not None
                and analytics.last_execution["route"] == "queryflux",
            }
        }

    return app


app = create_app()
