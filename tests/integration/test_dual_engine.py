"""Real canonical ClickHouse -> snapshot -> QueryFlux DuckDB and ClickHouse routes."""

import os

import pytest

from scripts.verify_dual_engine import verify

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1" or os.getenv("EXPECT_QUERYFLUX") != "1",
        reason="requires the two-engine Compose demo and reachable QueryFlux native metrics",
    ),
]


async def test_real_two_engine_routing_and_snapshot_lineage():
    evidence = await verify(add_fixture=True)
    assert evidence["passed"]
    assert len(evidence["seeded_event_ids"]) == 3
    assert evidence["native_success_count_delta"]["DuckDb"] > 0
    assert evidence["native_success_count_delta"]["ClickHouse"] > 0
