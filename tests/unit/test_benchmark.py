import json
import time

import pytest

from scripts import benchmark
from scripts.benchmark import require_idle, stable_stage


@pytest.mark.parametrize("lag", [None, 1])
def test_benchmark_rejects_unknown_or_nonzero_lag(lag):
    with pytest.raises(RuntimeError, match="known zero"):
        require_idle(None, {"consumer_lag": lag})


def test_benchmark_rejects_an_existing_producer():
    class Live:
        def get(self, key):
            return json.dumps({"updated_at": time.time(), "running": True})

    with pytest.raises(RuntimeError, match="existing simulator"):
        require_idle(Live(), {"consumer_lag": 0})


@pytest.mark.parametrize(
    "consumed,instance,expected",
    [(100, "one", True), (101, "one", False), (99, "one", False), (100, "two", False)],
)
def test_stable_requires_exact_consumption_and_same_processor(consumed, instance, expected):
    stage = {"errors": 0, "generated_per_sec": 100, "published": 100}
    baseline = {"consumed": 0, "instance_id": "one", "processor_errors": 0}
    final = {"consumed": consumed, "instance_id": instance, "processor_errors": 0}
    assert stable_stage(stage, baseline, final, 100, 0.5, False) is expected


def test_wait_for_idle_allows_lag_gauge_to_catch_up(monkeypatch):
    reports = iter([{"consumer_lag": 10}, {"consumer_lag": None}, {"consumer_lag": 0}])
    monkeypatch.setattr(benchmark, "processor_metrics", lambda live: next(reports))
    monkeypatch.setattr(benchmark.time, "sleep", lambda seconds: None)

    class Live:
        def get(self, key):
            return None

    assert benchmark.wait_for_idle(Live()) == {"consumer_lag": 0}
