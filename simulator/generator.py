"""One scheduler, lightweight state, bounded publication buffers; no task per vehicle."""
import math
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from shared.models import Vehicle
from simulator.config import SimulationConfig
from simulator.vehicle_factory import REGIONS


@dataclass(slots=True)
class State:
    speed: float
    heading: float
    lat: float
    lon: float
    odometer: float
    energy: float
    temperature: float = 80
    seq: int = 0
    scenario: str = 'NORMAL'
    remaining: float = 0
    buffer: deque = field(default_factory=deque)
    held: dict | None = None
    last: dict | None = None
    low_episode: bool = False


class Generator:
    def __init__(self, registry: list[Vehicle], config: SimulationConfig | None = None,
                 start: datetime | None = None, active_vehicles: int | None = None):
        self.config = config or SimulationConfig()
        self.rng = random.Random(self.config.seed)
        self.start = start or datetime.now(timezone.utc)
        self.registry = registry
        self.active = min(active_vehicles or len(registry), len(registry))
        self.states: dict[str, State] = {}
        self.cursor = 0
        self.generated = 0
        self.backpressure = 0

    def state(self, vehicle: Vehicle) -> State:
        if vehicle.vehicle_id not in self.states:
            lat, lon = REGIONS[vehicle.home_region]
            self.states[vehicle.vehicle_id] = State(
                self.rng.uniform(35, 75), self.rng.uniform(0, 360), lat, lon,
                vehicle.odometer_km, self.rng.uniform(35, 95))
        return self.states[vehicle.vehicle_id]

    def force(self, index: int, scenario: str, seconds: float = 45):
        state = self.state(self.registry[index])
        state.scenario, state.remaining = scenario, seconds

    def tick(self, index: int, timestamp: datetime, dt: float = 1) -> list[dict]:
        vehicle = self.registry[index]
        s = self.state(vehicle)
        c = self.config
        if s.remaining <= 0 and not s.buffer:
            s.scenario = self.rng.choices(list(c.probabilities), list(c.probabilities.values()))[0]
            s.remaining = c.idle_seconds if s.scenario == 'IDLING' else c.scenario_seconds
            if s.scenario in ('OFFLINE', 'NETWORK_RECOVERY_BURST'):
                s.remaining = c.offline_seconds
        scenario = s.scenario
        s.remaining -= dt
        previous_speed = s.speed
        if scenario == 'IDLING':
            s.speed = max(0, s.speed - 10 * dt)
        elif scenario == 'SPEEDING':
            s.speed += max(-3 * dt, min(3 * dt, 125 - s.speed))
        elif scenario == 'HARSH_BRAKE':
            s.speed = max(0, s.speed - c.harsh_delta_kmh_s * dt)
        elif scenario == 'HARSH_ACCELERATION':
            s.speed += c.harsh_delta_kmh_s * dt
        else:
            s.speed += self.rng.uniform(-c.normal_acceleration_kmh_s, c.normal_acceleration_kmh_s) * dt
        s.speed = max(0, min(c.speed_max, s.speed))
        s.heading = (s.heading + self.rng.uniform(-3, 3) * dt) % 360
        distance = (s.speed + previous_speed) / 2 * dt / 3600
        s.odometer += distance
        s.lat = max(-85, min(85, s.lat + distance * math.cos(math.radians(s.heading)) / 111.32))
        s.lon = ((s.lon + distance * math.sin(math.radians(s.heading)) /
                  (111.32 * math.cos(math.radians(s.lat))) + 180) % 360) - 180
        # Low-energy scenario accelerates consumption gradually, never jumps randomly.
        consumption = distance * .015 + .0005 * dt
        if scenario == 'LOW_ENERGY':
            consumption += 2 * dt
        s.energy = max(0, min(100, s.energy - consumption))
        s.temperature = max(-40, min(140, s.temperature + (90 - s.temperature) * min(dt * .02, 1)))
        s.seq += 1
        event = {
            'event_id': str(uuid5(NAMESPACE_URL, f'{self.config.seed}:{self.start.isoformat()}:{vehicle.vehicle_id}:{s.seq}')),
            'vehicle_id': vehicle.vehicle_id, 'vin': vehicle.vin, 'fleet_id': vehicle.fleet_id,
            'timestamp': timestamp.isoformat(), 'seq': s.seq, 'lat': round(s.lat, 6),
            'lon': round(s.lon, 6), 'speed_kmh': round(s.speed, 2),
            'heading_deg': round(s.heading, 4) % 360, 'engine_on': True,
            'fuel_pct': round(s.energy, 4) if vehicle.fuel_type == 'ICE' else None,
            'soc_pct': round(s.energy, 4) if vehicle.fuel_type == 'EV' else None,
            'odometer_km': round(s.odometer, 4), 'engine_temp_c': round(s.temperature, 2),
            'dtc': ['P0301', 'P0420'] if scenario == 'ENGINE_FAULT' else [],
            'event_type': scenario, 'source_oem': vehicle.oem, 'schema_version': 1,
        }
        s.last = event
        self.generated += 1
        if scenario in ('OFFLINE', 'NETWORK_RECOVERY_BURST'):
            if s.remaining > 0 and len(s.buffer) < c.max_buffered_per_vehicle:
                s.buffer.append(event)
                return []
            if len(s.buffer) >= c.max_buffered_per_vehicle:
                self.backpressure += 1
            s.buffer.append(event)
            output = [s.buffer.popleft() for _ in range(min(len(s.buffer), c.recovery_multiplier))]
            if not s.buffer:
                s.scenario, s.remaining = 'NORMAL', c.scenario_seconds
            return output
        if scenario == 'OUT_OF_ORDER_EVENT':
            if s.held is None:
                s.held = event
                return []
            output, s.held = [event, s.held], None
            return output
        if scenario == 'DUPLICATE_EVENT':
            return [event, dict(event)]
        if scenario == 'MALFORMED_EVENT':
            return [{**event, 'speed_kmh': 'invalid'}]
        return [event]

    def batch(self, size: int, rate: float) -> list[dict]:
        output = []
        dt = self.active / rate
        for _ in range(size):
            tick = self.cursor
            output.extend(self.tick(tick % self.active, self.start + timedelta(seconds=tick / rate), dt))
            self.cursor += 1
        return output

    def flush(self) -> list[dict]:
        output = []
        for state in self.states.values():
            if state.held:
                output.append(state.held)
                state.held = None
            output.extend(state.buffer)
            state.buffer.clear()
        return output
