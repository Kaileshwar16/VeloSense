"""Deterministic in-process integration with explicitly in-memory test sinks.

Real external-service verification lives in tests/integration, not here.
"""

import json

import pytest

from processor.pipeline import Processor
from shared.config import Settings


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.sorted = {}

    def pipeline(self, transaction=True):
        return Pipeline(self)

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        if kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    def zadd(self, key, values):
        self.sorted.setdefault(key, {}).update(values)

    def zrem(self, key, member):
        self.sorted.setdefault(key, {}).pop(member, None)

    def zremrangebyscore(self, key, lower, upper):
        self.sorted[key] = {k: v for k, v in self.sorted.get(key, {}).items() if v > upper}


class Pipeline:
    def __init__(self, redis):
        self.redis, self.commands = redis, []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.commands.append((name, args, kwargs))
            return self

        return queue

    def execute(self):
        return [getattr(self.redis, name)(*args, **kwargs) for name, args, kwargs in self.commands]


class MemoryAnalytics:
    def __init__(self):
        self.rows = {"telemetry": [], "alerts": []}
        self.fail = False

    def insert(self, table, rows):
        if self.fail:
            raise RuntimeError("injected sink failure")
        self.rows[table].extend(rows)


def test_simulator_processor_dedup_and_latest_state(event):
    live, analytics = MemoryRedis(), MemoryAnalytics()
    processor = Processor(Settings(), live, analytics)
    payload = json.dumps({**event, "speed_kmh": 130, "dtc": ["P0301"]}).encode()
    result = processor.process([payload, payload, b"{invalid"])
    assert result == {"accepted": 1, "duplicates": 1, "invalid": 1, "alerts": 2, "late": 0}
    assert len(analytics.rows["telemetry"]) == 1
    assert json.loads(live.get(f"vehicle:{event['vehicle_id']}:latest"))["speed_kmh"] == 130
    assert processor.process([payload])["duplicates"] == 1
    assert len(analytics.rows["telemetry"]) == 1
    assert len(analytics.rows["alerts"]) == 2


def test_failed_sink_does_not_claim_dedup_or_advance_state(event):
    live, analytics = MemoryRedis(), MemoryAnalytics()
    processor = Processor(Settings(), live, analytics)
    analytics.fail = True
    payload = json.dumps(event).encode()
    with pytest.raises(RuntimeError, match="injected"):
        processor.process([payload])
    assert live.get(f"dedup:{event['event_id']}") is None
    assert live.get(f"vehicle:{event['vehicle_id']}:latest") is None
    analytics.fail = False
    assert processor.process([payload])["accepted"] == 1
