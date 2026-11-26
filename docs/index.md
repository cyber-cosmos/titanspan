---
layout: home

hero:
  name: Titanspan
  text: Engineer beyond limits.
  tagline: An async-first Python application framework.

features:
  - title: Application lifecycle
    details: Compose providers, settings, and services under one application owner.
  - title: Native service registry
    details: Resolve application services through one shared container and context.
  - title: Proven Python foundations
    details: FastAPI, Dishka, Pydantic Settings, and Structlog handle core infrastructure.
---

## Install from source

Titanspan is a pre-release and has not yet been published to PyPI. Clone the
repository and install its locked environment:

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

## Explore the implemented foundation

- [Getting started](/getting-started/installation) and the
  [Hello World guide](/getting-started/hello-world) show the current workflow.
- [Application architecture](/architecture/) explains composition,
  application context, and lifecycle ownership.
- [Service Container](/container/) documents registration, resolution, scopes,
  and resource cleanup.
- [Configuration](/config/), [Logging](/logging/), [Contracts](/contracts/),
  and [Support](/support/) cover the implemented component surfaces.

The project is pre-alpha and is not production-ready. Database integration,
framework routing, AI workflows, distributed jobs, and high-throughput data
processing remain planned capabilities. See the
[roadmap](https://github.com/titanspan/titanspan/blob/main/ROADMAP.md) for
their current status.

## Learn and contribute

Application developers can continue with the
[Hello World guide](/getting-started/hello-world), then browse the component
navigation. Contributors can read the
[agent workflow](/development/agent-workflow),
[engineering standards](/development/standards), and
[contribution guide](https://github.com/titanspan/titanspan/blob/main/CONTRIBUTING.md).

Titanspan is open source under the MIT License. Visit the
[GitHub repository](https://github.com/titanspan/titanspan) to explore the
code, report issues, or contribute.
