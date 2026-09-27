"""Real Kafka -> running processor -> Redis/ClickHouse -> FastAPI -> QueryFlux.

Run RUN_INTEGRATION=1 pytest -q after make up and starting QueryFlux/API.
Never convert an unavailable required service into a passing integration test.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import redis

from shared.config import Settings
from shared.storage import ClickHouse
from simulator.generator import Generator
from simulator.producer import KafkaProducer
from simulator.vehicle_factory import vehicles

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="requires running Compose services, processor, and API",
    ),
]


def test_real_wire_path_idling_dedup_and_history():
    settings = Settings()
    vehicle = list(vehicles(100000))[-1]
    generator = Generator([vehicle], start=datetime.now(timezone.utc) - timedelta(seconds=28))
    generator.force(0, "IDLING", 100)
    generator.state(vehicle).speed = 0
    events = [generator.tick(0, generator.start + timedelta(seconds=t))[0] for t in range(25)]
    live = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    producer = KafkaProducer(settings.kafka, settings.topic)
    producer.publish(events + [events[-1]])
    producer.close()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        value = live.get(f"vehicle:{vehicle.vehicle_id}:latest")
        if value and json.loads(value)["event_id"] == events[-1]["event_id"]:
            break
        time.sleep(0.25)
    else:
        pytest.fail("processor did not persist the Kafka event within 30 seconds")
    with httpx.Client(
        base_url="http://127.0.0.1:8000", headers={"X-API-Key": settings.api_key}, timeout=30
    ) as client:
        response = client.get(f"/api/v1/vehicles/{vehicle.vehicle_id}/live")
        assert response.status_code == 200
        state = response.json()["data"]
        assert state["event_id"] == events[-1]["event_id"]
        assert state["idle_duration_seconds"] == 24
        assert "IDLING_ALERT" in state["active_alerts"]
        history = client.get(f"/api/v1/vehicles/{vehicle.vehicle_id}/history").json()
        assert history["data"]
        assert all(
            row["timestamp"] is not None and row["timestamp"].endswith("Z")
            for row in history["data"]
        )
        events_result = client.get("/api/v1/analytics/events").json()
        assert all(row["minute"] and row["minute"].endswith("Z") for row in events_result["data"])
        if os.getenv("EXPECT_QUERYFLUX") == "1":
            assert history["execution"]["route"] == "queryflux"
        store = ClickHouse(settings)
        count = store.query(
            "SELECT count(*) AS n FROM valeosense.telemetry_read WHERE event_id = {event:UUID}",
            {"param_event": events[-1]["event_id"]},
        )
        assert int(count[0]["n"]) == 1
        alert_id = state["active_alerts"]["IDLING_ALERT"]["alert_id"]
        count = store.query(
            "SELECT count(*) AS n FROM valeosense.alerts_read WHERE alert_id = {alert:UUID}",
            {"param_alert": alert_id},
        )
        assert int(count[0]["n"]) == 1
        # Crash replay simulation at analytical sink: same persisted row inserted twice.
        row = store.query(
            "SELECT * FROM valeosense.telemetry_read WHERE event_id = {event:UUID}",
            {"param_event": events[-1]["event_id"]},
        )[0]
        store.insert("telemetry", [row])
        count = store.query(
            "SELECT count(*) AS n FROM valeosense.telemetry_read WHERE event_id = {event:UUID}",
            {"param_event": events[-1]["event_id"]},
        )
        assert int(count[0]["n"]) == 1
        history_again = client.get(f"/api/v1/vehicles/{vehicle.vehicle_id}/history").json()
        timestamps = [row["timestamp"] for row in history_again["data"]]
        assert len(timestamps) == len(set(timestamps))
        store.close()
    live.close()
