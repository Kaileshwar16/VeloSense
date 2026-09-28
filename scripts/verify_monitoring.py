"""Verify provisioned Grafana and actual Prometheus samples, without printing secrets."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from shared.config import Settings


def main():
    settings = Settings()
    with httpx.Client(
        base_url=os.getenv("GRAFANA_URL", "http://127.0.0.1:3001"),
        auth=("admin", os.getenv("GRAFANA_ADMIN_PASSWORD") or settings.api_key),
        timeout=10,
    ) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        dashboard = client.get("/api/dashboards/uid/valeosense-overview")
        dashboard.raise_for_status()
        panels = dashboard.json()["dashboard"]["panels"]
        assert len(panels) == 18, "dashboard provisioning incomplete"
        proxy = "/api/datasources/proxy/uid/valeosense-prometheus/api/v1/query"

        def query(expression):
            response = client.get(proxy, params={"query": expression})
            response.raise_for_status()
            payload = response.json()
            assert payload["status"] == "success", "Prometheus query failed"
            return payload["data"]["result"]

        deadline = time.monotonic() + 45
        while True:
            result = query('up{job="valeosense"}')
            if result and result[0]["value"][1] == "1":
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Exporter did not produce a successful Prometheus scrape")
            time.sleep(2)
        # Scrape success alone does not prove the exporter emitted useful data.
        for expression in ("valeosense_api_requests_total", "valeosense_processor_reporting"):
            assert query(expression), f"Missing metric: {expression}"
        for panel in panels:
            for target in panel["targets"]:
                query(target["expr"].replace("$__rate_interval", "1m"))
        if os.getenv("EXPECT_QUERYFLUX") == "1":
            native = query('up{job="queryflux"}')
            assert native and native[0]["value"][1] == "1", "QueryFlux scrape is down"
            for engine in ("ClickHouse", "DuckDb"):
                samples = query(
                    'sum(queryflux_queries_total{status="Success",engine_type="' + engine + '"})'
                )
                assert samples and float(samples[0]["value"][1]) > 0, (
                    f"No native successful queries for {engine}; run make verify-dual-engine first"
                )
        evidence = {
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "grafana_version": health.json()["version"],
            "dashboard_uid": "valeosense-overview",
            "panels": len(panels),
            "checks": [
                "authenticated Grafana health and dashboard",
                "provisioned Prometheus datasource proxy",
                "real exporter scrape up=1",
                "API and processor freshness metrics present",
                "all dashboard PromQL expressions accepted",
            ],
            "passed": True,
        }
        if os.getenv("EXPECT_QUERYFLUX") == "1":
            evidence["checks"].append("native QueryFlux scrape and both engine successes present")
    Path("artifacts/monitoring-smoke.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
