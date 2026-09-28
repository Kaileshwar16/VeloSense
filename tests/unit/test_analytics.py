import asyncio

import httpx
import pytest

from backend.analytics import Analytics
from shared.config import Settings


async def test_concurrency_is_bounded_and_cancelled_waiter_releases_its_count():
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"data": []})

    analytics = Analytics(Settings(max_analytics=1, analytics_route="direct"))
    await analytics.direct.aclose()
    analytics.direct = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    first = asyncio.create_task(analytics.execute("SELECT 1"))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        second = asyncio.create_task(analytics.execute("SELECT 2"))
        await asyncio.sleep(0)
        assert analytics.running == 1 and analytics.waiting == 1
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert analytics.waiting == 0
        release.set()
        await asyncio.wait_for(first, timeout=1)
        assert analytics.running == 0
        assert (await analytics.execute("SELECT 3"))["data"] == []
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*[t for t in (first, second) if t is not None], return_exceptions=True)
        await analytics.close()


async def test_queryflux_failure_does_not_fall_back_to_direct():
    analytics = Analytics(Settings(analytics_route="queryflux"))
    await analytics.queryflux.client.aclose()
    analytics.queryflux.client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await analytics.execute("SELECT 1")
        assert analytics.routes == {
            "direct:clickhouse": 0,
            "queryflux:clickhouse": 1,
            "queryflux:duckdb": 0,
        }
        assert analytics.errors == 1 and analytics.running == 0
        assert analytics.last_execution is None
        assert analytics.latency_ms_total > 0
    finally:
        await analytics.close()


async def test_recent_workload_uses_same_gateway_and_records_engine_metrics():
    analytics = Analytics(Settings(analytics_route="queryflux", debug=True))
    seen = []

    async def query(sql):
        seen.append(sql)
        return [{"vehicle_id": "V000001", "readings": 3}]

    analytics.queryflux.query = query
    try:
        from backend.analytics import recent_sql

        sql = recent_sql(["V000001"], 15, 120)
        result = await analytics.execute(sql, workload="recent_sample")
        assert seen == [sql]
        assert result["execution"]["engine"] == "duckdb"
        assert result["execution"]["route"] == "queryflux"
        assert analytics.routes["queryflux:duckdb"] == 1
        assert analytics.engine_metrics["duckdb"]["successes"] == 1
        assert analytics.engine_metrics["clickhouse"]["requests"] == 0
        assert analytics.engine_metrics["duckdb"]["latency_ms_total"] > 0
    finally:
        await analytics.close()


async def test_duckdb_failure_is_counted_and_does_not_block_historical_queries():
    analytics = Analytics(Settings(analytics_route="queryflux"))

    async def query(sql):
        if "valeosense_recent" in sql:
            raise RuntimeError("Recent telemetry snapshot is stale")
        return [{"n": 1}]

    analytics.queryflux.query = query
    try:
        with pytest.raises(RuntimeError, match="stale"):
            await analytics.execute(
                "SELECT * FROM valeosense_recent.telemetry", workload="recent_sample"
            )
        assert analytics.engine_metrics["duckdb"]["errors"] == 1
        assert analytics.engine_metrics["duckdb"]["successes"] == 0
        assert (await analytics.execute("SELECT COUNT(*) FROM valeosense.telemetry_read"))["data"]
        assert analytics.engine_metrics["clickhouse"]["successes"] == 1
        assert analytics.running == 0
    finally:
        await analytics.close()


@pytest.mark.parametrize(
    "sql", ["DELETE FROM x", "SELECT 1; DROP TABLE x", "INSERT INTO x VALUES (1)"]
)
async def test_recent_workload_does_not_weaken_select_only_safety(sql):
    analytics = Analytics(Settings(analytics_route="queryflux"))
    try:
        with pytest.raises(ValueError, match="SELECT"):
            await analytics.execute(sql, workload="recent_sample")
        assert analytics.requests == 0
    finally:
        await analytics.close()


@pytest.mark.parametrize(
    "ids,minutes", [(["V000001' OR 1=1"], 15), (["V000001"] * 9, 15), (["V000001"], 61), ([], 15)]
)
def test_recent_sql_rejects_invalid_selection(ids, minutes):
    from backend.analytics import recent_sql

    with pytest.raises(ValueError):
        recent_sql(ids, minutes, 120)
