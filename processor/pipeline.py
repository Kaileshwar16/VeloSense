import json
import time
from datetime import datetime, timezone

import redis
from pydantic import ValidationError

from processor.detectors import transition
from shared.config import Settings
from shared.models import Telemetry
from shared.storage import ClickHouse


class Processor:
    """One consumer process. Commit Kafka only after both sinks acknowledge.

    Redis commit is a batch transaction; ClickHouse replay is collapsed by FINAL
    on ReplacingMergeTree keys. This is practical idempotency, not a distributed
    exactly-once transaction. Single consumer process is deliberately enforced.
    """

    def __init__(self, settings: Settings, live=None, analytics=None):
        self.settings = settings
        self.live = live or redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.analytics = analytics or ClickHouse(settings)
        self.counters = {
            "consumed": 0,
            "accepted": 0,
            "duplicates_ignored": 0,
            "validation_errors": 0,
            "late_events": 0,
            "alerts_generated": 0,
            "processor_errors": 0,
            "consumer_lag": None,
        }
        self.last_metrics = time.monotonic()
        self.last_consumed = 0

    def process(self, payloads: list[bytes]):
        events = []
        duplicates = invalid = late_count = 0
        local_seen = set()
        for payload in payloads:
            try:
                event = Telemetry.model_validate_json(payload)
                if event.timestamp.timestamp() > time.time() + 30:
                    raise ValueError("event time more than 30 seconds in the future")
            except (ValidationError, ValueError):
                invalid += 1
                continue
            if event.event_id in local_seen:
                duplicates += 1
                continue
            local_seen.add(event.event_id)
            events.append(event)
        pipeline = self.live.pipeline(transaction=False)
        for event in events:
            pipeline.get(f"dedup:{event.event_id}")
            pipeline.get(f"vehicle:{event.vehicle_id}:latest")
        snapshots = pipeline.execute()
        states, rows, alerts, accepted_ids = {}, [], [], []
        for index, event in enumerate(events):
            if snapshots[2 * index]:
                duplicates += 1
                continue
            old = states.get(event.vehicle_id)
            if old is None and snapshots[2 * index + 1]:
                old = json.loads(snapshots[2 * index + 1])
            current, row, created, _ = transition(event, old, self.settings)
            if row["late"]:
                late_count += 1
            else:
                current["received_at"] = datetime.now(timezone.utc).isoformat()
                states[event.vehicle_id] = current
            rows.append(row)
            alerts.extend(created)
            accepted_ids.append(str(event.event_id))
        # Persist history before dedup markers. Replays retain deterministic primary keys.
        self.analytics.insert("telemetry", rows)
        self.analytics.insert("alerts", alerts)
        pipe = self.live.pipeline(transaction=True)
        for event_id in accepted_ids:
            pipe.set(f"dedup:{event_id}", "1", nx=True, ex=self.settings.dedup_seconds)
        now = time.time()
        for vehicle_id, state in states.items():
            pipe.set(f"vehicle:{vehicle_id}:latest", json.dumps(state), ex=3600)
            # Event-time freshness prevents an old recovery batch masquerading as online.
            event_time = datetime.fromisoformat(state["timestamp"]).timestamp()
            pipe.zadd("vehicles:online", {vehicle_id: event_time})
            pipe.zrem("vehicles:idling", vehicle_id)
            if state["status"] == "IDLING":
                pipe.zadd("vehicles:idling", {vehicle_id: event_time})
            pipe.set(
                f"alerts:{vehicle_id}", json.dumps(list(state["active_alerts"].values())), ex=3600
            )
            for kind in (
                "IDLING_ALERT",
                "SPEEDING",
                "HARSH_BRAKE",
                "HARSH_ACCELERATION",
                "ENGINE_FAULT",
                "LOW_ENERGY",
            ):
                member = f"{vehicle_id}:{kind}"
                pipe.zrem("alerts:active", member)
                if kind in state["active_alerts"]:
                    pipe.zadd("alerts:active", {member: event_time})
        for index in ("vehicles:online", "vehicles:idling", "alerts:active"):
            pipe.zremrangebyscore(index, "-inf", now - 3600)
        pipe.execute()
        self.counters["consumed"] += len(payloads)
        self.counters["accepted"] += len(rows)
        self.counters["duplicates_ignored"] += duplicates
        self.counters["validation_errors"] += invalid
        self.counters["late_events"] += late_count
        self.counters["alerts_generated"] += len(alerts)
        if events:
            self.counters["event_latency_ms"] = max(
                0, (now - max(e.timestamp.timestamp() for e in events)) * 1000
            )
        self.metrics()
        return {
            "accepted": len(rows),
            "duplicates": duplicates,
            "invalid": invalid,
            "alerts": len(alerts),
            "late": late_count,
        }

    def metrics(self):
        now = time.monotonic()
        elapsed = now - self.last_metrics
        if elapsed >= 1:
            self.counters["consumed_per_sec"] = (
                self.counters["consumed"] - self.last_consumed
            ) / elapsed
            self.last_metrics, self.last_consumed = now, self.counters["consumed"]
        self.live.set(
            "metrics:processor", json.dumps({**self.counters, "updated_at": time.time()}), ex=120
        )
