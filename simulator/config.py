from dataclasses import dataclass, field

DEFAULT_PROBABILITIES = {
    "NORMAL": 0.68,
    "IDLING": 0.08,
    "SPEEDING": 0.04,
    "HARSH_BRAKE": 0.04,
    "HARSH_ACCELERATION": 0.025,
    "ENGINE_FAULT": 0.04,
    "LOW_ENERGY": 0.025,
    "OFFLINE": 0.015,
    "DUPLICATE_EVENT": 0.015,
    "OUT_OF_ORDER_EVENT": 0.015,
    "MALFORMED_EVENT": 0.005,
    "NETWORK_RECOVERY_BURST": 0.02,
}


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 42
    probabilities: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PROBABILITIES))
    scenario_seconds: int = 40
    idle_seconds: int = 45
    offline_seconds: int = 6
    speed_max: float = 180
    normal_acceleration_kmh_s: float = 3
    harsh_delta_kmh_s: float = 14
    max_buffered_per_vehicle: int = 20
    recovery_multiplier: int = 3

    def __post_init__(self):
        if set(self.probabilities) != set(DEFAULT_PROBABILITIES):
            raise ValueError("probabilities must specify every supported scenario")
        if any(value < 0 for value in self.probabilities.values()):
            raise ValueError("probabilities cannot be negative")
        if abs(sum(self.probabilities.values()) - 1) > 1e-6:
            raise ValueError("probabilities must sum to 1")
