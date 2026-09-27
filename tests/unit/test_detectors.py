from datetime import datetime, timedelta
from uuid import uuid4

from processor.detectors import transition
from shared.config import Settings
from shared.models import Telemetry


def tick(base, seconds, **kwargs):
    return Telemetry.model_validate(
        {
            **base,
            "event_id": str(uuid4()),
            "seq": seconds + 1,
            "timestamp": datetime.fromisoformat(base["timestamp"]) + timedelta(seconds=seconds),
            **kwargs,
        }
    )


def test_idling_requires_duration_and_only_one_incident(event):
    settings = Settings(idling_seconds=20)
    previous = None
    incidents, seconds = [], 0
    for t in range(25):
        previous, row, alerts, active = transition(tick(event, t, speed_kmh=0), previous, settings)
        seconds += row["idling_seconds"]
        incidents.extend(alerts)
        if t <= 20:
            assert not alerts
    assert [a["type"] for a in incidents] == ["IDLING_ALERT"]
    assert seconds == 24
    assert active[0]["duration_seconds"] == 24


def test_gap_resets_idling_and_prevents_false_brake(event):
    settings = Settings(idling_seconds=20)
    previous, *_ = transition(tick(event, 0, speed_kmh=90), None, settings)
    previous, row, alerts, _ = transition(tick(event, 30, speed_kmh=0), previous, settings)
    assert not alerts
    assert row["idling_seconds"] == 0
    assert previous["idle_duration_seconds"] == 0


def test_brake_uses_speed_delta_not_scenario_label(event):
    settings = Settings()
    previous, *_ = transition(tick(event, 0, speed_kmh=82), None, settings)
    _, _, alerts, _ = transition(
        tick(event, 1, speed_kmh=60, event_type="NORMAL"), previous, settings
    )
    assert [a["type"] for a in alerts] == ["HARSH_BRAKE"]
    _, _, alerts, _ = transition(
        tick(event, 1, speed_kmh=80, event_type="HARSH_BRAKE"), previous, settings
    )
    assert alerts == []


def test_speed_fault_and_recovery(event):
    settings = Settings()
    previous, _, alerts, _ = transition(
        tick(event, 0, speed_kmh=125, dtc=["P0301"]), None, settings
    )
    assert {a["type"] for a in alerts} == {"SPEEDING", "ENGINE_FAULT"}
    previous, _, alerts, _ = transition(
        tick(event, 1, speed_kmh=125, dtc=["P0301"]), previous, settings
    )
    assert alerts == []
    previous, _, _, _ = transition(tick(event, 2, speed_kmh=99, dtc=[]), previous, settings)
    assert "SPEEDING" not in previous["active_alerts"]
    assert "ENGINE_FAULT" not in previous["active_alerts"]


def test_out_of_order_keeps_latest_and_no_alert(event):
    settings = Settings()
    previous, *_ = transition(tick(event, 2, speed_kmh=80), None, settings)
    current, row, alerts, _ = transition(
        tick(event, 1, speed_kmh=0, dtc=["P0301"]), previous, settings
    )
    assert current == previous
    assert row["late"]
    assert row["idling_seconds"] == 0
    assert alerts == []


def test_ev_has_no_fuel_cost_and_ice_estimate_is_explicit(event):
    settings = Settings(fuel_lph=0.8, fuel_price=100)
    for fuel, soc, expected in ((50, None, 0.8 / 3600 * 100), (None, 50, 0)):
        previous, *_ = transition(
            tick(event, 0, speed_kmh=0, fuel_pct=fuel, soc_pct=soc), None, settings
        )
        _, row, _, _ = transition(
            tick(event, 1, speed_kmh=0, fuel_pct=fuel, soc_pct=soc), previous, settings
        )
        assert abs(row["estimated_cost"] - expected) < 1e-10
