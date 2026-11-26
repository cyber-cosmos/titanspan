---
title: "ADR 0018: Native application service composition"
---

<span id="adr-0018-native-application-service-composition"></span>

- Status: Accepted
- Date: 2026-11-26
- Supersedes: Application composition and facade-resolution statements in
  ADR 0014 and ADR 0015

## Context

The native container, configuration repository, logging manager, and facades
had working component-level APIs but were not one application service graph.
The application registered configuration separately in a web adapter,
created logging directly, and facades kept independent production lookups.
This prevented alternate configuration repositories and typed service
contracts from forming one substitutable application boundary.

The early web integration used a separate graph for FastAPI route dependencies.
Native Router handlers now resolve through the application Container. Explicit
external route providers still use a private graph, but ordinary Titanspan
services must not require that graph.

## Decision

- `Application` constructs and owns exactly one native `Container` for
  framework services.
- Register that same container under `ServiceContainer` and
  `AsyncServiceContainer` before component providers run.
- Register the selected configuration repository under `ConfigRepository`,
  `ConfigReader`, and `ConfigWriter`. Register typed access, scoped overrides,
  redacted diagnostics, and macro capabilities only when the selected
  implementation structurally supports them.
- Register configuration and logging providers through one ordered native
  `ServiceProvider` collection. Application-defined providers register after
  framework providers. Optional `boot` methods run after registration,
  inside the application context, with dependencies resolved by the native
  container. `Application.startup()` and `Application.shutdown()` own this
  lifecycle independently of HTTP hosting. Keep the application context
  active through boot, shutdown, and owned-resource cleanup.
- `async with Application(...)` provides a structured standalone lifecycle
  for commands, workers, and workflows. The ASGI lifespan delegates to the
  same startup and shutdown methods.
- Construct the logging manager from the registered configuration contract.
  Explicit application logging configuration takes precedence. Register
  `LoggingManager` as an application singleton and `LogWriter` through the
  manager's channel factory.
- `Config` and `Log` inherit a typed `Facade` base, declare the canonical
  service contract, and use one context-local active application binding for
  production resolution. Explicit `use` and fake contexts remain temporary
  test overrides, not production registries.
- `Application.dependency(service)` creates a FastAPI dependency that resolves
  native services from the application container and active request scope.
  Pure ASGI middleware holds request and application context through the full
  response send, including streaming bodies.
- Keep explicit third-party route providers behind the private adapter.
  `Application.providers` remains an advanced interoperability boundary and
  may use a separate provider graph; native Router handlers use the
  application Container.
- Close provider-owned startup work and application services after normal
  shutdown, startup failure, and cancellation. Run cleanup in reverse
  ownership order.

## Alternatives considered

### Keep independent framework registries

Rejected because configuration, logging, facades, and application services
could resolve different instances and could not be substituted through one
contract graph.

### Remove all external route-provider integration

Deferred because some applications may rely on the explicit provider adapter
for external services. Native service injection is available independently
and has request-scope and streaming-lifecycle integration coverage.

### Make the generic facade forward arbitrary methods dynamically

Rejected because dynamic forwarding hides signatures from static type
checkers and IDEs. The base resolves the declared service; component facades
keep explicit typed methods.

## Consequences

Applications, facades, helpers, provider boot hooks, and direct contract
resolution share one configuration and logging identity. A genuine alternate
configuration repository can be selected at construction without inheriting
from the production repository. Optional repository capabilities remain
optional.

The optional web route graph and raw provider interoperability input remain
visible limitations. Application startup does not preflight arbitrary user
graphs. `Settings` also inherits methods from its private validation base;
those inherited backend methods are not a supported Titanspan API.

## Risks and controls

- **Provider ordering:** Built-in providers register before application
  providers; order is deterministic and tested.
- **Partial boot failure:** `AsyncExitStack` owns cleanup callbacks before
  provider boot, and regression coverage verifies logger closure and context
  restoration.
- **Context leakage:** A `ContextVar` holds application, container, and
  optional execution scope. Nested contexts, concurrent tasks, request
  middleware, full lifespan binding, and restoration after cleanup are tested.
- **Duplicate service identity:** Contract aliases register the same object;
  application integration tests compare identities across contract, app,
  facade, and helper access.
- **ASGI graph divergence:** The remaining separate graph is documented and
  limited to explicit external route-provider integration. Native application
  services use one container across handlers, facades, and providers.

## Verification

Architecture tests run through `make architecture-integration-test` and the
corresponding CI job. They cover contract identity, configuration substitution,
provider registration and boot injection, facade resolution, logging
configuration, shared service identity, context isolation, and startup cleanup.
Unit and integration suites also cover config, logging, scopes, ASGI requests,
cancellation, and resource cleanup.
