# Benchmarks

Benchmarks measure implemented code. Treat results as informational until
stable runner hardware and baselines exist. The suite measures application
construction, route compilation, ASGI dispatch, Container resolution, Events,
HTTP clients, and eager and lazy Collections pipelines. Sync Container cases
time one resolution per sample. Async Container cases time batches of 64
awaited resolutions on a persistent event loop. This excludes loop creation.
Each async sample reports a batch, not per-resolution latency. Separate cases
cover sync and async cached singleton retrieval. Collection cases compare
standard-library operations and report traced peak memory for incremental
and materialized prefixes.

HTTP cases use an in-process ASGI test client and a local HTTP/1.1 server.
They compare pooled HTTPX2 and native Titanspan requests. They also measure
bounded fan-out and streaming versus buffering of a two-megabyte response.
The fan-out case sends 16 requests with a concurrency limit of four. Each
sample times one complete ASGI request, including the outbound calls. Memory
values count Python allocations reported by `tracemalloc`. They exclude native
allocations.

`make benchmark` writes a JSON report containing workload timings, host,
Python, and installed dependency versions. Results describe that run and do
not establish a performance claim.

## Local observation on 2026-11-27

One `make benchmark` run used an eight-core Apple M2 on macOS 27.0.1. It used
CPython 3.12.12, FastAPI 0.165.0, Starlette 1.10.0, HTTPX2 2.16.2, and
pytest-benchmark 5.3.1. The source was based on commit `a071b59` plus the
benchmark changes in this revision. The table reports medians and sample 95th
percentiles using the nearest-rank method. Streaming memory used three
independent samples.

| Workload | Samples | Median | 95th percentile |
| --- | ---: | ---: | ---: |
| Cold app startup and 24-route compilation | 22 | 46.820 ms | 117.795 ms |
| Warm native route dispatch | 347 | 3.483 ms | 11.810 ms |
| Warm injected route dispatch | 48 | 16.075 ms | 29.972 ms |
| Warm dispatch with native middleware | 75 | 16.560 ms | 24.747 ms |
| Pooled HTTPX2 request | 912 | 0.687 ms | 1.332 ms |
| Pooled Titanspan HTTP request | 1,064 | 0.838 ms | 1.512 ms |
| ASGI request with 16 outbound requests, limit four | 55 | 19.752 ms | 68.305 ms |

The HTTP baseline and adapter use the same small loopback response and pool
limits. This run showed a 0.151 ms median difference. A post-run process sample
showed substantial host activity. Treat the latency values as run artifacts,
not a stable comparison. The two-megabyte stream used 308,600 traced peak
bytes. Buffering the same response used 4,214,800 bytes. The three memory
samples are limited evidence for this payload and runtime.

Add new measurements only when implemented behavior has a meaningful
question. Record hardware, operating system, Python and dependency versions,
workload, concurrency, throughput, latency distributions, and peak memory
where useful. Keep deferred components out of the benchmark suite.
