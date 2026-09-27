import httpx
import pytest

from backend.queryflux.client import QueryFluxClient


@pytest.mark.asyncio
async def test_trino_pages_are_combined():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(200, json={"nextUri": "http://proxy:18080/page"})
        return httpx.Response(200, json={"columns": [{"name": "count"}], "data": [[4]]})

    client = QueryFluxClient("http://proxy:18080", "test")
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await client.query("SELECT 4") == [{"count": 4}]
    assert len(seen) == 2
    await client.close()


@pytest.mark.asyncio
async def test_untrusted_pagination_never_receives_credentials_or_cancellation():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"nextUri": "http://attacker.invalid/steal"})

    client = QueryFluxClient("http://proxy:18080", "test")
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="untrusted"):
        await client.query("SELECT 4")
    assert seen == ["http://proxy:18080/v1/statement"]
    await client.close()


@pytest.mark.asyncio
async def test_query_errors_are_not_reported_as_success():
    client = QueryFluxClient("http://proxy", "test")
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"error": {"message": "backend failed"}})
        )
    )
    with pytest.raises(RuntimeError, match="backend failed"):
        await client.query("SELECT 1")
    await client.close()
