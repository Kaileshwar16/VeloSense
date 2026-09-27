import httpx
import pytest

from backend.monitoring import create_app, render_metrics


def test_fresh_counters_units_and_unknown_lag():
    text = render_metrics(
        {
            "processor": {
                "updated_at": 99,
                "consumed": 42,
                "consumer_lag": None,
                "event_latency_ms": 250,
            },
            "api": {"requests": 5, "latency_ms_total": 100},
        },
        {"analytics_configured_route": "queryflux", "queryflux_verified_in_process": False},
        now=100,
    )
    assert "# TYPE valeosense_processor_consumed_total counter" in text
    assert "valeosense_processor_consumed_total 42\n" in text
    assert "valeosense_processor_last_batch_event_latency_seconds 0.25\n" in text
    assert "valeosense_api_request_duration_seconds_total 0.1\n" in text
    assert "valeosense_processor_consumer_lag" not in text
    assert "valeosense_route_queryflux_configured 1\n" in text
    assert "valeosense_queryflux_verified 0\n" in text


@pytest.mark.parametrize(
    "report",
    [
        None,
        {},
        {"updated_at": 95, "consumed": 42},
        {"updated_at": 100, "running": False, "consumed": 42},
    ],
)
def test_missing_and_stale_reports_do_not_become_zero_lag_or_live_counters(report):
    text = render_metrics({"processor": report}, {}, now=100)
    assert "valeosense_processor_reporting 0\n" in text
    assert "valeosense_processor_consumer_lag" not in text
    assert "valeosense_processor_consumed_total" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "unauthorized", "unavailable", "malformed"])
async def test_scrape_authentication_and_failure_visibility(failure):
    def handler(request):
        assert request.headers["X-API-Key"] == "secret-test-key"
        if failure == "unauthorized":
            return httpx.Response(401)
        if failure == "unavailable":
            raise httpx.ConnectError("private upstream address", request=request)
        if failure == "malformed":
            return httpx.Response(200, text="invalid JSON")
        return httpx.Response(200, json={"data": {"api": {"requests": 7}}})

    async with httpx.AsyncClient(
        base_url="http://backend",
        headers={"X-API-Key": "secret-test-key"},
        transport=httpx.MockTransport(handler),
    ) as upstream:
        app = create_app(upstream)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                base_url="http://exporter", transport=httpx.ASGITransport(app)
            ) as client:
                response = await client.get("/metrics")
    if failure:
        assert response.status_code == 503
        assert response.text == "Metrics source unavailable\n"
    else:
        assert response.status_code == 200
        assert "version=0.0.4" in response.headers["content-type"]
        assert "valeosense_api_requests_total 7\n" in response.text
    assert "secret-test-key" not in response.text
