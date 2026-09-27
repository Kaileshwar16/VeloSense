"""Small explicit SQL adapters. No telemetry is written to PostgreSQL."""

import json
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row

from shared.config import Settings


class ClickHouse:
    def __init__(self, settings: Settings):
        self.client = httpx.Client(base_url=settings.clickhouse_url, timeout=30)

    def execute(self, sql: str, params: dict | None = None) -> str:
        response = self.client.post("/", content=sql, params=params)
        response.raise_for_status()
        return response.text

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        return json.loads(self.execute(sql + " FORMAT JSON", params))["data"]

    def insert(self, table: str, rows: list[dict]):
        if table not in ("telemetry", "alerts"):
            raise ValueError("unsupported write table")
        if rows:
            payload = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
            self.execute(
                f"INSERT INTO valeosense.{table} FORMAT JSONEachRow\n" + payload,
                {"date_time_input_format": "best_effort"},
            )

    def initialize(self):
        for statement in Path("infra/clickhouse.sql").read_text().split(";"):
            if statement.strip():
                self.execute(statement)

    def close(self):
        self.client.close()


class Metadata:
    def __init__(self, settings: Settings):
        self.url = settings.database_url

    def query(self, sql: str, parameters: tuple = ()) -> list[dict]:
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5) as connection:
            return connection.execute(sql, parameters).fetchall()

    def vehicles(self, limit: int, offset: int, fleet_id: str | None = None):
        clause, params = ("WHERE fleet_id = %s", (fleet_id,)) if fleet_id else ("", ())
        return self.query(
            f"SELECT * FROM vehicles {clause} ORDER BY vehicle_id LIMIT %s OFFSET %s",
            params + (limit, offset),
        )

    def vehicle(self, vehicle_id: str):
        rows = self.query("SELECT * FROM vehicles WHERE vehicle_id = %s", (vehicle_id,))
        return rows[0] if rows else None
