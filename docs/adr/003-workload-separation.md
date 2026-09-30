# ADR-003: Separate metadata and telemetry

## Context
Fleet identities need relational constraints; telemetry needs batched writes, scans, and retention.

## Options
PostgreSQL for all data; ClickHouse for everything; specialized stores.

## Decision
PostgreSQL stores fleets/vehicles/configuration schema; ClickHouse stores validated events and incidents. MergeTree is partitioned by month and ordered by vehicle/time/event ID. FINAL views collapse replayed keys.

## Consequences
Live, metadata, and analytical workloads use independent paths. There is no distributed transaction across Redis and ClickHouse. Monthly partitions and a 30-day TTL are local demo choices; an optional independent Kafka-to-Iceberg archive now retains raw records beyond warm TTL (see ADR-005).
