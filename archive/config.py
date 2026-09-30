import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ArchiveConfig:
    catalog_uri: str
    warehouse: str
    table: str = "valeosense.telemetry_archive"
    kafka: str = "localhost:19092"
    topic: str = "valeosense.telemetry.v1"
    batch_rows: int = 5000
    flush_seconds: int = 10

    def __post_init__(self):
        if not self.catalog_uri or not self.warehouse:
            raise ValueError("Iceberg catalog URI and warehouse are required")
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", self.table):
            raise ValueError("ICEBERG_TABLE must be namespace.table using lowercase identifiers")
        if not 1 <= self.batch_rows <= 10000 or not 1 <= self.flush_seconds <= 30:
            raise ValueError("Iceberg batch rows must be 1..10000 and flush seconds 1..30")

    @classmethod
    def from_env(cls):
        uri = os.getenv("ICEBERG_CATALOG_URI") or os.getenv("DATABASE_URL", "")
        # Reuse the application's psycopg 3 driver, not SQLAlchemy's psycopg2 default.
        if uri.startswith("postgresql://"):
            uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)
        return cls(
            catalog_uri=uri,
            warehouse=os.getenv("ICEBERG_WAREHOUSE", "file:///data/iceberg/warehouse"),
            table=os.getenv("ICEBERG_TABLE", "valeosense.telemetry_archive"),
            kafka=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"),
            topic=os.getenv("ICEBERG_TOPIC", "valeosense.telemetry.v1"),
            batch_rows=int(os.getenv("ICEBERG_BATCH_ROWS", "5000")),
            flush_seconds=int(os.getenv("ICEBERG_FLUSH_SECONDS", "10")),
        )
