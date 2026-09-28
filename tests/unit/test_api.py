import json
from dataclasses import replace

import httpx
import pytest

from backend.analytics import Analytics
from backend.main import create_app
from shared.config import Settings


class TestMetadata:
    __test__ = False

    def query(self, sql, params=()):
        return [{"n": 1, "ok": 1}]

    def vehicle(self, vehicle_id):
        return {"vehicle_id": vehicle_id} if vehicle_id == "V000001" else None

    def vehicles(self, limit, offset, fleet_id):
        return [{"vehicle_id": "V000001"}] if offset == 0 else []


class TestLive:
    __test__ = False

    async def ping(self):
        return True

    async def get(self, key):
        return json.dumps({"vehicle_id": "V000001", "speed_kmh": 42})

    async def mget(self, keys):
        return [await self.get(key) for key in keys]

    async def aclose(self):
        pass


@pytest.fixture
async def api():
    settings = Settings(api_key="test-key", debug=True, analytics_route="direct")
    analytics = Analytics(settings)
    await analytics.direct.aclose()
    analytics.direct = httpx.AsyncClient(
        base_url="http://clickhouse",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"vehicle_id": "V000001"}]})
        ),
    )
    app = create_app(settings, live=TestLive(), metadata=TestMetadata(), analytics=analytics)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-key"},
        ) as client:
            yield client


async def test_health(api):
    response = await api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_live_and_not_found(api):
    response = await api.get("/api/v1/vehicles/V000001/live")
    assert response.json()["data"]["speed_kmh"] == 42
    response = await api.get("/api/v1/vehicles/V999999/live")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == 404


async def test_pagination(api):
    response = await api.get("/api/v1/vehicles?limit=1")
    assert response.json()["pagination"] == {"limit": 1, "offset": 0, "total": 1}
    assert len(response.json()["data"]) == 1
    assert (await api.get("/api/v1/vehicles?offset=1")).json()["data"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/vehicles?limit=101",
        "/api/v1/vehicles?offset=-1",
        "/api/v1/vehicles/not-valid/live",
        "/api/v1/analytics/idling?days=999",
        "/api/v1/analytics/idling?fleet_id=F001%27OR1=1",
    ],
)
async def test_input_validation(api, path):
    response = await api.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Invalid request parameters"


async def test_api_key_and_analytics(api):
    response = await api.get("/api/v1/vehicles", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
    response = await api.get("/api/v1/analytics/idling")
    assert response.status_code == 200
    assert response.json()["execution"]["route"] == "direct"
    assert response.json()["assumptions"]["currency"] == "INR"


async def test_analytics_rejects_mutations_and_hides_debug_metadata():
    analytics = Analytics(replace(Settings(), debug=False, analytics_route="direct"))
    with pytest.raises(ValueError):
        await analytics.execute("DELETE FROM telemetry")
    await analytics.direct.aclose()
    analytics.direct = httpx.AsyncClient(
        base_url="http://clickhouse",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []})),
    )
    result = await analytics.execute("SELECT 1")
    assert "execution" not in result
    assert analytics.running == 0
    await analytics.close()


async def test_unknown_path_has_consistent_error(api):
    response = await api.get("/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == 404


async def test_metrics_include_analytical_latency(api):
    assert (await api.get("/api/v1/analytics/idling")).status_code == 200
    metrics = (await api.get("/api/v1/system/metrics")).json()["data"]
    assert metrics["analytics_latency_ms_total"] > 0
    assert metrics["analytics_last_latency_ms"] > 0
    assert metrics["analytics_running"] == metrics["analytics_waiting"] == 0


@pytest.mark.parametrize(
    "query", ["vehicle_ids=V000001%27OR1=1", "vehicle_ids=V000101", "minutes=61"]
)
async def test_recent_api_rejects_unbounded_or_invalid_selection(api, query):
    assert (await api.get("/api/v1/analytics/recent?" + query)).status_code == 422


async def test_recent_api_explicitly_requires_queryflux(api):
    response = await api.get("/api/v1/analytics/recent")
    assert response.status_code == 503
    assert "QueryFlux" in response.json()["error"]["message"]


@pytest.mark.parametrize("failed", [False, True])
async def test_recent_api_discloses_scope_hides_metadata_row_and_surfaces_engine_failure(failed):
    settings = Settings(api_key="test-key", debug=True, analytics_route="queryflux")
    analytics = Analytics(settings)

    async def execute(sql, *, workload):
        assert workload == "recent_sample"
        assert "FROM valeosense_recent.telemetry" in sql
        if failed:
            raise RuntimeError("Recent telemetry snapshot is stale")
        return {
            "data": [
                {
                    "vehicle_id": "",
                    "window_minutes": 120,
                    "vehicle_limit": 100,
                    "row_limit": 20000,
                    "snapshot_epoch": 100,
                },
                {
                    "vehicle_id": "V000001",
                    "readings": 3,
                    "average_speed_kmh": 42,
                    "first_seen": "2026-09-28 10:00:00",
                    "last_seen": "2026-09-28 10:00:02",
                },
            ]
        }

    analytics.execute = execute
    app = create_app(settings, live=TestLive(), metadata=TestMetadata(), analytics=analytics)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://test",
            headers={"X-API-Key": "test-key"},
        ) as client:
            response = await client.get("/api/v1/analytics/recent")
    if failed:
        assert response.status_code == 503
    else:
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["vehicle_id"] == "V000001"
        assert response.json()["scope"]["complete_history"] is False
        assert response.json()["scope"]["row_limit"] == 20000
