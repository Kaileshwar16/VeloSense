# ADR-002: Redis owns hot state

## Context
Live vehicle requests should not scan historical telemetry. Detectors need previous state and dedup markers.

## Options
One relational database; processor-only memory; Redis.

## Decision
Use Redis latest/alert keys, time-scored indexes, and dedup TTL markers. Persist detector episode state with the latest reading.

## Consequences
Fast point reads and restartable state without raw historical storage. Memory grows with dedup rate × TTL. A single state-owner lease limits horizontal scaling; Redis failure stops processing instead of committing offsets.
