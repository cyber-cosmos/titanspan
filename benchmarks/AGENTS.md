# Benchmark instructions

Follow root `AGENTS.md` and
[`docs/src/content/docs/development/standards.md`](../docs/src/content/docs/development/standards.md). Benchmarks
provide reproducible evidence; they do not make unsupported product claims.

- State the workload, data shape, warm-up, concurrency, and measured
  operation. Separate setup from timed work.
- Compare with the underlying library's native API when that is a useful
  baseline. Keep workload and configuration equivalent.
- Record hardware, OS, Python and dependency versions, throughput, latency
  distribution, concurrency, and peak memory when reporting results.
- Keep timing informational on shared CI runners. Never fabricate results or
  alter workload parameters to conceal regressions.
- Type and document benchmark code like production code. Use comments for
  measurement decisions, not to narrate benchmark fixture calls.
- Run `make benchmark`, `make python-standards`, `make types`, and `make check`
  for relevant changes.
