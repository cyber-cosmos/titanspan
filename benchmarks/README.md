# Benchmarks

Benchmarks measure implemented code. Treat results as informational until
stable runner hardware and baselines exist. The suite measures application
construction, warm container resolution, and eager and lazy collection
pipelines. Sync cases time one resolution per sample. Async cases time batches
of 64 awaited resolutions on a persistent event loop. This excludes loop
creation. Each async sample reports a batch, not per-resolution latency.
Separate cases cover sync and async cached singleton retrieval. Collection
cases compare standard-library operations and report traced peak memory for
incremental and materialized prefixes. Results describe the runner; they do not
establish a performance claim.

As modules are implemented, organize measurements under container, HTTP,
database, concurrency, parallel processing, collections, pipelines, queues,
workflows, and memory. Record hardware, operating system, Python and
dependency versions, workload, concurrency, throughput, latency distributions,
and peak memory for every comparison.
