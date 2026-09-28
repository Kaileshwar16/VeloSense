"""Environment configuration; secrets stay out of logs and responses."""

import math
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    kafka: str = field(
        default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    )
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    clickhouse_url: str = field(
        default_factory=lambda: os.getenv("CLICKHOUSE_URL", "http://localhost:8123")
    )
    queryflux_url: str = field(
        default_factory=lambda: os.getenv("QUERYFLUX_URL", "http://localhost:18080")
    )
    analytics_route: str = field(default_factory=lambda: os.getenv("ANALYTICS_ROUTE", "direct"))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    cors: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    )
    idling_seconds: float = field(
        default_factory=lambda: float(os.getenv("IDLING_THRESHOLD_SECONDS", "20"))
    )
    fuel_lph: float = field(default_factory=lambda: float(os.getenv("IDLE_FUEL_LPH", "0.8")))
    fuel_price: float = field(
        default_factory=lambda: float(os.getenv("FUEL_PRICE_PER_LITRE", "100"))
    )
    speeding_kmh: float = field(
        default_factory=lambda: float(os.getenv("SPEEDING_THRESHOLD_KMH", "100"))
    )
    brake_mps2: float = field(
        default_factory=lambda: float(os.getenv("HARSH_BRAKE_THRESHOLD_MPS2", "-3"))
    )
    accel_mps2: float = field(
        default_factory=lambda: float(os.getenv("HARSH_ACCEL_THRESHOLD_MPS2", "3"))
    )
    online_seconds: int = 60
    dedup_seconds: int = 86400
    max_gap_seconds: int = 10
    max_analytics: int = field(
        default_factory=lambda: int(os.getenv("MAX_ANALYTICAL_QUERIES", "4"))
    )
    topic: str = "valeosense.telemetry.v1"
    duckdb_vehicle_limit: int = field(
        default_factory=lambda: int(os.getenv("DUCKDB_VEHICLE_LIMIT", "100"))
    )
    duckdb_window_minutes: int = field(
        default_factory=lambda: int(os.getenv("DUCKDB_WINDOW_MINUTES", "120"))
    )
    duckdb_max_age_seconds: int = field(
        default_factory=lambda: int(os.getenv("DUCKDB_MAX_AGE_SECONDS", "120"))
    )

    def __post_init__(self):
        positive = (self.idling_seconds, self.speeding_kmh, self.accel_mps2)
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("detector thresholds must be finite and positive")
        if not math.isfinite(self.brake_mps2) or self.brake_mps2 >= 0:
            raise ValueError("braking threshold must be finite and negative")
        if self.max_analytics < 1:
            raise ValueError("MAX_ANALYTICAL_QUERIES must be positive")
        if not 1 <= self.duckdb_vehicle_limit <= 1000:
            raise ValueError("DUCKDB_VEHICLE_LIMIT must be between 1 and 1000")
        if not 1 <= self.duckdb_window_minutes <= 1440:
            raise ValueError("DUCKDB_WINDOW_MINUTES must be between 1 and 1440")
        if not 1 <= self.duckdb_max_age_seconds <= 600:
            raise ValueError("DUCKDB_MAX_AGE_SECONDS must be between 1 and 600")
