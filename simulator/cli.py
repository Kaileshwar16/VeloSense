import argparse
import json
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


def run(args) -> dict:
    settings = Settings()
    config = SimulationConfig(seed=args.seed)
    if args.probabilities:
        config = SimulationConfig(seed=args.seed, probabilities=json.loads(args.probabilities.read_text()))
    generator = Generator(list(vehicles(args.vehicles, args.seed)), config,
                          active_vehicles=args.active_vehicles)
    # Explicit deterministic showcase scenarios; normal stochastic simulation continues afterwards.
    if args.mode == 'demo':
        for index, scenario in enumerate(('IDLING', 'SPEEDING', 'HARSH_BRAKE', 'ENGINE_FAULT',
                                          'DUPLICATE_EVENT', 'OUT_OF_ORDER_EVENT',
                                          'NETWORK_RECOVERY_BURST', 'HARSH_ACCELERATION')):
            if index < generator.active:
                generator.force(index, scenario)
    producer = KafkaProducer(settings.kafka, settings.topic) if args.sink == 'kafka' else None
    metrics = redis.Redis.from_url(settings.redis_url, decode_responses=True) if producer else None
    output = args.output.open('w') if args.output else None
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    started, last_report, last_generated = time.monotonic(), time.monotonic(), 0
    emitted = 0
    error = None
    try:
        while running and (args.duration == 0 or time.monotonic() - started < args.duration):
            events = generator.batch(args.batch_size, args.rate)
            emitted += len(events)
            if producer:
                producer.publish(events)
            if output:
                output.writelines(json.dumps(event) + '\n' for event in events)
            now = time.monotonic()
            if now - last_report >= 1:
                report = {'generated': generator.generated, 'emitted': emitted,
                          'published': producer.published if producer else 0,
                          'errors': producer.errors if producer else 0,
                          'backpressure': producer.backpressure if producer else 0,
                          'generated_per_sec': (generator.generated - last_generated) / (now - last_report),
                          'updated_at': time.time()}
                if metrics:
                    metrics.set('metrics:simulator', json.dumps(report), ex=120)
                last_report, last_generated = now, generator.generated
            # Blocking producer naturally slows generation; never build an unbounded catch-up queue.
            due = started + generator.cursor / args.rate
            if due > time.monotonic():
                time.sleep(min(due - time.monotonic(), 1))
        remaining = generator.flush()
        emitted += len(remaining)
        if producer:
            producer.publish(remaining)
        if output:
            output.writelines(json.dumps(event) + '\n' for event in remaining)
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        if output:
            output.close()
        if producer:
            producer.close()
    elapsed = time.monotonic() - started
    report = {'target_per_sec': args.rate, 'registered': args.vehicles,
              'active_vehicles': generator.active, 'generated': generator.generated,
              'emitted': emitted, 'published': producer.published if producer else None,
              'errors': producer.errors if producer else 0, 'error': error,
              'backpressure': producer.backpressure if producer else 0,
              'duration_seconds': elapsed, 'generated_per_sec': generator.generated / elapsed,
              'published_per_sec': producer.published / elapsed if producer else None,
              'sink': args.sink, 'updated_at': time.time()}
    if metrics:
        metrics.set('metrics:simulator', json.dumps({**report, 'running': False}), ex=120)
        metrics.close()
    if args.report:
        args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


def parser():
    parser = argparse.ArgumentParser(description='Stateful ValeoSense telemetry simulator')
    parser.add_argument('--vehicles', type=int, default=int(os.getenv('VEHICLE_COUNT', '100000')))
    parser.add_argument('--active-vehicles', type=int, default=1000)
    parser.add_argument('--rate', type=int, default=int(os.getenv('EVENT_RATE', '1000')))
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('BATCH_SIZE', '500')))
    parser.add_argument('--duration', type=float, default=60, help='0 runs until interrupted')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--mode', choices=['demo', 'load'], default='demo')
    parser.add_argument('--sink', choices=['kafka', 'file'], default='kafka')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--probabilities', type=Path)
    return parser


if __name__ == '__main__':
    cli = parser()
    args = cli.parse_args()
    if min(args.rate, args.batch_size, args.active_vehicles) < 1 or args.duration < 0:
        cli.error('rate, batch size, active vehicles must be positive; duration must be nonnegative')
    if args.sink == 'file' and not args.output:
        cli.error('--sink file requires --output')
    run(args)
