"""Verify a running cloud demo; health alone does not establish a working stream."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from shared.config import Settings


def check_progress(before, after, now):
    for kind, counter in (("processor", "accepted"), ("simulator", "published")):
        first, last = before.get(kind), after.get(kind)
        if not first or not last:
            raise RuntimeError(f"Missing {kind} metrics")
        if not 0 <= now - last.get("updated_at", 0) < 15:
            raise RuntimeError(f"Stale {kind} heartbeat")
        if last[counter] <= first[counter]:
            raise RuntimeError(f"{kind} counter did not advance")
    if before["processor"]["instance_id"] != after["processor"]["instance_id"]:
        raise RuntimeError("Processor restarted during verification")
    if after["processor"]["processor_errors"] or after["simulator"]["errors"]:
        raise RuntimeError("The pipeline reports errors")


def verify(url, api_key, interval=15):
    with httpx.Client(base_url=url, timeout=35) as client:

        def get(path):
            response = client.get(path, headers={"X-API-Key": api_key})
            response.raise_for_status()
            return response.json()

        assert client.get("/api/v1/vehicles").status_code == 401
        health = get("/health")
        assert health["status"] == "ok"
        listing = get("/api/v1/vehicles?limit=1")
        assert listing["pagination"]["total"] == 100000
        initial = get("/api/v1/system/metrics")["data"]
        first_live = get("/api/v1/vehicles/V000001/live")["data"]
        assert first_live, "No live telemetry"
        time.sleep(interval)
        final = get("/api/v1/system/metrics")["data"]
        check_progress(initial, final, time.time())
        live = get("/api/v1/vehicles/V000001/live")["data"]
        assert live["timestamp"] > first_live["timestamp"], "Vehicle telemetry did not advance"
        history = get("/api/v1/vehicles/V000001/history?limit=10")["data"]
        assert history, "Persisted history is empty"
        latest = datetime.fromisoformat(history[0]["timestamp"].replace("Z", "+00:00"))
        assert 0 <= time.time() - latest.timestamp() < 60, "Persisted history is stale"
        routing = get("/api/v1/system/routing")["data"]
        return {
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "api_url": url,
            "passed": True,
            "registry_count": listing["pagination"]["total"],
            "route": routing["analytics_configured_route"],
            "accepted_delta": final["processor"]["accepted"] - initial["processor"]["accepted"],
            "published_delta": final["simulator"]["published"] - initial["simulator"]["published"],
            "consumer_lag": final["processor"]["consumer_lag"],
            "checks": [
                "unauthenticated access rejected",
                "dependencies healthy",
                "100K registry",
                "fresh advancing simulator and processor",
                "live vehicle advanced",
                "recent persisted ClickHouse history",
            ],
            "limits": "Bounded functional check; not a throughput, HA, SLA or dual-engine proof.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://frontend:8080")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(verify(args.url, Settings().api_key), indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")
