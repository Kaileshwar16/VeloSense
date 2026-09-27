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
        assert analytics.routes == {"direct:clickhouse": 0, "queryflux:clickhouse": 1}
        assert analytics.errors == 1 and analytics.running == 0
        assert analytics.last_execution is None
        assert analytics.latency_ms_total > 0
    finally:
        await analytics.close()
