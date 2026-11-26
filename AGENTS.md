# Titanspan Agent Instructions

This document is the canonical repository-wide instruction file for AI coding
agents working on Titanspan.

Read this file before making changes. Consult applicable scoped `AGENTS.md`
files, architecture documents, accepted Architecture Decision Records (ADRs),
engineering standards, and existing implementations.

Scoped instructions may extend these rules but must not contradict or weaken
them. Coding-agent configurations, skills, profiles, and harness adapters
must reference these instructions rather than maintain competing policies.

## 1. Project identity

Titanspan is an independent, open-source, async-first Python application
framework for building intelligent systems at scale.

Its vision is to provide a cohesive foundation for:

- Web applications and APIs.
- Artificial intelligence and agentic systems.
- Stateful workflow orchestration.
- Structured concurrency and CPU parallelism.
- Distributed execution and background processing.
- High-throughput data processing and streaming.
- Extensible application infrastructure.

Titanspan draws inspiration from Laravel's architecture, expressive APIs,
application conventions, and developer experience while remaining entirely
native to the Python ecosystem.

Laravel inspires the developer experience. Python determines the
implementation architecture and language semantics. Framework cohesion
determines the design.

Titanspan does not maintain external framework API compatibility, reproduce
PHP-specific behavior, or introduce compatibility-only naming conventions.

The framework is under active development. Verify implementations and tests
before describing capabilities as available. Roadmap items are planned work,
not implemented features or public API specifications.

## 2. Engineering philosophy

Build the framework, not the infrastructure.

Titanspan exists to unify mature Python technologies through expressive APIs,
convention over configuration, application lifecycle management, dependency
integration, and consistent developer experience.

The framework owns:

- Native public APIs and application conventions.
- Service registration and dependency integration.
- Application and execution lifecycles.
- Component composition and coordination.
- Contracts, facades, helpers, and service providers.
- Configuration and resource ownership policies.
- Framework-specific abstractions and testing support.

Established dependencies own their underlying infrastructure and execution
mechanisms.

Prioritize correctness, simplicity, maintainability, security, performance,
extensibility, and developer experience.

Write the minimum necessary framework code to deliver the required behavior
without sacrificing engineering quality.

## 3. Dependency-first implementation

Prefer delegation over reimplementation.

Before introducing functionality:

1. Inspect existing Titanspan components for reusable capabilities.
2. Investigate whether an existing dependency provides the functionality.
3. Verify dependency capabilities against official documentation and the
   exact versions recorded in `uv.lock`.
4. Prefer direct delegation, configuration, composition, or a thin adapter.
5. Consider another established dependency only when existing foundations
   cannot reasonably satisfy the requirement.
6. Implement custom infrastructure only when a demonstrated requirement
   cannot be addressed safely through the available alternatives.

Custom implementations require a clear architectural justification.

Do not unnecessarily implement competing:

- Dependency injection engines.
- HTTP networking or connection-pooling infrastructure.
- HTTP protocol parsers.
- Routing and route-matching engines.
- Schema validation engines.
- Database abstraction or ORM engines.
- Cryptographic primitives.
- Distributed task execution engines.
- Workflow graph execution engines.
- Scheduling systems.
- Concurrency runtimes.
- Data processing engines.

Titanspan may provide native APIs over these capabilities without owning
their underlying execution mechanisms.

Prefer thin, strongly typed adapters. Do not introduce unnecessary layers,
forwarding classes, duplicated abstractions, or speculative infrastructure.

Use supported public dependency APIs. Do not rely on undocumented backend
internals, monkey-patching, or fragile implementation details.

If a dependency cannot safely support a requested capability, document the
limitation and evaluate alternatives. Do not implement unsafe workarounds
merely to achieve API completeness.

Preserve accurate dependency metadata, licensing, attribution, and
documentation of delegated behavior.

## 4. Technology foundations

Respect accepted ADRs and existing architectural decisions.

The preferred technology foundations are:

| Responsibility              | Technology                      |
| --------------------------- | ------------------------------- |
| Web and ASGI infrastructure | FastAPI, Starlette              |
| Dependency resolution       | Dishka                          |
| Configuration               | Pydantic Settings               |
| Validation                  | Pydantic                        |
| Logging                     | Structlog, Python logging       |
| HTTP client                 | HTTPX                           |
| Database and persistence    | SQLAlchemy                      |
| Database migrations         | Alembic                         |
| Cache                       | Cashews                         |
| Events                      | Blinker                         |
| Distributed jobs            | Taskiq                          |
| Scheduling                  | APScheduler                     |
| Filesystem adapters         | fsspec                          |
| Async concurrency           | AnyIO                           |
| CPU parallelism             | Process pools, native libraries |
| AI integrations             | LangChain                       |
| Stateful workflow execution | LangGraph                       |
| Data processing             | Polars, Apache Arrow            |
| Observability               | OpenTelemetry                   |
| CLI infrastructure          | Typer, Rich                     |
| Testing                     | Pytest                          |

These are architectural foundations, not requirements to install every
dependency or implement every associated component immediately.

Do not introduce unused, redundant, or unjustified dependencies.

Dependency replacement requires verified evidence, a focused architectural
proposal, maintainer review, and an ADR when the decision is consequential.

The authoritative technology decisions are maintained in `ARCHITECTURE.md`
and the accepted ADRs under `docs/architecture/decisions/`.

## 5. Framework architecture

Titanspan is a modular application framework, not a collection of unrelated
utility packages.

Each component must have clearly defined responsibilities, dependency
boundaries, public APIs, and resource ownership.

### Component responsibilities

Maintain separation between:

- Foundation: application composition, bootstrap, and lifecycle.
- Container: service registration, dependency resolution, and scopes.
- Contracts: shared, dependency-independent abstraction boundaries.
- Config: application configuration and settings.
- Logging: application logging and structured diagnostics.
- Facades: expressive access to application-owned services.
- Support: reusable, general-purpose framework utilities.
- HTTP: incoming and outgoing HTTP infrastructure.
- Routing: endpoint registration, matching, and dispatch.

Apply the same separation of concerns to future components.

Do not duplicate responsibilities already owned by another component.

### Service composition

The native Container is the authoritative registry for ordinary
application-owned services.

Use native service providers to register component services.

Resolve shared services through their canonical contracts where appropriate.
Facade access, dependency injection, application helpers, and ordinary
service resolution must cooperate through the same application context and
service registry.

Do not introduce competing production service registries, implicit global
application instances, or disconnected dependency resolution mechanisms.

Document deliberate interoperability boundaries and transitional limitations.

### Component organization

Use predictable, domain-oriented package and module names.

Place public implementations within their owning components and shared
contracts under domain packages within `titanspan.contracts`.

Use private backend adapters and internal implementation modules where
appropriate.

For example, prefer `container/container.py` for the native public
implementation rather than a vendor-named public module.

Separate cohesive responsibilities when doing so improves maintainability,
testability, or dependency boundaries.

Do not create unnecessary files, empty directories, speculative interfaces,
or artificial abstraction layers merely to satisfy an architectural diagram.

### Dependency boundaries

Keep foundational modules independent of optional AI, database, queue, and
infrastructure adapters.

Prevent circular dependencies.

Prefer composition and focused protocols over deep inheritance,
unnecessary metaprogramming, or unrestricted dynamic forwarding.

Use dependency inversion where it establishes a genuine architectural
boundary. Do not introduce interfaces for their own sake.

## 6. Contracts and backend encapsulation

Define shared public contracts only where they establish meaningful
abstraction boundaries, substitution capabilities, or extension points.

Each established contract should have:

- A canonical definition.
- A clearly defined responsibility.
- Production implementations where applicable.
- Genuine consumers or a justified extension purpose.
- Static conformance evidence.
- Behavioral verification.
- Container registration where appropriate.

Python structural typing is preferred where suitable. Explicit inheritance
from a protocol is not universally required.

Runtime protocol checks alone do not establish behavioral conformance.

Component packages may re-export canonical contract objects but must not
redeclare them. Keep implementation-private protocols within their owning
components.

Ordinary Titanspan application APIs must remain independent of unnecessary
backend-specific types.

Provide explicit, documented interoperability where it offers genuine value.
Do not conceal which libraries perform delegated behavior.

Do not introduce redundant wrappers merely to hide third-party names.

Contracts do not imply implementations. Do not advertise a capability simply
because its interface exists.

## 7. Framework cohesion and component completeness

Framework cohesion takes precedence over isolated component completeness.

A component is not complete merely because its classes and methods exist,
its documentation is written, or its isolated unit tests pass.

An implemented component must, where applicable:

- Satisfy its established contracts.
- Register its services through native service providers.
- Consume application configuration through the canonical configuration
  repository.
- Integrate with the existing Container and application context.
- Participate in application startup, execution, and shutdown.
- Expose consistent, strongly typed native APIs.
- Reuse existing framework capabilities.
- Preserve application and execution-scope isolation.
- Own and finalize resources correctly.
- Demonstrate genuine cross-component integration.
- Provide accurate documentation and executable examples.

Use real application integration tests to verify service identity,
substitutability, lifecycle behavior, and interactions between components.

Do not simulate completeness through disconnected abstractions, placeholder
implementations, or tests that exercise only artificial fixtures.

When a required dependency or component is not implemented, explicitly
document the limitation and integration work that remains.

Conduct architectural and framework-cohesion reviews after major
implementation milestones before introducing further dependent components.

## 8. Public API and developer experience

Provide expressive, predictable, discoverable, and strongly typed APIs.

Favor convention over configuration while preserving explicit customization
and extension mechanisms.

Use Laravel-inspired application patterns where they provide genuine value,
including service providers, facades, fluent interfaces, contextual
dependency injection, resource conventions, and application helpers.

Adapt these patterns to Python rather than mechanically translating another
language's implementation.

Use:

- Canonical snake_case functions, methods, parameters, and attributes.
- PascalCase classes, protocols, and exceptions.
- UPPER_SNAKE_CASE constants.
- Native Python decorators, context managers, protocols, generics, and
  special methods where appropriate.
- Explicit, typed fluent APIs.

Do not introduce camelCase compatibility aliases, PHP-specific type coercion,
or redundant methods solely to reproduce external framework APIs.

Keep Ruff's `N` naming rules enabled.

A narrowly reviewed naming exception is permitted only where a supported
external Python protocol requires an exact spelling. Record the specific
file and rule in the native API policy test.

Preserve established Titanspan behavior. Consequential API changes require
documentation, caller updates, regression coverage, and appropriate
architectural review.

## 9. Async, concurrency, and resource safety

Titanspan is async-first, not async-only.

Keep pure computation, object construction, dependency registration,
configuration access, and other sync-safe operations synchronous.

Expose explicit asynchronous alternatives when an operation requires
asynchronous initialization, I/O, callbacks, or resource cleanup.

Never make a public operation conditionally return either a resolved value
or an awaitable.

Do not silently create event loops, block existing event loops, or hide
unsafe thread transitions.

### Execution and concurrency

- Prefer structured concurrency.
- Give every concurrent task an explicit owner.
- Propagate cancellation and timeouts correctly.
- Offload blocking operations through appropriate, bounded execution
  mechanisms.
- Bound concurrency, queues, buffering, memory, connections, and retries.
- Apply backpressure and incremental processing to large or ongoing
  workloads.
- Do not create unbounded tasks or use unbounded `asyncio.gather()` for
  arbitrary input streams.
- Distinguish asynchronous I/O concurrency from CPU parallelism and
  distributed execution.
- Use process-based or suitable native execution for CPU-bound workloads.

### Application and execution isolation

Keep application-owned and execution-owned resources distinct.

Use context-local state for application, request, job, workflow, agent, and
other execution contexts.

Ensure nested contexts restore previous state after success, failure,
cancellation, and normal exit.

Do not share mutable or thread-unsafe resources across incompatible
execution contexts.

In particular, do not share SQLAlchemy `AsyncSession` instances across
concurrent tasks. Keep transaction ownership explicit.

### Resource ownership

Every resource must have a clearly identified owner and lifecycle.

Finalize resources on success, failure, cancellation, partial
initialization failure, and shutdown.

Keep request-scoped resources available until complete response
transmission, including streaming and disconnection handling.

Ensure externally supplied resources and container-owned resources follow
their documented ownership policies.

Make retry behavior safe for non-idempotent operations.

### Performance evidence

Do not claim scalability or performance improvements solely from async
syntax or architectural intentions.

Use reproducible measurements and record relevant workload, platform,
dependency versions, concurrency, throughput, latency, and peak memory.

## 10. Development workflow

Before making meaningful changes:

1. Inspect `git status`, relevant source files, tests, and existing
   conventions. Preserve user changes and concurrent development work.
2. Read applicable scoped instructions, architectural decisions, and
   engineering standards.
3. Identify existing implementations and reusable dependency capabilities.
4. For non-trivial changes, establish scope, affected modules, expected
   behavior, architectural impact, tests, risks, and acceptance criteria.
5. Use Red-Green-Refactor. Write and execute a focused failing test before
   implementing meaningful behavior changes or defect corrections.
6. Implement the smallest cohesive change that satisfies the requirement.
7. Run applicable targeted and repository-wide checks.
8. Review the complete diff, including tests, documentation, configuration,
   and architectural consequences.
9. Report actual results and unresolved limitations.

Keep implementation focused on the requested task.

Do not turn minor corrections into large architectural refactors.

Use the existing agent workflow and engineering standards:

- [Agent workflow](docs/development/agent-workflow.md)
- [Engineering standards](docs/development/standards.md)

## 11. Python and package standards

Maintain the following mandatory standards:

- Python 3.12 or later, subject to the supported version matrix.
- UTF-8 encoding and LF line endings.
- Four-space Python indentation.
- Two-space YAML indentation.
- Strict maximum Python source line length of 80 characters.
- PEP 8 naming conventions.
- Absolute imports.
- Explicit public exports.
- Comprehensive type annotations.
- Explicit return annotations.
- Strict Ruff linting and formatting.
- Strict Pyright type checking.

These requirements apply to production code, tests, examples, benchmarks,
and development scripts.

Do not introduce wildcard imports, dead code, commented-out implementations,
mutable default arguments, unexplained magic numbers, or unnecessary global
mutable state.

Keep `Any`, unsafe casts, and type suppressions limited to narrow,
documented third-party boundaries.

Avoid unnecessarily broad exception handling and blanket suppressions.

Prefer `pathlib`, context managers, focused protocols, immutable values
where appropriate, and explicit side effects.

### Documentation and comments

Every module, class, function, method, fixture, and test must have a
physically multiline Google-style docstring.

Add meaningful implementation comments for non-obvious:

- Architectural rationale.
- Invariants.
- Lifecycle and resource ownership.
- Concurrency and cancellation.
- Security boundaries.
- Error handling and recovery.

Comments must explain why the implementation behaves as it does rather
than merely restating the code.

Meaningful comment quality remains subject to human review.

### Technical writing

Follow [the writing standard](docs/development/writing-standards.md) and the
canonical terms in [the glossary](docs/development/glossary.md).

Use clear, concise American English. Prefer active voice and one primary idea
per sentence. Keep procedural sentences near 20 words and descriptive
sentences near 25 words. These limits are targets, not substitutes for
technical accuracy.

Write direct procedural instructions and explain non-obvious design choices.
Preserve exact Python identifiers, commands, URLs, and technical meaning.
Vale findings at warning and suggestion levels are advisory. Error-level
terminology, capitalization, and prohibited-expression findings must be
corrected.

### Dependency and package management

Use `uv` exclusively for Python dependency management, environments,
locking, building, and publishing.

Preserve `uv.lock` and update it through supported `uv` commands.

Do not introduce Poetry, Pipenv, Conda, global package installations, or
unjustified dependencies.

Keep development tooling and agent assets outside `src/titanspan/`, except
for necessary scoped Markdown instructions.

Verify that built distributions do not contain development-only
instructions, agent configurations, or unrelated tooling.

## 12. Testing and verification

Use Red-Green-Refactor for every meaningful behavior change.

Every defect correction requires a regression test.

Provide comprehensive unit and real integration tests for implemented
behavior and architectural boundaries.

As applicable, verify:

- Successful operations.
- Invalid input and failure conditions.
- Contract conformance and substitutability.
- Cross-component integration.
- Application and execution-context isolation.
- Resource ownership and cleanup.
- Concurrent execution.
- Cancellation and timeouts.
- Security boundaries.
- Public API behavior.

Use actual production implementations and underlying dependencies when
testing integration boundaries.

Mocks, fakes, and fixtures are appropriate for isolated behavior but must
not substitute for the real component whose integration is being verified.

Maintain independently enforced minimum coverage thresholds:

- Statement coverage: 95%.
- Branch coverage: 90%.

These thresholds apply to `src/titanspan`.

Never weaken assertions, lower thresholds, skip failing tests, or introduce
artificial coverage merely to satisfy a quality gate.

Use reproducible benchmarks where performance is relevant. Do not alter
benchmarks to conceal regressions.

## 13. Quality checks and continuous integration

Use existing Makefile targets and `uv run --locked` for repository tooling.

Required verification includes:

- Ruff linting.
- Ruff formatting.
- Strict Pyright.
- Python syntax validation.
- Docstring validation.
- Implementation comment validation.
- Source line-length validation.
- Architecture and import-boundary checks.
- Public API validation.
- Agent configuration validation.
- Dependency lock verification.
- Applicable unit and integration tests.
- Coverage enforcement.
- Security verification.
- Package build verification.
- Documentation validation.

Use `make check` for the standard read-only quality gate.

Use `make ci` for the extended CI-equivalent verification, including
security, documentation, packaging, and runtime checks.

Inspect the Makefile for current available commands. Do not invent targets
or claim that unavailable or unexecuted commands have passed.

### Mandatory CI gate

Preserve the fail-closed `ci-gate` and its mandatory job inventory.

Every required check must remain independently visible and participate in
the final gate.

Failed, missing, skipped, cancelled, or malformed mandatory results must
not be accepted as successful.

CI policy changes require a focused justification and independent
maintainer review.

Verify workflow syntax and policy before modifying remote CI rules.

## 14. Documentation requirements

Keep public documentation consistent with the current implementation.

Update relevant documentation, component specifications, examples,
architecture records, roadmap status, and changelog entries when behavior
or public APIs change.

Documentation must distinguish between:

- Implemented and verified capabilities.
- Implemented but incompletely verified behavior.
- Planned functionality.
- Unsupported capabilities.
- Known architectural limitations.

Use accurate, executable Python examples.

Do not invent APIs, performance measurements, dependency capabilities, or
verification results.

When adding, renaming, or removing documentation pages, update the VitePress
navigation accordingly.

Run the actual navigation consistency validator against the documentation
site, its regression tests, and the applicable documentation build.

Do not consider fixture-only navigation tests sufficient verification of
the published documentation structure.

Preserve legally required attribution while using consistent native
Titanspan terminology.

## 15. Security and repository safety

Treat external inputs, configuration values, HTTP requests, tool inputs,
and external service responses as untrusted.

Validate input, bind database parameters, authorize tool execution, and
enforce applicable application and tenant boundaries.

Prevent exposure of secrets, credentials, authorization headers, private
payloads, and sensitive configuration through logs or diagnostics.

Never commit credentials, private user data, or real `.env` files.

Do not introduce paid services, commercial AI calls, or hosted
infrastructure without explicit authorization.

Do not install coding agents or automatically execute downloaded scripts.

Preserve sandboxing and approval requirements.

Do not introduce blanket permission bypasses, unrestricted shell or network
settings, or executable agent hooks without an independently reviewed,
justified requirement.

Do not commit, push, publish, release, deploy, message third parties, or
modify organization settings unless the current task explicitly authorizes
the action.

Never force-push, rewrite shared history, reset away user changes, or bypass
repository protections.

## 16. Protected engineering policies

Agents must not:

- Disable or weaken tests, coverage, strict typing, Ruff, security checks,
  hooks, CI, or architecture constraints.
- Lower coverage requirements or introduce blanket exclusions.
- Skip failing tests or weaken meaningful assertions.
- Suppress security findings merely to make checks pass.
- Remove mandatory CI jobs or omit them from the final gate.
- Make mandatory checks best-effort.
- Unpin external GitHub Actions.
- Weaken workflow permissions or repository safeguards.
- Bypass hooks or remove platform and integration verification.
- Present placeholders, TODOs, mocks, or planned work as complete behavior.
- Invent APIs, test results, benchmarks, or documentation evidence.
- Make unrelated refactors or introduce unjustified dependencies.
- Conceal implementation defects, failed checks, or unresolved limitations.

Changes to canonical agent instructions, engineering standards, quality
policies, CI requirements, or accepted architectural constraints require
focused justification and independent review through the repository
contribution process.

Do not weaken a policy as a workaround for implementation difficulties.

## 17. Git and delivery

Preserve existing user changes and coordinate with concurrent development
sessions.

When commits are authorized:

- Review the complete diff before committing.
- Stage only files relevant to the requested changes.
- Use focused, meaningful Conventional Commits.
- Follow the explicitly authorized branch and push strategy.
- Preserve repository history and existing safeguards.
- Verify applicable remote CI results after pushing.

Do not assume authorization to publish packages, create releases, deploy
applications, or modify repository settings merely because committing and
pushing were authorized.

### Final reporting

Report:

- What changed and why.
- Relevant architectural decisions.
- Dependencies reused or introduced.
- Public API additions or changes.
- Framework integration evidence.
- Tests and quality checks actually executed.
- Observed verification and CI results.
- Remaining limitations, risks, and blockers.

Distinguish verified behavior from assumptions and unexecuted checks.

Never conceal failed or skipped verification.

## 18. Canonical references

Use the following documents and configurations as authoritative references
for their respective responsibilities:

- [`AGENTS.md`](AGENTS.md): canonical repository-wide agent instructions.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): system architecture and component
  boundaries.
- [`ROADMAP.md`](ROADMAP.md): planned development milestones.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): repository contribution process.
- [`SECURITY.md`](SECURITY.md): security and vulnerability reporting.
- [`CHANGELOG.md`](CHANGELOG.md): recorded framework changes.
- [`docs/development/standards.md`](docs/development/standards.md):
  detailed engineering standards.
- [`docs/development/agent-workflow.md`](docs/development/agent-workflow.md):
  required agent development workflow.
- [`docs/architecture/decisions/`](docs/architecture/decisions/):
  accepted and proposed architectural decisions.
- [`pyproject.toml`](pyproject.toml): executable package and tool
  configuration.
- [`uv.lock`](uv.lock): locked dependency versions.
- [`Makefile`](Makefile): canonical repository development commands.

Keep these references consistent. Resolve contradictory instructions
explicitly rather than silently selecting whichever rule is easiest to
satisfy.

## 19. Final guiding principle

Build upon proven technologies rather than competing with them.

Delegate infrastructure mechanics to established dependencies. Own the
application conventions, integration architecture, public APIs, and
developer experience.

Every implementation must contribute to a cohesive, expressive, reliable,
and maintainable Python application framework.

Build intelligently. Scale confidently. Engineer beyond limits.
