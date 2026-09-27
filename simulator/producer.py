import json
import time

from confluent_kafka import Producer


class KafkaProducer:
    def __init__(self, servers: str, topic: str):
        self.topic = topic
        self.published = 0
        self.errors = 0
        self.backpressure = 0
        self.undelivered = 0
        self.producer = Producer(
            {
                "bootstrap.servers": servers,
                "enable.idempotence": True,
                "acks": "all",
                "linger.ms": 20,
                "batch.num.messages": 1000,
                "queue.buffering.max.messages": 20000,
                "queue.buffering.max.kbytes": 32768,
                "compression.type": "lz4",
                "delivery.timeout.ms": 30000,
            }
        )

    def delivered(self, error, message):
        if error:
            self.errors += 1
        else:
            self.published += 1

    def publish(self, events: list[dict]):
        for event in events:
            payload = json.dumps(event, separators=(",", ":")).encode()
            started = time.monotonic()
            while True:
                try:
                    self.producer.produce(
                        self.topic,
                        key=event["vehicle_id"].encode(),
                        value=payload,
                        on_delivery=self.delivered,
                    )
                    break
                except BufferError:
                    self.backpressure += 1
                    self.producer.poll(0.1)
                    if time.monotonic() - started > 30:
                        raise TimeoutError("Kafka queue full for 30s; stopped without silent drops")
            self.producer.poll(0)
            if self.errors:
                raise RuntimeError(f"{self.errors} Kafka delivery failures")

    def close(self):
        pending = self.producer.flush(35)
        self.undelivered = pending
        if pending or self.errors:
            raise RuntimeError(
                f"Kafka shutdown: {pending} undelivered; {self.errors} delivery errors"
            )
