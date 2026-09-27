# Failure demo: duplicate delivery and analytical replay

The automated real-service test is the shortest reproducible failure demonstration. Start the stack and then run:

```bash
RUN_INTEGRATION=1 EXPECT_QUERYFLUX=1 .venv/bin/pytest -q tests/integration/test_stack.py
```

Omit `EXPECT_QUERYFLUX=1` when running explicit direct mode. `RUN_INTEGRATION=1` makes unavailable services fail, rather than skip.

The test creates 25 consecutive idle readings for synthetic vehicle V100000, publishes them to the real Kafka topic, and publishes the final payload a second time with the same event_id, seq, and content. It waits for the real processor, checks Redis through the public API, confirms one active idling incident, and queries ClickHouse for exactly one event and one alert key. It then deliberately reinserts the same stored analytical row to represent a sink replay and verifies both the FINAL view and routed API history still return one reading per timestamp for the fixture.

This verifies practical duplicate suppression and analytical read idempotency. It does not prove all possible two-sink crash interleavings or exactly-once processing.

## Optional manual backlog demonstration

With a simulator running at 1K/sec:

```bash
docker compose --env-file .env -f infra/docker-compose.yml stop processor
# Wait about 10 seconds while the producer continues publishing.
docker compose --env-file .env -f infra/docker-compose.yml start processor
```

Live-state timestamps age while processing is stopped. After restart, committed Kafka offsets resume and the lag gauge eventually returns to zero. Do not call the last reported lag current while the processor heartbeat is stale. Kafka retention is finite; a long outage can exceed the demo's one-day / per-partition size limit. The automated submission evidence focuses on the duplicate test, not an unmeasured fault-tolerance SLA.
