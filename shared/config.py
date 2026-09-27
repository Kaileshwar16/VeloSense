"""Environment configuration; secrets stay out of logs and responses."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    redis_url: str = field(default_factory=lambda: os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    kafka: str = field(default_factory=lambda: os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:19092'))
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', ''))
    clickhouse_url: str = field(default_factory=lambda: os.getenv('CLICKHOUSE_URL', 'http://localhost:8123'))
    queryflux_url: str = field(default_factory=lambda: os.getenv('QUERYFLUX_URL', 'http://localhost:18080'))
    analytics_route: str = field(default_factory=lambda: os.getenv('ANALYTICS_ROUTE', 'direct'))
    api_key: str = field(default_factory=lambda: os.getenv('API_KEY', ''))
    debug: bool = field(default_factory=lambda: os.getenv('DEBUG', 'false').lower() == 'true')
    cors: list[str] = field(default_factory=lambda: os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(','))
    idling_seconds: float = field(default_factory=lambda: float(os.getenv('IDLING_THRESHOLD_SECONDS', '20')))
    fuel_lph: float = field(default_factory=lambda: float(os.getenv('IDLE_FUEL_LPH', '0.8')))
    fuel_price: float = field(default_factory=lambda: float(os.getenv('FUEL_PRICE_PER_LITRE', '100')))
    speeding_kmh: float = 100
    brake_mps2: float = -3
    accel_mps2: float = 3
    online_seconds: int = 60
    dedup_seconds: int = 86400
    max_gap_seconds: int = 10
    max_analytics: int = field(default_factory=lambda: int(os.getenv('MAX_ANALYTICAL_QUERIES', '4')))
    topic: str = 'valeosense.telemetry.v1'
