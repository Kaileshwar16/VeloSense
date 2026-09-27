# Measured benchmark

Measured: 2026-09-27T14:38:40Z

Real Kafka delivery and both processor sinks. Single broker and single processor.
This is a short laptop run, not a long-duration capacity or 100K/sec claim.

| Target events/s | Generated/s | Published | Consumed | End-to-end consumed/s | Drain s | Stable |
|---:|---:|---:|---:|---:|---:|:---:|
| 1000 | 999.73 | 15270 | 15270 | 896.18 | 0.50 | True |
| 10000 | 9996.21 | 152595 | 152595 | 2899.28 | 36.09 | False |

Unattempted targets after saturation: [25000, 50000, 100000].

Maximum stable measured generation: 999.73 events/s.
Maximum stable measured full-path consumption including startup/drain: 896.18 records/s.

Published includes intentional duplicates; malformed payloads are counted as consumed and rejected.
Generated measures canonical readings before duplicate injection. CPU/RSS describe the simulator process only.
Processor counters are process-local. Run without another producer or processor restart.
Stability threshold: generation >=90% target, all published records consumed, <5 seconds drain, no delivery/processor errors.
Rates of 25K/50K/100K are targets, not claims. Stop at first unstable stage.

Reproduce: `make benchmark` (15 seconds per attempted stage). Raw evidence: `benchmark_results.json`.
Increasing sample length, repeating runs, and dedicated hardware are required before making capacity guarantees.
