"""Real Trino HTTP client for the upstream QueryFlux proxy; no engine emulation."""

import asyncio
import time
from urllib.parse import urlparse

import httpx


class QueryFluxClient:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=20, auth=("valeosense", api_key), headers={"X-Trino-User": "valeosense"}
        )

    async def query(self, sql: str) -> list[dict]:
        response = await self.client.post(self.url + "/v1/statement", content=sql)
        response.raise_for_status()
        page = response.json()
        rows, columns = [], []
        deadline = time.monotonic() + 25
        next_uri = None
        try:
            while True:
                if page.get("error"):
                    raise RuntimeError(
                        "QueryFlux query failed: " + page["error"].get("message", "unknown")
                    )
                if page.get("columns"):
                    columns = [column["name"] for column in page["columns"]]
                rows.extend(page.get("data") or [])
                if len(rows) > 10000:
                    raise RuntimeError("QueryFlux result exceeded the bounded row limit")
                next_uri = page.get("nextUri")
                if not next_uri:
                    break
                # Follow only our configured proxy; do not forward credentials to an arbitrary URL.
                parsed = urlparse(next_uri)
                origin = urlparse(self.url)
                if parsed.scheme != origin.scheme or parsed.netloc != origin.netloc:
                    # Containers can reach the host while QF advertises localhost.
                    if (
                        parsed.hostname not in ("localhost", "127.0.0.1")
                        or parsed.port != origin.port
                    ):
                        raise RuntimeError("QueryFlux returned an untrusted pagination origin")
                    next_uri = self.url + parsed.path + ("?" + parsed.query if parsed.query else "")
                if time.monotonic() > deadline:
                    raise TimeoutError("QueryFlux query exceeded 25 seconds")
                await asyncio.sleep(0.02)
                response = await self.client.get(next_uri)
                response.raise_for_status()
                page = response.json()
        except BaseException:
            if next_uri:
                try:
                    await self.client.delete(next_uri)
                except httpx.HTTPError:
                    pass  # Original error is preserved; cancellation is best effort.
            raise
        return [dict(zip(columns, row)) for row in rows]

    async def close(self):
        await self.client.aclose()
