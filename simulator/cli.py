import argparse
import json
import math
import os
import signal
import time
from pathlib import Path

import redis

from shared.config import Settings
from simulator.config import SimulationConfig
from simulator.generator import Generator
from simulator.producer import KafkaProducer
from simulator.vehicle_factory import vehicles


def run(args: argparse.Namespace) -> dict:
    settings = Settings()
    config = SimulationConfig(seed=args.seed)
    if args.probabilities:
        config = SimulationConfig(
            seed=args.seed, probabilities=json.loads(args.probabilities.read_text())
        )
    generator = Generator(
        list(vehicles(args.vehicles, args.seed)), config, active_vehicles=args.active_vehicles
    )
    # Explicit deterministic showcase scenarios; normal stochastic simulation continues afterwards.
    if args.mode == "demo":
        for index, scenario in enumerate(
            (
                "IDLING",
                "SPEEDING",
                "HARSH_BRAKE",
                "ENGINE_FAULT",
                "DUPLICATE_EVENT",
                "OUT_OF_ORDER_EVENT",
                "NETWORK_RECOVERY_BURST",
                "HARSH_ACCELERATION",
            )
        ):
            if index < generator.active:
                generator.force(index, scenario)
    producer = metrics = output = None
    running = True

    def stop(*_):
        nonlocal running
        running = False

    handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    started, last_report, last_generated = time.monotonic(), time.monotonic(), 0
    emitted = 0
    failure = None
    cleanup_errors = []
    try:
        if args.sink == "kafka":
            producer = KafkaProducer(settings.kafka, settings.topic)
            metrics = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            output = args.output.open("w")
        while running and (args.duration == 0 or time.monotonic() - started < args.duration):
            # At most one second of readings per batch, even at very low rates.
            size = min(args.batch_size, args.rate)
            if args.duration:
                remaining = math.ceil(args.duration * args.rate) - generator.cursor
                if remaining <= 0:
                    break
                size = min(size, remaining)
            events = generator.batch(size, args.rate)
            emitted += len(events)
            if producer:
                producer.publish(events)
            if output:
                output.writelines(json.dumps(event) + "\n" for event in events)
            now = time.monotonic()
            if now - last_report >= 1:
                report = {
                    "generated": generator.generated,
                    "emitted": emitted,
                    "published": producer.published if producer else 0,
                    "errors": producer.errors if producer else 0,
                    "backpressure": producer.backpressure if producer else 0,
                    "generated_per_sec": (generator.generated - last_generated)
                    / (now - last_report),
                    "updated_at": time.time(),
                    "running": True,
                }
                if metrics:
                    metrics.set("metrics:simulator", json.dumps(report), ex=120)
                last_report, last_generated = now, generator.generated
            # Blocking producer naturally slows generation; never build an unbounded catch-up queue.
            due = started + generator.cursor / args.rate
            if args.duration:
                due = min(due, started + args.duration)
            while running and (delay := due - time.monotonic()) > 0:
                time.sleep(min(delay, 0.25))
        remaining = generator.flush()
        emitted += len(remaining)
        if producer:
            producer.publish(remaining)
        if output:
            output.writelines(json.dumps(event) + "\n" for event in remaining)
    except Exception as exc:
        failure = exc
    finally:
        # Flush failures must not erase the original cause or prevent a report.
        for resource in (output, producer):
            if resource:
                try:
                    resource.close()
                except Exception as exc:
                    if failure is None:
                        failure = exc
                    else:
                        cleanup_errors.append(type(exc).__name__)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    elapsed = time.monotonic() - started
    report = {
        "target_per_sec": args.rate,
        "registered": args.vehicles,
        "active_vehicles": generator.active,
        "generated": generator.generated,
        "emitted": emitted,
        "published": producer.published if producer else None,
        "errors": producer.errors if producer else 0,
        "error": type(failure).__name__ if failure else None,
        "cleanup_errors": cleanup_errors,
        "undelivered": producer.undelivered if producer else 0,
        "running": False,
        "backpressure": producer.backpressure if producer else 0,
        "duration_seconds": elapsed,
        "generated_per_sec": generator.generated / elapsed,
        "published_per_sec": producer.published / elapsed if producer else None,
        "sink": args.sink,
        "updated_at": time.time(),
    }
    if metrics:
        try:
            metrics.set("metrics:simulator", json.dumps(report), ex=120)
        except Exception as exc:
            failure = failure or exc
            report["error"] = type(failure).__name__
        finally:
            metrics.close()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if failure:
        raise failure
    return report


def parser():
    parser = argparse.ArgumentParser(description="Stateful ValeoSense telemetry simulator")
    parser.add_argument("--vehicles", type=int, default=int(os.getenv("VEHICLE_COUNT", "100000")))
    parser.add_argument("--active-vehicles", type=int, default=1000)
    parser.add_argument("--rate", type=int, default=int(os.getenv("EVENT_RATE", "1000")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BATCH_SIZE", "500")))
    parser.add_argument("--duration", type=float, default=60, help="0 runs until interrupted")
    parser.add_argument("--seed", type=int, default=int(os.getenv("SEED", "42")))
    parser.add_argument("--mode", choices=["demo", "load"], default="demo")
    parser.add_argument("--sink", choices=["kafka", "file"], default="kafka")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--probabilities", type=Path)
    return parser


if __name__ == "__main__":
    cli = parser()
    args = cli.parse_args()
    if (
        min(args.rate, args.batch_size, args.active_vehicles) < 1
        or not 1 <= args.vehicles <= 100000
        or not math.isfinite(args.duration)
        or args.duration < 0
    ):
        cli.error(
            "vehicles must be 1..100000; rate, batch size, active vehicles must be positive; "
            "duration must be finite and nonnegative"
        )
    if args.sink == "file" and not args.output:
        cli.error("--sink file requires --output")
    run(args)
