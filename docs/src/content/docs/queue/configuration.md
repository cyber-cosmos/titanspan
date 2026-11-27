---
title: "Queue configuration"
description: "Configure application-owned queue connections and limits."
---

Queue reads settings from the active Config repository. Application
construction validates configuration but does not open broker connections.

## Configure connections

The following example uses Redis Streams for queued jobs and keeps the
synchronous connection available for local execution.

```python
from titanspan.foundation import Application
from titanspan.queue import QueueServiceProvider


application = Application(
    config={
        "app": {"name": "documents"},
        "queue": {
            "default_connection": "redis",
            "default_queue": "default",
            "namespace": "documents-production",
            "connections": {
                "sync": {"driver": "sync"},
                "disabled": {"driver": "null"},
                "redis": {
                    "driver": "redis_stream",
                    "options": {
                        "url": "redis://127.0.0.1:6379/0",
                        "idle_timeout_ms": 600_000,
                        "unacknowledged_lock_timeout_seconds": 900,
                    },
                },
            },
            "max_payload_bytes": 1_000_000,
            "max_payload_depth": 64,
            "worker_concurrency": 16,
            "prefetch": 0,
            "default_tries": 1,
            "batch_history_limit": 1024,
        },
    },
    service_providers=(
        QueueServiceProvider(jobs=(ProcessDocument,)),
    ),
)
```

Replace the example URL with a trusted deployment setting. Do not commit
credentials. Queue configuration representations redact backend options.

`namespace` separates the application's physical broker keys. Use the same
namespace for producers and workers in one deployment. Use different
namespaces for isolated environments that share a broker.

The connection name and logical queue also form the physical Queue name.
Two named connections that share a Redis URL do not consume each other's
messages.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `default_connection` | `sync` | Connection used when a job has no selection. |
| `default_queue` | `default` | Logical queue used when a job has no selection. |
| `namespace` | Derived from `app.name` | Application prefix for broker keys. |
| `max_payload_bytes` | `1000000` | Maximum encoded job envelope size. |
| `max_payload_depth` | `64` | Maximum nested object or array depth in each job payload. Values must be 1 through 256. |
| `worker_concurrency` | `16` | Maximum active async handlers per worker. |
| `prefetch` | `0` | Additional messages permitted beyond active capacity. |
| `default_tries` | `1` | Total attempts when a job has no `tries` override. |
| `batch_history_limit` | `1024` | Retained local batch snapshots. Values must be 1 through 10000. |
| `schedule_poll_interval` | `1.0` seconds | Taskiq schedule-source refresh interval. |
| `schedule_loop_interval` | `1.0` seconds | Taskiq schedule loop interval. |

Redis result storage accepts two optional connection settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `result_ttl_seconds` | `86400` | Retain each result for one day. |
| `result_pool_size` | `4` | Maximum Redis result-backend connections. |

Queue bounds result values to 1 MB and 64 nested containers. These limits
protect result storage independently of the job-envelope size setting.

Each entry under `connections` has a `driver` and an optional `options`
mapping. Built-in drivers are `sync`, `null`, `redis_stream`, and `rabbitmq`.
Custom Taskiq brokers can be registered through a trusted
`QueueServiceProvider` driver factory.

Redis Streams supports two recovery settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `idle_timeout_ms` | `600000` | Minimum pending-message age before Taskiq can reclaim it. |
| `unacknowledged_lock_timeout_seconds` | `900` | Expiration for Taskiq's Redis lock around pending-message claims. |

Taskiq checks for pending messages after it reads fresh messages. An idle
queue does not trigger recovery by itself. See [Delivery guarantees](/framework/queue/delivery/).

## Optional backend packages

Install the backend extra that matches the selected driver:

```shell
uv add 'titanspan[queue-redis]'
```

```shell
uv add 'titanspan[queue-rabbitmq]'
```

Redis and RabbitMQ integrations run against real local or CI services.
RabbitMQ coverage verifies publication, consumption, cleanup, and redelivery
after a worker process dies inside a handler. It does not support delayed
scheduling.

## Register job classes

Pass trusted classes to `QueueServiceProvider(jobs=(...))`. Registration
freezes during application startup. Workers accept only those registered job
names; broker messages cannot import arbitrary Python classes.

The default provider registers Queue services without discovering arbitrary
application modules. Use explicit provider registration or trusted installed
provider discovery. See [Jobs](/framework/queue/jobs/).
