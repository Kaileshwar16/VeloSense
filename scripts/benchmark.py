# ruff: noqa: E501
"""Measured, progressively increasing real Kafka load. Stop when the pipeline saturates."""

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil
import redis

from shared.config import Settings


def processor_metrics(client):
    value = client.get("metrics:processor")
    if not value:
        raise RuntimeError("processor metrics unavailable; start the processor first")
    metrics = json.loads(value)
    if time.time() - metrics["updated_at"] > 10:
        raise RuntimeError("processor heartbeat is stale")
    return metrics


def benchmark(rates: list[int], duration: int, output: Path):
    live = redis.Redis.from_url(Settings().redis_url, decode_responses=True)
    results = []
    for rate in rates:
        baseline = processor_metrics(live)
        if baseline.get("consumer_lag", 0) not in (0, None):
            raise RuntimeError("benchmark requires a drained topic and no other producer")
        report_path = Path(f"artifacts/benchmark-{rate}.json")
        started = time.monotonic()
        cpu_peak = memory_peak = 0
        stopped_for_memory = False
        command = [
            sys.executable,
            "-m",
            "simulator.cli",
            "--vehicles",
            "100000",
            "--active-vehicles",
            str(min(rate, 100000)),
            "--rate",
            str(rate),
            "--batch-size",
            "500",
            "--duration",
            str(duration),
            "--mode",
            "load",
            "--report",
            str(report_path),
        ]
        with Path(f"artifacts/benchmark-{rate}.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            sampler = psutil.Process(process.pid)
            sampler.cpu_percent()
            while process.poll() is None:
                try:
                    memory_peak = max(memory_peak, sampler.memory_info().rss)
                    cpu_peak = max(cpu_peak, sampler.cpu_percent())
                except psutil.NoSuchProcess:
                    break
                if live.info("memory")["used_memory"] > 220 * 1024 * 1024:
                    process.send_signal(signal.SIGTERM)
                    stopped_for_memory = True
                time.sleep(0.5)
        published_end = time.monotonic()
        if process.returncode != 0 or not report_path.exists():
            result = {
                "target_per_sec": rate,
                "error": "simulator failed; inspect stage log",
                "returncode": process.returncode,
                "stable": False,
            }
            results.append(result)
            break
        stage = json.loads(report_path.read_text())
        at_publish_end = processor_metrics(live)
        consumed_at_end = at_publish_end["consumed"] - baseline["consumed"]
        deadline = time.monotonic() + 45
        final = at_publish_end
        while (
            final["consumed"] - baseline["consumed"] < stage["published"]
            and time.monotonic() < deadline
        ):
            time.sleep(0.5)
            final = processor_metrics(live)
        elapsed = time.monotonic() - started
        consumed = final["consumed"] - baseline["consumed"]
        drain = time.monotonic() - published_end
        stable = (
            not stopped_for_memory
            and not stage["errors"]
            and stage["generated_per_sec"] >= rate * 0.9
            and consumed >= stage["published"]
            and drain < 5
            and final["processor_errors"] == baseline["processor_errors"]
        )
        result = {
            **stage,
            "consumed": consumed,
            "consumed_at_publish_end": consumed_at_end,
            "accepted": final["accepted"] - baseline["accepted"],
            "duplicates": final["duplicates_ignored"] - baseline["duplicates_ignored"],
            "validation_errors": final["validation_errors"] - baseline["validation_errors"],
            "processor_errors": final["processor_errors"] - baseline["processor_errors"],
            "end_to_end_seconds": elapsed,
            "drain_seconds": drain,
            "consumed_per_sec_including_startup_and_drain": consumed / elapsed,
            "simulator_peak_rss_bytes": memory_peak,
            "simulator_peak_cpu_percent": cpu_peak,
            "stopped_for_memory": stopped_for_memory,
            "stable": stable,
        }
        results.append(result)
        print(json.dumps(result), flush=True)
        # Progressively protect the laptop and avoid calling an overloaded target sustained.
        if not stable:
            break
        time.sleep(6)  # Allow the lag gauge to reflect committed offsets before next stage.
    report = {
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "real generator -> Kafka -> processor -> Redis + ClickHouse",
        "host": {"logical_cpus": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total},
        "stage_duration_requested_seconds": duration,
        "stability_rule": ">=90% generation target, all published consumed, <5s drain, no errors",
        "results": results,
        "unattempted_targets": rates[len(results) :],
        "maximum_stable_generated_per_sec": max(
            (r["generated_per_sec"] for r in results if r.get("stable")), default=0
        ),
        "maximum_stable_end_to_end_consumed_per_sec": max(
            (r["consumed_per_sec_including_startup_and_drain"] for r in results if r.get("stable")),
            default=0,
        ),
    }
    output.write_text(json.dumps(report, indent=2))
    lines = [
        "# Measured benchmark",
        "",
        f"Measured: {report['measured_at_utc']}",
        "",
        "Real Kafka delivery and both processor sinks. Single broker and single processor.",
        "This is a short laptop run, not a long-duration capacity or 100K/sec claim.",
        "",
        "| Target events/s | Generated/s | Published | Consumed | End-to-end consumed/s | Drain s | Stable |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in results:
        if "error" in row and row["error"]:
            lines.append(f"| {row['target_per_sec']} | failed | — | — | — | — | no |")
        else:
            lines.append(
                f"| {row['target_per_sec']} | {row['generated_per_sec']:.2f} | {row['published']} | {row['consumed']} | {row['consumed_per_sec_including_startup_and_drain']:.2f} | {row['drain_seconds']:.2f} | {row['stable']} |"
            )
    lines += [
        "",
        f"Unattempted targets after saturation: {report['unattempted_targets']}.",
        "",
        f"Maximum stable measured generation: {report['maximum_stable_generated_per_sec']:.2f} events/s.",
        f"Maximum stable measured full-path consumption including startup/drain: {report['maximum_stable_end_to_end_consumed_per_sec']:.2f} records/s.",
        "",
        "Published includes intentional duplicates; malformed payloads are counted as consumed and rejected.",
        "Generated measures canonical readings before duplicate injection. CPU/RSS describe the simulator process only.",
        "Processor counters are process-local. Run without another producer or processor restart.",
        "Stability threshold: generation >=90% target, all published records consumed, <5 seconds drain, no delivery/processor errors.",
        "Rates of 25K/50K/100K are targets, not claims. Stop at first unstable stage.",
        "",
        "Reproduce: `make benchmark` (15 seconds per attempted stage). Raw evidence: `benchmark_results.json`.",
        "Increasing sample length, repeating runs, and dedicated hardware are required before making capacity guarantees.",
    ]
    Path("docs/benchmark.md").write_text("\n".join(lines) + "\n")
    live.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rates", default="1000,10000,25000,50000,100000")
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"))
    args = parser.parse_args()
    rates = [int(value) for value in args.rates.split(",")]
    if args.duration < 5 or any(rate < 1 for rate in rates):
        parser.error("duration must be >=5 seconds and targets must be positive")
    benchmark(rates, args.duration, args.output)
