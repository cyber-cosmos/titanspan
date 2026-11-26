---
title: "Concurrency"
---

<span id="concurrency"></span>

Structured concurrency APIs are planned. The design favors bounded task
groups, cancellation propagation, backpressure, and graceful shutdown. AnyIO is
the selected future foundation; no Titanspan concurrency pool is implemented.

Do not treat async I/O as CPU parallelism. CPU-heavy work and distributed jobs
will use separate process and queue integrations when those modules are built.
See [ADR 0008](/titanspan/architecture/decisions/0008-structured-concurrency/).
