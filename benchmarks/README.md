# Benchmarks

Benchmarks measure implemented code and are informational until stable runner
hardware and baselines exist. The suite measures application construction,
warm container resolution, and eager and lazy collection pipelines. Sync measurements time one
resolution per sample. Async measurements time batches of 64 awaited
resolutions on a persistent event loop to avoid timing loop creation; their
reported sample is a batch, not a per-resolution latency. Separate cases cover
sync and async cached singleton retrieval. Collection cases compare equivalent
standard-library operations and report traced peak memory for incremental and
materialized prefixes. Results are specific to the runner and do not establish
a performance claim.

As modules are implemented, organize measurements under container, HTTP,
database, concurrency, parallel processing, collections, pipelines, queues,
workflows, and memory. Record hardware, operating system, Python and
dependency versions, workload, concurrency, throughput, latency distributions,
and peak memory for every comparison.
