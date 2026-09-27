# ADR-001: Redpanda for the streaming boundary

## Context
The one-day demo needs ordered per-vehicle delivery, observable backlog, and restartable consumers.

## Options
Direct synchronous writes; Kafka; Kafka-compatible Redpanda.

## Decision
Use one Redpanda broker with six partitions, key by vehicle_id, bounded retention, and manual consumer commits.

## Consequences
Small local deployment and real Kafka protocol. One replica is not high availability; development-mode durability settings are not production guarantees. Redpanda is a source-available external dependency.
