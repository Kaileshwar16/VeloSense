"""Verify both real QueryFlux engines and their native execution counters.

Run inside the backend container. --seed adds three explicitly identified synthetic
VeloSense readings to canonical ClickHouse using the existing generator/detector.
It does not put fixture rows directly into DuckDB or claim to verify Kafka ingestion.
"""

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.queryflux.client import QueryFluxClient
from processor.detectors import transition
from shared.config import Settings
from shared.models import Telemetry
from shared.storage import ClickHouse
from simulator.generator import Generator
from simulator.vehicle_factory import vehicles


def native_counts(text: str) -> dict[str, float]:
    counts = {"ClickHouse": 0.0, "DuckDb": 0.0}
    for line in text.splitlines():
        if not line.startswith("queryflux_queries_total{"):
            continue
        labels, value = line.rsplit(" ", 1)
        if 'status="Success"' not in labels:
            continue
        match = re.search(r'engine_type="([^"]+)"', labels)
        if match and match[1] in counts:
            counts[match[1]] += float(value)
    return counts


def seed(settings: Settings):
    vehicle = list(vehicles(settings.duckdb_vehicle_limit))[-1]
    generator = Generator([vehicle], start=datetime.now(timezone.utc) - timedelta(seconds=3))
    generator.force(0, "NORMAL", 100)
    rows, state = [], None
    for second in range(3):
        event = Telemetry.model_validate(
            generator.tick(0, generator.start + timedelta(seconds=second))[0]
        )
        state, row, _, _ = transition(event, state, settings)
        rows.append(row)
    store = ClickHouse(settings)
    try:
        store.insert("telemetry", rows)
    finally:
        store.close()
    return vehicle.vehicle_id, [str(row["event_id"]) for row in rows]


async def verify(add_fixture: bool):
    settings = Settings()
    vehicle, event_ids = seed(settings) if add_fixture else ("V000001", [])
    api_url = os.getenv("VERIFY_API_URL", "http://127.0.0.1:8000")
    metrics_url = os.getenv("QUERYFLUX_METRICS_URL", "http://queryflux:19000/metrics")
    async with httpx.AsyncClient(timeout=35) as client:
        gateway = QueryFluxClient(settings.queryflux_url, settings.api_key)
        # Close even when a verification assertion fails.
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(gateway.close)
            return await verify_routes(
                client, gateway, settings, vehicle, event_ids, api_url, metrics_url
            )


async def verify_routes(client, gateway, settings, vehicle, event_ids, api_url, metrics_url):
    before_response = await client.get(metrics_url)
    before_response.raise_for_status()
    before = native_counts(before_response.text)
    headers = {"X-API-Key": settings.api_key}
    deadline = time.monotonic() + 90
    while True:
        light = await client.get(
            api_url + "/api/v1/analytics/recent",
            params={"vehicle_ids": vehicle, "minutes": 15},
            headers=headers,
        )
        light.raise_for_status()
        sample = light.json()
        fixture_arrived = True
        if event_ids:
            quoted = ",".join(f"'{value}'" for value in event_ids)
            duck = await gateway.query(
                "SELECT COUNT(*) AS n FROM valeosense_recent.telemetry "
                f"WHERE event_id IN ({quoted})"
            )
            fixture_arrived = int(duck[0]["n"]) == len(event_ids)
        if sample["data"] and fixture_arrived:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "No real recent telemetry reached DuckDB; start the stream or use --seed"
            )
        await asyncio.sleep(2)
    assert sample.get("execution", {}).get("engine") == "duckdb", "verification needs DEBUG=true"
    assert sample["execution"]["route"] == "queryflux"
    assert sample["scope"]["complete_history"] is False
    if event_ids:
        # Exact event identity in both stores proves data lineage, beyond API labels.
        quoted = ",".join(f"'{value}'" for value in event_ids)
        duck = await gateway.query(
            f"SELECT COUNT(*) AS n FROM valeosense_recent.telemetry WHERE event_id IN ({quoted})"
        )
        ch = await gateway.query(
            f"SELECT COUNT(*) AS n FROM valeosense.telemetry_read WHERE event_id IN ({quoted})"
        )
        assert int(duck[0]["n"]) == int(ch[0]["n"]) == len(event_ids)
    heavy = await client.get(api_url + "/api/v1/analytics/events", headers=headers)
    heavy.raise_for_status()
    assert heavy.json()["data"], "ClickHouse historical query returned no telemetry"
    assert heavy.json().get("execution", {}).get("engine") == "clickhouse"
    assert heavy.json()["execution"]["route"] == "queryflux"
    after_response = await client.get(metrics_url)
    after_response.raise_for_status()
    after = native_counts(after_response.text)
    delta = {engine: after[engine] - before[engine] for engine in before}
    assert all(value > 0 for value in delta.values()), "native engine counters did not advance"
    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "seeded_event_ids": event_ids,
        "seed_path": "generator -> detector -> canonical ClickHouse -> snapshot -> DuckDB"
        if event_ids
        else None,
        "light": sample,
        "heavy_execution": heavy.json()["execution"],
        "native_success_count_delta": delta,
        "checks": [
            "real API -> QueryFlux -> DuckDB",
            "real API -> QueryFlux -> ClickHouse",
            "native per-engine counters advanced",
            "bounded snapshot scope disclosed",
        ],
        "passed": True,
    }
    if event_ids:
        result["checks"].append("exact seeded event IDs found through both QueryFlux routes")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.seed)), indent=2))
