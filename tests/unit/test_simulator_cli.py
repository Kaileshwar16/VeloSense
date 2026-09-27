import json

import pytest

from simulator import cli


def test_failure_still_flushes_reports_and_closes_metrics(monkeypatch, tmp_path):
    class Producer:
        published = 0
        errors = 0
        backpressure = 2
        undelivered = 1
        closed = False

        def publish(self, events):
            raise TimeoutError("queue full")

        def close(self):
            self.closed = True
            raise RuntimeError("flush failed too")

    class Metrics:
        closed = False

        def set(self, *args, **kwargs):
            pass

        def close(self):
            self.closed = True

    producer, metrics = Producer(), Metrics()
    monkeypatch.setattr(cli, "KafkaProducer", lambda *args: producer)
    monkeypatch.setattr(cli.redis.Redis, "from_url", lambda *args, **kwargs: metrics)
    report_path = tmp_path / "new-directory" / "failed.json"
    args = cli.parser().parse_args(
        ["--vehicles", "1", "--duration", "1", "--report", str(report_path)]
    )
    with pytest.raises(TimeoutError, match="queue full"):
        cli.run(args)
    report = json.loads(report_path.read_text())
    assert producer.closed and metrics.closed
    assert report["error"] == "TimeoutError"
    assert report["cleanup_errors"] == ["RuntimeError"]
    assert report["backpressure"] == 2
    assert report["undelivered"] == 1
    assert report["running"] is False


def test_low_rate_caps_batch_and_honors_duration(monkeypatch, tmp_path):
    # Deterministic fake clock proves low-rate pacing without wall-clock sleeps.
    clock = [0.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    args = cli.parser().parse_args(
        [
            "--vehicles",
            "1",
            "--rate",
            "2",
            "--batch-size",
            "500",
            "--duration",
            "3",
            "--sink",
            "file",
            "--output",
            str(tmp_path / "events.jsonl"),
            "--mode",
            "load",
        ]
    )
    report = cli.run(args)
    assert report["generated"] == 6
    assert report["duration_seconds"] == 3
    assert report["generated_per_sec"] == 2


def test_seed_environment_is_used(monkeypatch):
    monkeypatch.setenv("SEED", "123")
    assert cli.parser().parse_args([]).seed == 123
