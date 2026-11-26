---
title: "Deployment"
---

<span id="deployment"></span>

The package is at the engineering foundation stage and has not been published
to PyPI or declared production ready. A Dockerfile and optional local
PostgreSQL, pgvector, Redis, and Mailpit services are provided for development.

Future deployment guidance will cover workers, process shutdown, configuration,
secrets, telemetry, and recovery once those integrations are implemented.

## Local services

Copy `.env.example` to `.env` and run `make docker-up` for PostgreSQL and Redis.
The Compose profiles are opt-in:

```sh
docker compose --profile vector up -d
docker compose --profile mail up -d
```

PostgreSQL uses port 5432, pgvector uses 5433, Redis uses 6379, and Mailpit's
SMTP and web UI use 1025 and 8025. Ports bind to loopback. The sample
PostgreSQL password is for local development only. Never reuse it in a
deployed environment. `make docker-down` stops services and retains named
volumes.

Application and worker Compose profiles will be added after those runtimes
exist; starting a service that does not yet have implemented behavior would be
misleading.
