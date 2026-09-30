"""Iceberg data and Kafka checkpoints are published in one catalog transaction."""

from dataclasses import dataclass
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError
from pyiceberg.catalog import load_catalog
from pyiceberg.io.pyarrow import schema_to_pyarrow
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DoubleType,
    IntegerType,
    ListType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

from archive.config import ArchiveConfig
from shared.models import Telemetry

PREFIX = "valeosense.kafka.next-offset."
START_PREFIX = "valeosense.kafka.start-offset."
SOURCE_TOPIC = "valeosense.kafka.topic"
MAX_BATCH_BYTES = 32 * 1024 * 1024


def archive_schema():
    columns = [
        ("event_id", StringType()),
        ("vehicle_id", StringType()),
        ("vin", StringType()),
        ("fleet_id", StringType()),
        ("timestamp", TimestamptzType()),
        ("seq", LongType()),
        ("lat", DoubleType()),
        ("lon", DoubleType()),
        ("speed_kmh", DoubleType()),
        ("heading_deg", DoubleType()),
        ("engine_on", BooleanType()),
        ("fuel_pct", DoubleType()),
        ("soc_pct", DoubleType()),
        ("odometer_km", DoubleType()),
        ("engine_temp_c", DoubleType()),
        ("dtc", ListType(element_id=100, element=StringType(), element_required=True)),
        ("event_type", StringType()),
        ("source_oem", StringType()),
        ("schema_version", IntegerType()),
        ("source_topic", StringType()),
        ("source_partition", IntegerType()),
        ("source_offset", LongType()),
        ("received_at", TimestamptzType()),
        ("valid", BooleanType()),
        ("validation_error", StringType()),
        ("raw_payload", BinaryType()),
    ]
    required = {"source_topic", "source_partition", "source_offset", "received_at", "valid"}
    return Schema(
        *[
            NestedField(i, name, kind, required=name in required)
            for i, (name, kind) in enumerate(columns, 1)
        ]
    )


def catalog_for(config: ArchiveConfig):
    return load_catalog(
        "valeosense_archive",
        type="sql",
        uri=config.catalog_uri,
        warehouse=config.warehouse,
        **{"py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO"},
    )


def open_table(config: ArchiveConfig, *, create=False):
    catalog = catalog_for(config)
    if create:
        catalog.create_namespace_if_not_exists(config.table.split(".")[0])
        schema = archive_schema()
        table = catalog.create_table_if_not_exists(
            config.table,
            schema=schema,
            partition_spec=PartitionSpec(
                PartitionField(
                    source_id=schema.find_field("received_at").field_id,
                    field_id=1000,
                    transform=DayTransform(),
                    name="received_day",
                )
            ),
            properties={
                "format-version": "2",
                "write.parquet.compression-codec": "zstd",
                # Recompute checkpoints after a conflict instead of rebasing an append.
                "commit.retry.num-retries": "0",
                SOURCE_TOPIC: config.topic,
            },
        )
    else:
        table = catalog.load_table(config.table)
    if table.properties.get(SOURCE_TOPIC) != config.topic:
        raise ValueError("Iceberg table source topic differs from configured topic")
    return table


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    payload: bytes | None
    timestamp_ms: int

    @classmethod
    def from_message(cls, message):
        return cls(
            message.topic(),
            message.partition(),
            message.offset(),
            message.value(),
            message.timestamp()[1],
        )


def record_row(record: Record):
    row = {
        "source_topic": record.topic,
        "source_partition": record.partition,
        "source_offset": record.offset,
        "received_at": datetime.fromtimestamp(record.timestamp_ms / 1000, timezone.utc)
        if record.timestamp_ms >= 0
        else datetime.now(timezone.utc),
        "raw_payload": record.payload,
        "valid": False,
    }
    try:
        telemetry = Telemetry.model_validate_json(record.payload or b"")
        if telemetry.seq > 2**63 - 1:
            raise OverflowError("seq exceeds Iceberg long range")
        row.update(telemetry.model_dump())
        row["event_id"] = str(telemetry.event_id)
        row["valid"] = True
    except ValidationError as error:
        # Keep the exact raw bytes but never copy potentially sensitive values to errors/logs.
        row["validation_error"] = ",".join(sorted({e["type"] for e in error.errors()}))
    except OverflowError:
        row["validation_error"] = "seq_out_of_range"
    return row


def checkpoint(table, partition: int) -> int | None:
    value = table.properties.get(f"{PREFIX}{partition}")
    return int(value) if value is not None else None


def append_records(table, records: list[Record]) -> dict:
    """One ordered batch from one exclusive consumer; replay by Kafka identity is a no-op.

    Logical duplicates at different Kafka offsets remain in this raw archive.
    Any exception must stop the consumer, so a fresh table is loaded before retry.
    """
    if sum(len(record.payload or b"") for record in records) > MAX_BATCH_BYTES:
        raise ValueError("archive batch exceeds 32 MiB")
    table.refresh()
    next_offsets, starts, rows = {}, {}, []
    previous = {}
    for record in records:
        if record.topic != table.properties[SOURCE_TOPIC]:
            raise ValueError("batch source topic differs from archive topic")
        if record.partition < 0 or record.offset < 0:
            raise ValueError("invalid Kafka partition or offset")
        if record.partition in previous and record.offset < previous[record.partition]:
            raise ValueError("Kafka partition records must be ordered")
        previous[record.partition] = record.offset
        lower = next_offsets.get(record.partition, checkpoint(table, record.partition))
        if lower is not None and record.offset < lower:
            continue
        rows.append(record_row(record))
        if f"{START_PREFIX}{record.partition}" not in table.properties:
            starts.setdefault(record.partition, record.offset)
        next_offsets[record.partition] = record.offset + 1
    if rows:
        data = pa.Table.from_pylist(rows, schema=schema_to_pyarrow(table.schema()))
        with table.transaction() as transaction:
            transaction.append(data)
            transaction.set_properties({f"{PREFIX}{p}": str(n) for p, n in next_offsets.items()})
            transaction.set_properties({f"{START_PREFIX}{p}": str(n) for p, n in starts.items()})
    return {
        "written": len(rows),
        "invalid": sum(not row["valid"] for row in rows),
        "replayed": len(records) - len(rows),
        "next_offsets": next_offsets,
    }
