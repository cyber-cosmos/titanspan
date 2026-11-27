---
title: Titanspan
template: splash
hero:
  title: Titanspan
  tagline: Engineer beyond limits.
  actions:
    - text: Get started
      link: /framework/getting-started/installation/
      variant: primary
    - text: Browse the documentation
      link: /framework/architecture/
      variant: minimal
---

Titanspan is an async-first Python application framework for building
intelligent systems. Its implemented foundation brings application lifecycle,
service composition, configuration, logging, dependency resolution, and
native routing under one cohesive application API.

## Install from source

Titanspan is a pre-alpha project and has not been published to PyPI. Clone the
repository and install its locked development environment:

```sh
git clone https://github.com/titanspan/framework.git
cd framework
uv sync --locked
```

Run the working ASGI example from the repository root:

```sh
uv run uvicorn --app-dir examples/hello-world app:app --reload
```

## Start with an application

`Application` composes Titanspan services and exposes the current FastAPI
integration through its ASGI boundary:

```python
from titanspan import Application

application = Application(
    config={"app": {"name": "service-api"}},
)
app = application.asgi
```

The application owns its native container, provider lifecycle, and shared
execution context. Titanspan Routing owns route definitions and dispatch;
FastAPI and Starlette provide the underlying ASGI adapter.

## Understand the foundation

Application construction registers configuration and logging providers in one
native service container. The application lifecycle starts providers and
finalizes owned resources; context-local state connects service resolution,
facades, and request handling. Established Python libraries provide the
underlying dependency resolution, HTTP hosting, settings validation, and
structured logging mechanisms.

Configuration, the service container, contracts, HTTP, Routing, logging,
Collections, and Support are implemented. Database, AI workflows, distributed
jobs, and high-throughput data processing remain planned. See the
[roadmap](https://github.com/titanspan/framework/blob/main/ROADMAP.md) for
current status.

## Explore and contribute

- [Getting started](/framework/getting-started/installation/) and the
  [Hello World guide](/framework/getting-started/hello-world/) show the current workflow.
- [Application architecture](/framework/architecture/) explains composition,
  application context, and lifecycle ownership.
- Explore [configuration](/framework/config/), the [service
  container](/framework/container/), [contracts](/framework/contracts/),
  [HTTP](/framework/http/), [Routing](/framework/routing/),
  [logging](/framework/logging/), [Collections](/framework/collections/),
  and [Support](/framework/support/).
- Read the [architecture guide](/framework/architecture/) and
  [engineering specifications](/framework/specifications/backend-boundaries/).
- Contributors can read the
  [agent workflow](/framework/development/agent-workflow/) and
  [engineering standards](/framework/development/standards/).

Titanspan is open source under the MIT License. Visit the
[GitHub repository](https://github.com/titanspan/framework) to explore the
code, report issues, or contribute. See the
[contribution guide](https://github.com/titanspan/framework/blob/main/CONTRIBUTING.md)
for the project workflow.
