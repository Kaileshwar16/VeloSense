# ADR-005: Protect a working demo

## Context
One day and a memory-constrained laptop make a large infrastructure stack risky.

## Options
Flink/Spark, Kubernetes, Iceberg, MinIO and Grafana immediately; or bounded Python processing with JSON metrics.

## Decision
Use a single processor, polling dashboard, JSON metrics, no result cache, and semaphore-protected analytics. Defer cold storage and all orchestration beyond Compose.

## Consequences
The running system is measurable and understandable. Warm history is deleted by TTL rather than archived. Future Parquet export can be upgraded to Iceberg for schema evolution, snapshots, time travel, atomic metadata, and multi-engine analytics. Those capabilities are not implemented here.
