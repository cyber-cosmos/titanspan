---
name: performance-engineering
description: Design reproducible Titanspan performance experiments and review memory or throughput-sensitive changes.
---

# Performance engineering

## When to use

Use when a change claims or may affect latency, throughput, concurrency,
allocation, streaming, or large-dataset memory use.

## References

- Root and `benchmarks/AGENTS.md`
- `ARCHITECTURE.md` high-throughput design
- Relevant native library performance documentation
- Existing benchmark fixtures and `Makefile`

## Procedure

1. Define the workload, input size, data shape, concurrency, warm-up, and
   measured operation.
2. Choose a relevant baseline, preferably the underlying library's native
   API, and keep configuration equivalent.
3. Record hardware, operating system, Python, dependency versions, workload,
   concurrency, throughput, latency distributions, and peak memory.
4. Repeat enough runs to describe variability; separate setup from timed
   work.
5. Inspect for unbounded task creation, eager materialization, repeated copies,
   object churn, blocking I/O, or contention.
6. Report raw method and limitations. Keep shared-runner timing informational.

## Failure modes

- Inventing results or presenting an unverified optimization as measured.
- Comparing different workloads or hiding setup costs.
- Adding brittle CI timing thresholds on shared runners.
- Reporting only average latency when tail behavior matters.
- Using async syntax as evidence of CPU parallelism or scale.

## Validation

Run `make benchmark` only when the benchmark tooling and workload are
available. Run `make stress-test` for repeated behavior, not as a substitute
for a controlled performance experiment.

## Completion criteria

The workload and baseline are reproducible, results include the required
environment metadata, and claims stay within the evidence.
