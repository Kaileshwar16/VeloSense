import json
import logging
import signal
import time

from confluent_kafka import Consumer

from processor.pipeline import Processor
from shared.config import Settings


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    processor = Processor(settings)
    # The prototype has one state owner. Fail closed rather than race detector state.
    lock = processor.live.lock("processor:owner", timeout=90, blocking=False)
    if not lock.acquire():
        raise RuntimeError("another processor owns state; horizontal workers are not enabled")
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka,
            "group.id": "valeosense-processor-v1",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "max.poll.interval.ms": 120000,
        }
    )
    consumer.subscribe([settings.topic])
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    last_lag = 0.0
    try:
        while running:
            lock.reacquire()
            messages = consumer.consume(num_messages=500, timeout=1)
            if any(message.error() for message in messages):
                raise RuntimeError("Kafka consumer reported a partition error")
            if messages:
                processor.process([message.value() for message in messages])
                for message in messages:
                    consumer.store_offsets(message=message)
                consumer.commit(asynchronous=False)
            if time.monotonic() - last_lag >= 5:
                lag = 0
                for partition in consumer.assignment():
                    _, high = consumer.get_watermark_offsets(partition, timeout=3)
                    positions = consumer.committed([partition], timeout=3)
                    lag += max(0, high - max(0, positions[0].offset))
                processor.counters["consumer_lag"] = lag if consumer.assignment() else None
                last_lag = time.monotonic()
            processor.metrics()
    except Exception:
        processor.counters["processor_errors"] += 1
        try:
            processor.metrics()
        finally:
            logging.exception(
                json.dumps({"event": "processor_failed", "offset_commit": "withheld"})
            )
        raise
    finally:
        consumer.close()
        lock.release()
        processor.analytics.close()
        processor.live.close()


if __name__ == "__main__":
    main()
