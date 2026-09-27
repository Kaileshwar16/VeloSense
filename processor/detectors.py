"""Event-time detection; stale readings never roll back state or trigger alerts."""
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from shared.config import Settings
from shared.models import Telemetry


def transition(event: Telemetry, previous: dict | None, settings: Settings):
    current = event.model_dump(mode='json')
    previous_time = datetime.fromisoformat(previous['timestamp']) if previous else None
    dt = (event.timestamp - previous_time).total_seconds() if previous_time else 0
    # Seq resets across simulator runs are permitted when time advances. Equal timestamp
    # with a lower/equal seq and any backwards event time are historical-only.
    late = previous is not None and (dt < 0 or (dt == 0 and event.seq <= previous['seq']))
    row = {**current, 'idling_seconds': 0., 'estimated_fuel_l': 0.,
           'estimated_cost': 0., 'detected_types': [], 'late': late}
    if late:
        return previous, row, [], []
    continuous = previous is not None and 0 < dt <= settings.max_gap_seconds
    was_idle = bool(previous and previous['engine_on'] and previous['speed_kmh'] <= .5)
    idle = event.engine_on and event.speed_kmh <= .5
    start = previous.get('idle_start') if continuous and idle and was_idle else None
    if idle and start is None:
        start = current['timestamp']
    duration = max(0., (event.timestamp - datetime.fromisoformat(start)).total_seconds()) if start else 0.
    idle_delta = dt if continuous and idle and was_idle else 0.
    # Assumption: 0.8 L/h ICE idle burn, INR 100/L. EV fuel waste is zero.
    fuel = idle_delta / 3600 * settings.fuel_lph if event.fuel_pct is not None else 0.
    row.update(idling_seconds=idle_delta, estimated_fuel_l=fuel,
               estimated_cost=fuel * settings.fuel_price)
    acceleration = (event.speed_kmh - previous['speed_kmh']) / 3.6 / dt if continuous else 0.
    types = []
    if idle and duration > settings.idling_seconds:
        types.append('IDLING_ALERT')
    if event.speed_kmh > settings.speeding_kmh:
        types.append('SPEEDING')
    if acceleration < settings.brake_mps2:
        types.append('HARSH_BRAKE')
    if acceleration > settings.accel_mps2:
        types.append('HARSH_ACCELERATION')
    if event.dtc:
        types.append('ENGINE_FAULT')
    energy = event.fuel_pct if event.fuel_pct is not None else event.soc_pct
    if energy < 10:
        types.append('LOW_ENERGY')
    prior_alerts = previous.get('active_alerts', {}) if continuous else {}
    active, created = {}, []
    for kind in types:
        alert_start = start if kind == 'IDLING_ALERT' else current['timestamp']
        old = prior_alerts.get(kind)
        alert_id = old['alert_id'] if old else str(uuid5(NAMESPACE_URL, f'{event.event_id}:{kind}'))
        litres = duration / 3600 * settings.fuel_lph if event.fuel_pct is not None and kind == 'IDLING_ALERT' else 0.
        alert = {'alert_id': alert_id, 'event_id': str(event.event_id),
                 'vehicle_id': event.vehicle_id, 'fleet_id': event.fleet_id,
                 'timestamp': current['timestamp'], 'type': kind,
                 'start_timestamp': old['start_timestamp'] if old else alert_start,
                 'duration_seconds': duration if kind == 'IDLING_ALERT' else 0.,
                 'estimated_fuel_l': litres, 'estimated_cost': litres * settings.fuel_price,
                 'detail': ','.join(event.dtc) if kind == 'ENGINE_FAULT' else f'acceleration_mps2={acceleration:.2f}'}
        active[kind] = alert
        if not old:
            created.append(alert)
    row['detected_types'] = types
    current.update(idle_start=start, idle_duration_seconds=duration, active_alerts=active,
                   status='IDLING' if idle else 'MOVING' if event.speed_kmh > .5 else 'STOPPED')
    return current, row, created, list(active.values())
