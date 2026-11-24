# Titanspan

**Engineer beyond limits.**

Titanspan is an open-source, async-first Python application framework for
building intelligent systems at scale. It is inspired by Laravel's expressive
developer experience and builds on established Python libraries.

The project is at the beginning of **Phase 0: Engineering foundation**. The
current implementation includes a FastAPI-backed application lifecycle, an
async Dishka container integration, typed environment settings, a small CLI,
and tested Support utilities for arrays, strings, URIs, timing, and numbers.
Numeric locale formatting and number spelling use the optional `numbers`
extra. AI workflows, persistence, distributed execution, and other modules
described in the architecture are planned, not implemented or production
ready.

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

Open `http://127.0.0.1:8000/` to see the JSON greeting.

## Development

```sh
uv sync --locked
make help
make check
```

Use `make docs` to serve the VitePress documentation locally and
`make docs-build` to build it. Docker is optional; see the local
infrastructure section in the project documentation.

The current runtime foundation uses FastAPI and Starlette for ASGI, Dishka for
dependency resolution and resource cleanup, Pydantic Settings for typed
configuration, and Typer with Rich for the CLI. SQLAlchemy, Alembic, LangGraph,
AnyIO, and other integrations are architectural choices for future modules;
they are not installed or exposed as Titanspan features yet.

To start optional local services, copy `.env.example` to `.env` and run
`make docker-up`. This starts PostgreSQL and Redis on loopback ports. The
`vector` and `mail` Compose profiles start pgvector and Mailpit respectively.
Run `make docker-down` to stop services; named development data is retained.

## Architecture

Titanspan owns its application APIs, lifecycle, integration conventions, and
testing experience. It delegates web serving to FastAPI, dependency resolution
to Dishka, and typed configuration to Pydantic Settings. See
[ARCHITECTURE.md](ARCHITECTURE.md), the
[architecture decision records](docs/architecture/decisions/), and the
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

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the repository's
[AGENTS.md](AGENTS.md) before making architectural changes. The project uses
test-driven development, uv, GNU Make, Ruff, Pyright, and Pytest.

## Security

Please report security issues privately using the repository's
[security advisory page](https://github.com/titanspan/titanspan/security/advisories/new).
See [SECURITY.md](SECURITY.md) for the supported disclosure process.

## License

Titanspan is distributed under the MIT License. See [LICENSE](LICENSE).
