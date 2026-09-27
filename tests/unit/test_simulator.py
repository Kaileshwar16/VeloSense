import csv
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from shared.models import Telemetry
from simulator.config import DEFAULT_PROBABILITIES, SimulationConfig
from simulator.generator import Generator
from simulator.vehicle_factory import vehicles, write_registry

START = datetime(2026, 9, 27, tzinfo=timezone.utc)


def generator(count=1):
    return Generator(list(vehicles(count)), start=START)


def test_registry_exact_100000_and_reproducible(tmp_path):
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    write_registry(first)
    write_registry(second)
    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    rows = list(csv.DictReader(first.open()))
    assert len(rows) == 100000
    assert len({row["vehicle_id"] for row in rows}) == 100000
    assert len({row["vin"] for row in rows}) == 100000
    assert rows[0]["vehicle_id"] == "V000001"
    assert rows[-1]["vehicle_id"] == "V100000"
    assert all(len(row["vin"]) == 17 for row in rows)


def test_canonical_bounds_smoothness_and_energy():
    g = generator(20)
    for index in range(20):
        g.force(index, "NORMAL", 200)
        readings = [g.tick(index, START + timedelta(seconds=t))[0] for t in range(100)]
        for previous, event in zip(readings, readings[1:]):
            Telemetry.model_validate(event)
            assert abs(event["speed_kmh"] - previous["speed_kmh"]) <= 3.01
            assert event["odometer_km"] >= previous["odometer_km"]
            assert (event["fuel_pct"] is None) != (event["soc_pct"] is None)
            energy = event["fuel_pct"] if event["fuel_pct"] is not None else event["soc_pct"]
            assert 0 <= energy <= 100


def test_seed_and_start_deterministic():
    assert generator(10).batch(100, 10) == generator(10).batch(100, 10)


def test_duplicate_preserves_entire_payload():
    g = generator()
    g.force(0, "DUPLICATE_EVENT")
    output = g.tick(0, START)
    assert len(output) == 2
    assert output[0] == output[1]


def test_publication_reorders_actual_events():
    g = generator()
    g.force(0, "OUT_OF_ORDER_EVENT")
    assert g.tick(0, START) == []
    output = g.tick(0, START + timedelta(seconds=1))
    assert [event["seq"] for event in output] == [2, 1]
    assert output[0]["timestamp"] > output[1]["timestamp"]


def test_idling_persists_and_faults_persist():
    g = generator()
    g.force(0, "IDLING", 60)
    events = [g.tick(0, START + timedelta(seconds=t))[0] for t in range(50)]
    assert all(e["engine_on"] and e["speed_kmh"] == 0 for e in events[10:])
    g.force(0, "ENGINE_FAULT")
    assert all(g.tick(0, START + timedelta(seconds=60 + t))[0]["dtc"] for t in range(5))


def test_braking_reduces_speed_over_multiple_readings():
    g = generator()
    g.state(g.registry[0]).speed = 82
    g.force(0, "HARSH_BRAKE")
    speeds = [g.tick(0, START + timedelta(seconds=t))[0]["speed_kmh"] for t in range(5)]
    assert speeds == [68, 54, 40, 26, 12]


def test_offline_buffers_then_recovers_without_loss():
    g = generator()
    g.force(0, "NETWORK_RECOVERY_BURST", 6)
    output = [g.tick(0, START + timedelta(seconds=t)) for t in range(10)]
    assert all(not batch for batch in output[:5])
    assert max(map(len, output)) == 3
    events = [event for batch in output for event in batch] + g.flush()
    assert sorted(e["seq"] for e in events) == list(range(1, 11))
    assert all(len(s.buffer) <= g.config.max_buffered_per_vehicle for s in g.states.values())


def test_malformed_is_invalid_and_delay_flush_preserves_tail():
    g = generator()
    g.force(0, "MALFORMED_EVENT")
    with pytest.raises(ValidationError):
        Telemetry.model_validate(g.tick(0, START)[0])
    g.force(0, "OUT_OF_ORDER_EVENT")
    assert g.tick(0, START) == []
    assert len(g.flush()) == 1
    assert g.flush() == []


def test_probability_validation():
    with pytest.raises(ValueError):
        SimulationConfig(probabilities={**DEFAULT_PROBABILITIES, "NORMAL": 2})


@pytest.mark.parametrize(
    "field,value",
    [
        ("lat", 91),
        ("speed_kmh", -1),
        ("fuel_pct", 101),
        ("timestamp", "2026-09-27T00:00:00"),
        ("speed_kmh", float("nan")),
    ],
)
def test_schema_rejects_invalid(event, field, value):
    with pytest.raises(ValidationError):
        Telemetry.model_validate({**event, field: value})
