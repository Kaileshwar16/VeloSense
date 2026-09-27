"""Optional internal Prometheus exporter for the existing authenticated JSON API."""

import asyncio
import math
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import Response

from shared.config import Settings


def render_metrics(metrics: dict, routing: dict, now: float) -> str:
    lines = []

    def emit(name, value, kind="gauge", help_text=None):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return
        name = "valeosense_" + name
        lines.extend(
            [f"# HELP {name} {help_text or name}", f"# TYPE {name} {kind}", f"{name} {value}"]
        )

    for source in ("processor", "simulator"):
        data = metrics.get(source) or {}
        updated = data.get("updated_at")
        age = max(0, now - updated) if isinstance(updated, (int, float)) else None
        fresh = age is not None and age < 5 and data.get("running") is not False
        emit(f"{source}_reporting", int(fresh), help_text="Heartbeat is less than 5 seconds old.")
        emit(f"{source}_heartbeat_age_seconds", age)
        # Redis can retain a stopped process's last report for 120s. Do not expose
        # its throughput, lag or counters as current observations.
        if not fresh:
            continue
        counters = (
            (
                "consumed",
                "accepted",
                "duplicates_ignored",
                "validation_errors",
                "late_events",
                "alerts_generated",
                "processor_errors",
            )
            if source == "processor"
            else ("generated", "emitted", "published", "errors", "backpressure")
        )
        for key in counters:
            emit(f"{source}_{key}_total", data.get(key), "counter")
        for key in ("consumer_lag", "consumed_per_sec", "generated_per_sec"):
            emit(f"{source}_{key}", data.get(key))
        latency = data.get("event_latency_ms")
        if isinstance(latency, (int, float)):
            emit("processor_last_batch_event_latency_seconds", latency / 1000)

    api = metrics.get("api") or {}
    for key in ("requests", "errors", "live_queries", "metadata_queries"):
        emit(f"api_{key}_total", api.get(key), "counter")
    latency = api.get("latency_ms_total")
    if isinstance(latency, (int, float)):
        emit("api_request_duration_seconds_total", latency / 1000, "counter")
    for key in ("analytics_requests", "analytics_errors", "queryflux_requests"):
        emit(f"{key}_total", metrics.get(key), "counter")
    for key in ("analytics_running", "analytics_waiting"):
        emit(key, metrics.get(key))
    latency = metrics.get("analytics_latency_ms_total")
    if isinstance(latency, (int, float)):
        emit("analytics_request_duration_seconds_total", latency / 1000, "counter")
    counts = routing.get("routing_counts") or {}
    for route in ("direct", "queryflux"):
        emit(f"route_{route}_requests_total", counts.get(f"{route}:clickhouse"), "counter")
        emit(f"route_{route}_configured", int(routing.get("analytics_configured_route") == route))
    emit("queryflux_verified", int(routing.get("queryflux_verified_in_process") is True))
    return "\n".join(lines) + "\n"


def create_app(client=None):
    @asynccontextmanager
    async def lifespan(app):
        owned = client is None
        if owned:
            settings = Settings()
            if not settings.api_key:
                raise RuntimeError("API_KEY is required")
            app.state.client = httpx.AsyncClient(
                base_url=os.getenv("MONITORING_API_URL", "http://backend:8000"),
                headers={"X-API-Key": settings.api_key},
                timeout=3,
            )
        else:
            app.state.client = client
        try:
            yield
        finally:
            if owned:
                await app.state.client.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics():
        try:
            responses = await asyncio.gather(
                app.state.client.get("/api/v1/system/metrics"),
                app.state.client.get("/api/v1/system/routing"),
            )
            for response in responses:
                response.raise_for_status()
            payloads = [response.json()["data"] for response in responses]
            text = render_metrics(*payloads, now=time.time())
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            # A failed scrape must be up=0, never a cached successful snapshot.
            return Response("Metrics source unavailable\n", status_code=503)
        return Response(text, headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"})

    return app


app = create_app()
