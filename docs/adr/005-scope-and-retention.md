# ADR-005: Protect a working demo

## Context
One day and a memory-constrained laptop make a large infrastructure stack risky.

## Options
Flink/Spark, Kubernetes, Iceberg, MinIO and Grafana immediately; or bounded Python processing with JSON metrics.

## Decision
Use a single processor, polling dashboard, JSON metrics, no result cache, and semaphore-protected analytics. Keep optional services in independent Compose profiles; defer orchestration beyond Compose.

An optional monitoring profile now adds Prometheus and a provisioned Grafana
dashboard over the JSON metrics API. It is disabled in the default stack and can
be stopped independently, preserving the original bounded demo scope.

## Consequences
The optional Iceberg profile added on 2026-09-30 consumes Kafka independently and
stores raw records in daily Iceberg/Parquet partitions with a PostgreSQL catalog.
It supports atomic archive checkpoints and snapshot reads. One advisory-lock owner
keeps checkpoint recovery simple. The default warehouse is a persistent local
volume; S3 is configurable but unverified. See [iceberg.md](../iceberg.md).

Warm history still expires by TTL. The archive covers only Kafka records available
when its consumer starts and keeps up with retention; there is no ClickHouse
backfill or cross-store transaction. Automatic compaction, snapshot expiration,
schema migration tooling and QueryFlux archive routing remain deferred.
