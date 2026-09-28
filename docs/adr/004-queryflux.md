# ADR-004: Existing QueryFlux for analytical reads

## Context
The submission should demonstrate query routing without rebuilding the upstream project or assuming unsupported engines.

## Options
Direct ClickHouse only; QueryFlux with embedded DuckDB; QueryFlux's native ClickHouse adapter.

## Decision
Inspect upstream README, configuration types, examples, and license; use the native ClickHouse adapter through Trino HTTP. Preserve explicit direct mode for the core demo. Only mark the route verified after an actual successful query.

## Consequences
QueryFlux remains an attributed external component. The original decision connected ClickHouse. The Compose extension now also connects embedded DuckDB over a bounded Parquet snapshot, using a sample-namespace SQL-regex rule; see [queryflux.md](../queryflux.md). Engine-native FINAL is encapsulated in views, and timestamps use explicit UTC strings for the tested wire path. Native integration is proven; container deployment is independently verified and documented in queryflux.md. No claim of multi-engine failover or Redis support.
