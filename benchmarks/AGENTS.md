# Benchmark instructions

Follow root `AGENTS.md` and the performance requirements in
`docs/development/standards.md`. Benchmarks are evidence, not marketing.

- Record hardware, OS, Python and dependency versions, workload, concurrency,
  throughput, latency distribution, and peak memory.
- Compare Titanspan behavior with an appropriate underlying-library baseline.
- Keep benchmark inputs reproducible and representative. Separate setup time
  from measured work and disclose warm-up and repetitions.
- Do not add shared-runner wall-clock thresholds or alter measurements to hide
  regressions. Never fabricate or selectively omit results.
- Run `make benchmark` for informational microbenchmarks; use `make
  stress-test` only for behavior that warrants stress coverage.
