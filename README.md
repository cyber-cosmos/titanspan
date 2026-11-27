# Titanspan

**Engineer beyond limits.**

[![CI](https://github.com/titanspan/framework/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/titanspan/framework/actions/workflows/ci.yml)
[![Security](https://github.com/titanspan/framework/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/titanspan/framework/actions/workflows/security.yml)
[![Documentation](https://github.com/titanspan/framework/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/titanspan/framework/actions/workflows/docs.yml)

Titanspan is an independent, open-source, async-first Python application
framework for building intelligent systems at scale. It provides expressive
Python APIs on top of established libraries.

The project is in early development. The implemented foundation includes
native configuration, logging, Support utilities, Collections, a synchronous-
first service container, HTTP, and Routing on a FastAPI-backed ASGI host.
Routing provides native registration, dispatch, discovery, inspection, URL
generation, WebSockets, and OpenAPI integration. These components have unit
and integration coverage, but lifecycle,
concurrency, security, and operational limits remain. Titanspan is not yet
production-ready. See the architecture, roadmap, and component specifications
for current capability status.
Numeric locale formatting and number spelling use the optional `numbers`
extra. Logging capabilities and planned work are listed in the native
[logging specification](docs/src/content/docs/specifications/logging.md).

## Install

Python 3.12 or later is required. Install from a checkout with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run titanspan --help
uv run titanspan --version
```

The package has not yet been published to PyPI.

## Hello World

Run the example ASGI application from the repository root:

```sh
uv run uvicorn --app-dir examples/hello-world app:app --reload
```

Open `http://127.0.0.1:8000/` to see a configured JSON greeting. The example
registers a service through a provider, injects configuration and logging
contracts, and registers its endpoint through native Routing. FastAPI and
Starlette provide the ASGI host and protocol infrastructure. See the
[Hello World guide](docs/src/content/docs/getting-started/hello-world.md) for
details.

## Development

```sh
uv sync --locked
make help
make check
```

Use `make docs` to serve the Starlight documentation locally, `make docs-build`
to build it, and `make docs-test` to verify it in Playwright. Docker is
optional; see the local
infrastructure section in the project documentation.

The runtime uses FastAPI and Starlette for ASGI. Dishka resolves dependencies
and owns container resource cleanup. Pydantic Settings validates typed
configuration. Typer and Rich provide the CLI. Structlog powers the native
logging API. SQLAlchemy, Alembic, LangGraph, and other future integrations are
not installed or exposed as Titanspan features.

To start optional local services, copy `.env.example` to `.env` and run
`make docker-up`. This starts PostgreSQL and Redis on loopback ports. The
`vector` and `mail` Compose profiles start pgvector and Mailpit respectively.
Run `make docker-down` to stop services; named development data is retained.

## Architecture

Titanspan owns its application APIs, lifecycle, integration conventions, and
testing experience. It delegates ASGI hosting to FastAPI and Starlette,
dependency resolution to Dishka, typed configuration to Pydantic Settings,
and structured logging dispatch to a private adapter. See the
[logging guide](docs/src/content/docs/logging/),
[ARCHITECTURE.md](ARCHITECTURE.md), the
[architecture decision records](docs/src/content/docs/architecture/decisions/), and the
[roadmap](ROADMAP.md) for the intended module boundaries and future direction.

## Project philosophy

- Convention over configuration with expressive, idiomatic Python APIs.
- Async-first behavior with structured resource lifecycles.
- Composition, typed contracts, and interchangeable integrations.
- Mature libraries for foundational infrastructure.
- Minimal mandatory dependencies and no required paid services.
- Testability, bounded resource use, and clear failure behavior.

Potential future use cases include AI workflow orchestration, agentic
applications, retrieval-augmented generation, streaming APIs, data ingestion,
and distributed background processing. These are design goals, not claims of
current functionality.

## Citation

If you use Titanspan in academic research, publications, or software projects, please consider citing the framework.

```bibtex
@software{thayananthajothy_titanspan,
  author = {Thayananthajothy, Jerome},
  title  = {Titanspan},
  year   = {2026},
  url    = {https://github.com/titanspan/framework}
}
```

Machine-readable citation metadata is available in [CITATION.cff](CITATION.cff).

Titanspan was created by [Jerome Thayananthajothy](https://thavarshan.com).

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the repository's
[AGENTS.md](AGENTS.md) before making architectural changes. The project uses
test-driven development, uv, GNU Make, Ruff, Pyright, and Pytest.

## Security

Please report security issues privately using the repository's
[security advisory page](https://github.com/titanspan/framework/security/advisories/new).
See [SECURITY.md](SECURITY.md) for the supported disclosure process.

## License

Titanspan is distributed under the MIT License. See [LICENSE](LICENSE).
