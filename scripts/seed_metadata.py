"""Idempotent seed: registry -> COPY staging -> metadata; initialize topic and analytics."""

import csv
from pathlib import Path

import psycopg
from confluent_kafka.admin import AdminClient, NewTopic

from shared.config import Settings
from shared.storage import ClickHouse
from simulator.vehicle_factory import write_registry


def main():
    settings = Settings()
    path = Path("data/vehicles.csv")
    if not path.exists():
        write_registry(path)
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 100000 or len({row["vehicle_id"] for row in rows}) != 100000:
        raise ValueError("registry must contain exactly 100000 unique vehicles")
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(Path("infra/postgres.sql").read_text())
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO fleets VALUES (%s,%s) ON CONFLICT DO NOTHING",
                [(f"F{i:03d}", f"Synthetic Fleet {i:03d}") for i in range(1, 101)],
            )
            cursor.execute("CREATE TEMP TABLE seed_vehicles (LIKE vehicles) ON COMMIT DROP")
            with cursor.copy("COPY seed_vehicles FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(list(row.values()))
            cursor.execute(
                "INSERT INTO vehicles SELECT * FROM seed_vehicles ON CONFLICT DO NOTHING"
            )
    store = ClickHouse(settings)
    store.initialize()
    store.close()
    admin = AdminClient({"bootstrap.servers": settings.kafka})
    futures = admin.create_topics(
        [
            NewTopic(
                settings.topic,
                num_partitions=6,
                replication_factor=1,
                config={"retention.ms": "86400000", "retention.bytes": "268435456"},
            )
        ],
        request_timeout=20,
    )
    for future in futures.values():
        try:
            future.result()
        except Exception as error:
            if "TOPIC_ALREADY_EXISTS" not in str(error):
                raise
    print("Seeded 100000 vehicles; initialized ClickHouse and six-partition telemetry topic.")


if __name__ == "__main__":
    main()
