---
title: Titanspan
template: splash
hero:
  title: Titanspan
  tagline: Engineer beyond limits.
  actions:
    - text: Get started
      link: /titanspan/getting-started/installation/
      variant: primary
    - text: Browse the documentation
      link: /titanspan/architecture/
      variant: minimal
---

Titanspan is an async-first Python application framework for building
intelligent systems. Its implemented foundation brings application lifecycle,
service composition, configuration, logging, and dependency resolution under
one cohesive application API.

## Install from source

Titanspan is a pre-alpha project and has not been published to PyPI. Clone the
repository and install its locked development environment:

```sh
git clone https://github.com/titanspan/titanspan.git
cd titanspan
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
execution context. FastAPI supplies HTTP routing and ASGI hosting.

## Understand the foundation

Application construction registers configuration and logging providers in one
native service container. The application lifecycle starts providers and
finalizes owned resources; context-local state connects service resolution,
facades, and request handling. Established Python libraries provide the
underlying dependency resolution, HTTP hosting, settings validation, and
structured logging mechanisms.

Configuration, the service container, contracts, HTTP, logging, Collections,
and Support are implemented. Database, framework-owned routing, AI workflows,
distributed jobs, and high-throughput data processing remain planned. See the
[roadmap](https://github.com/titanspan/titanspan/blob/main/ROADMAP.md) for
current status.

## Explore and contribute

- [Getting started](/titanspan/getting-started/installation/) and the
  [Hello World guide](/titanspan/getting-started/hello-world/) show the current workflow.
- [Application architecture](/titanspan/architecture/) explains composition,
  application context, and lifecycle ownership.
- Explore [configuration](/titanspan/config/), the [service
  container](/titanspan/container/), [contracts](/titanspan/contracts/),
  [HTTP](/titanspan/http/), [logging](/titanspan/logging/),
  [Collections](/titanspan/collections/), and [Support](/titanspan/support/).
- Read the [architecture guide](/titanspan/architecture/) and
  [engineering specifications](/titanspan/specifications/backend-boundaries/).
- Contributors can read the
  [agent workflow](/titanspan/development/agent-workflow/) and
  [engineering standards](/titanspan/development/standards/).

Titanspan is open source under the MIT License. Visit the
[GitHub repository](https://github.com/titanspan/titanspan) to explore the
code, report issues, or contribute. See the
[contribution guide](https://github.com/titanspan/titanspan/blob/main/CONTRIBUTING.md)
for the project workflow.
