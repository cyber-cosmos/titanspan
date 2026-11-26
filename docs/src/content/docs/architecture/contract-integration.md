---
title: "Contract integration audit"
---

<span id="contract-integration-audit"></span>

This audit describes the current working implementation, not the roadmap.
The inventory was checked against `src/titanspan`, service providers,
container registrations, facade consumers, tests, and public exports.

Runtime-checkable protocols only establish attribute presence. The evidence
column distinguishes static assignments and behavioral tests from real
application integration. The cross-component test target runs tests marked
`architecture` and is a required job in the CI gate.

The shared Contracts package defines public protocols across ten domains:
configuration, container, Console, Events, foundation, HTTP, logging,
Pipeline, Routing, and Support. Domain value types are identified separately.
One public abstract facade base and one private production protocol are also
listed. Every public contract appears in its canonical domain package. The
root package re-exports the same object. Private implementation and test-only
protocols remain unexported.

## Configuration contracts

| Contract | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `ConfigReader` | `contracts/config/repository.py` | `config.Repository`; narrow read-only injection capability | Registered by `ConfigServiceProvider`; alternate repository and production conformance assignments in `tests/unit/contracts/test_contract_organization.py`; app resolution in `tests/integration/test_framework_cohesion.py` | Implemented, registered, no distinct built-in consumer |
| `ConfigWriter` | `contracts/config/repository.py` | `config.Repository`; narrow mutation capability | Registered by `ConfigServiceProvider` to the same selected repository instance; static and app integration evidence as `ConfigReader` | Implemented, registered, no distinct built-in consumer |
| `ConfigRepository` | `contracts/config/repository.py` | `config.Repository`; `Config` facade; config helper; logging provider; application | `ConfigServiceProvider` registers the selected object; alternate mapping implementation is injected through the real app lifecycle and shared by app, facade, and helper | Implemented and consumed |
| `TypedConfigReader` | `contracts/config/capabilities.py` | `config.Repository`; `Config` typed getters | Registered conditionally by `ConfigServiceProvider`; unsupported implementations remain valid base repositories and produce `ConfigCapabilityError` for typed reads | Optional capability implemented and consumed |
| `ScopedConfigOverrides` | `contracts/config/capabilities.py` | `config.Repository`; `Config.override` | Registered conditionally; unit tests cover nested scopes, mutation isolation, tasks, failure, and cancellation | Optional capability implemented and consumed |
| `ConfigDiagnostics` | `contracts/config/capabilities.py` | `config.Repository`; safe config CLI output | Registered conditionally; CLI depends on the protocol; redaction and CLI tests verify behavior | Optional capability implemented and consumed |
| `ConfigMacroRegistry` | `contracts/config/capabilities.py` | `config.Repository`; `Config` macro methods | Registered conditionally; Support macro tests cover registration and invocation | Optional capability implemented and consumed |

`ConfigRepository` is the ordinary application boundary. Optional
capabilities are separate, conditionally registered, and checked by the
facade only for the operation that needs them. A basic alternative does not
need to implement typed reads, overrides, redacted diagnostics, or macros.

## Container contracts

| Contract | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `InstanceRegistration` | `contracts/container/__init__.py` | `ConfigServiceProvider`; private ASGI provider adapter | Static conformance in `test_contract_organization.py`; actual configuration transfer is exercised by application and ASGI lifecycle tests | Implemented adapter capability |
| `ServiceRegistry` | `contracts/container/__init__.py` | `container.Container`; config and logging providers; application providers | Includes instance, transient, singleton, and scoped registration; static assignments and provider integration tests verify use through the real application | Implemented registration boundary |
| `ServiceContainer` | `contracts/container/__init__.py` | `container.Container`; `Facade`; `Application` | Bound to the owning application container; identity, contract resolution, provider injection, scopes, and resource behavior are exercised across container and application integration tests | Implemented, registered, and consumed |
| `AsyncServiceContainer` | `contracts/container/__init__.py` | `container.Container`; async-only consumers may depend on this smaller surface | Bound to the same application container as `ServiceContainer`; static and runtime contract checks plus execution-mode tests | Implemented capability; no separate built-in consumer |

`ServiceRegistry` is a registration-time protocol, not a runtime service for
mutating a frozen application. `InstanceRegistration` is consumed only by the
private web graph adapter. `ServiceContainer` and `AsyncServiceContainer`
resolve to the exact `Application.container` instance; they do not create
parallel registries.

The container adapter discovers concrete dependency closures from annotated
implementations before composing backend factories. It disables duplicate
backend recursion so Protocol contracts remain registered dependencies rather
than being mistaken for constructible classes. The registered `Greeter`
example covers this case with configuration and logging constructor
injection.

## Foundation contracts

| Contract | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `ServiceProvider` | `contracts/foundation/service_provider.py` | `ConfigServiceProvider`, `LoggingServiceProvider`, and application-defined providers; `foundation.Application` invokes `register` | Static assignments and real ordered registration / boot injection in `tests/integration/test_framework_cohesion.py` | Implemented and consumed |
| `BootableServiceProvider` | `contracts/foundation/service_provider.py` | Optional application provider capability; `foundation.Application` invokes `boot` after registration | Application checks the optional protocol and injects boot parameters; integration tests cover order, configuration injection, failed startup cleanup, and context restoration | Implemented lifecycle capability; no built-in provider currently requires boot |

Providers are structurally typed. Application construction is the only
registration owner; providers do not create another container. Provider boot
runs under the active application context. Native startup and shutdown also
work outside an ASGI host, and the ASGI lifespan delegates to those methods.
Pure ASGI request middleware keeps request scope and context active through
streamed response bodies. Regression tests cover cleanup and restoration after
shutdown and failed startup.

## Console contracts

| Contract or type | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `CommandRegistrar` | `contracts/console/__init__.py` | `console.Console`; applications and component command registration | Static assignment and duplicate-path behavior in `tests/unit/console/test_console.py`; parser dispatch in the same suite | Implemented and consumed |
| `ConsoleCommand` | `contracts/console/__init__.py` | Application command classes with `handle()` | Real class construction and async handler invocation through the Application Container | Implemented extension boundary |
| `ConsoleOutput` | `contracts/console/__init__.py` | `console.TerminalOutput`; command handlers | `ConsoleServiceProvider` binds the same output through `ServiceRegistry`; injection identity is verified in Console integration tests | Implemented, registered, and consumed |
| `ProgressTask` | `contracts/console/__init__.py` | Private Rich progress adapter; command handlers | Native context-manager behavior and progress validation in Console unit tests | Implemented and consumed |

`CommandHandler` is a public callable type alias. All Console contracts are
defined in their domain package and re-exported by `titanspan.contracts`.
Typer and Rich types remain inside the Console backend boundary.

## Events contracts

| Contract or type | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `EventDispatcher` | `contracts/events/dispatcher.py` | `events.NativeEventDispatcher`; event facade, helpers, subscribers, and application listeners | `EventServiceProvider` registers one instance under contract and concrete keys; strict Pyright checks the implementation and real Application integration verifies identity and dispatch behavior | Implemented, registered, and consumed |

`EventSelector` is a public type alias. It does not create a second runtime
contract. Blinker stores receiver references. Titanspan owns event selection,
injection, ordering, and sequential dispatch policy.

## Logging contracts

| Contract or type | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `LogDriver` | `contracts/logging/driver.py` | Native drivers; `LogChannel` and `LogManager` consume it | Static factory types; driver, stack, file, webhook, and lifecycle tests | Implemented and consumed |
| `AsyncLogDriver` | `contracts/logging/async_driver.py` | Optional custom async destination capability; `LogChannel` consumes it | Async delivery and cancellation tests; no bundled driver currently implements this optional extension | Implemented extension point |
| `LogFormatter` | `contracts/logging/formatter.py` | Native text, JSON, and console formatters; standard driver consumes it | Formatter and real file logging tests; custom formatter factories are typed against the protocol | Implemented and consumed |
| `LogProcessor` | `contracts/logging/processor.py` | Redaction and context processors; `LogChannel` consumes it | Processor ordering, redaction, and channel tests | Implemented and consumed |
| `LogCustomizer` | `contracts/logging/customizer.py` | Application customizers; `LogManager` and `LoggingServiceProvider` consume it | Provider static assignment and request logging lifecycle integration | Implemented and consumed |
| `LogWriter` | `contracts/logging/logger.py` | Native `logging.Logger`; application services and `Log` facade consume it | Default logger bound by `LoggingServiceProvider`; constructor injection and identity checked in application integration | Implemented, registered, and consumed |
| `LoggingManager` | `contracts/logging/manager.py` | `logging.LogManager`; application and `Log` facade consume it | Singleton factory registered by `LoggingServiceProvider`; configuration-driven construction, identity, and shutdown are integration-tested | Implemented, registered, and consumed |
| `LogBridge` | `contracts/logging/bridge.py` | `StandardLogBridge`; manager returns and owns it | Real standard-library logging bridge tests verify propagation and cleanup | Implemented and consumed |
| `DeliveryStatus` | `contracts/logging/delivery.py` | Native delivery result used by drivers and channels | Driver, background queue, stack delivery, and logger tests | Implemented shared domain type |

Logging extension contracts describe behavior, not backend types. Only
`LoggingManager` and the default `LogWriter` are application container
services. The logging manager and channels own drivers, formatters, processors,
bridges, and customizers.

## HTTP contracts

| Contract or type | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `HttpRequest` | `contracts/http/request.py` | `http.Request`; native route handlers, middleware, and helpers | Request-scoped under concrete and protocol keys; ASGI tests verify identity and input behavior | Implemented, registered, and consumed |
| `HttpResponse`, `ResponseFactory` | `contracts/http/response.py` | Native response classes and `NativeResponseFactory`; route dispatch and middleware | Factory registered by `HttpServiceProvider`; response and ASGI tests verify output and redirect rules | Implemented, registered, and consumed |
| `HttpMiddleware`, `RequestHandler` | `contracts/http/middleware.py` | Foundation middleware stack and route middleware | Resolved through the application Container; ordering and streaming tests cover execution | Implemented and consumed |
| `HttpClient`, `HttpClientResponse` | `contracts/http/client.py` | `HttpxClientAdapter`, native client response | Application singleton registration; loopback sync, async, stream, timeout, and shutdown tests | Implemented, registered, and consumed |

`OutgoingRequest`, `JsonValue`, query aliases, and `ServerSentEvent` are
transport-neutral values. HTTPX2 owns the outgoing pools. Starlette and
FastAPI own protocol parsing and ASGI response transmission.

## Routing contracts

| Contract | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `RouteCatalog`, `RouteInfo` | `contracts/routing/catalog.py` | `Router.routes`, `RouteDefinition`; URL generation, facade inspection, backend compilation, and Console `route:list` | One application-owned catalog; routing and Console lifecycle integration tests | Implemented, registered, and consumed |
| `UriUrlGenerator` | `contracts/routing/url_generator.py` | `routing.UrlGenerator`; URI factories, helpers, and named redirects | Registered under concrete and protocol keys; URI integration verifies shared identity | Implemented, registered, and consumed |
| `RouteAction`, `ControllerAction`, `RouteEndpoint` | `contracts/routing/types.py` | Route registration and dispatch annotations | Static checks and dispatch tests; these are type aliases, not protocols | Implemented |

Starlette and FastAPI own path matching and hosting. Titanspan's route catalog
is the source for registration, metadata, URL generation, and compiled routes.

## Support contracts

| Contract or type | Definition | Implementation and consumers | Registration and evidence | Status |
| --- | --- | --- | --- | --- |
| `HtmlRenderable` | `contracts/support/html_renderable.py` | `support.HtmlString` and `support.Uri`; encoded HTML utilities and helpers consume it | Static inheritance for `HtmlString`; URI, escaping, and HTML string behavior tests | Implemented and consumed |
| `DeferredDisplayValue` | `contracts/support/deferred_display_value.py` | Application-defined display values; `EncodedHtmlString` consumes it before escaping | Unit fixtures cover deferred trusted markup and plain-text escaping | Implemented extension point |
| `MessageBagProtocol` | `contracts/support/message_bag.py` | `support.MessageBag` structurally implements it; message consumers may depend on the read/write surface | Strict assignment in `test_contract_organization.py`; MessageBag behavior tests | Implemented and statically verified |
| `MessageProvider` | `contracts/support/message_bag.py` | `support.MessageBag.merge` consumes application-defined message providers | Structural fixture and merge behavior tests in `tests/unit/support/test_message_bag.py`; no built-in provider class | Implemented extension point |

`MessageKey` is a public shared type alias. `Scope` and `ServiceFactory` are
container domain values in `contracts/container`; `titanspan.container`
re-exports those same objects. Configuration key aliases, `ConfigArray`, and
logging `DeliveryStatus` are domain values rather than additional protocols.

## Private and test-only protocols

| Protocol | Owner | Consumer | Status |
| --- | --- | --- | --- |
| `_ByteConvertible` | `support.binary_codec` | Binary codec input normalization | Private implementation seam; tested by codec behavior and property tests |
| `_SharedConsumer` | Container unit tests | Test-only Dishka graph fixture | Test fixture, not a framework contract |
| `RepositoryContract` | Container dependency engine tests | Test-only contract binding fixture | Test fixture, not a framework contract |

## Abstract base classes

| Base class | Responsibility | Concrete subclasses | Evidence |
| --- | --- | --- | --- |
| `facades.Facade` | Share typed active-application container lookup without dynamic forwarding | `facades.Config`, `facades.Log` | `tests/integration/test_framework_cohesion.py` verifies both subclass the base and resolve their declared service contracts |

`Facade` is public reusable infrastructure, not a service contract. The
`ABC` in `tests/unit/container/test_container.py` is a test fixture for
abstract dependency-key resolution.

## Removed unowned public protocols

The first native API pass exported `MappingConvertible`, `JsonTextProvider`,
`Renderable`, `ResponseConvertible`, and `ValidatedData`. Repository audit
found that they had fixture-only implementations, no production consumers,
and no implemented HTTP, validation, JSON, or generic rendering owner. They
have been removed from public exports. Their tests now assert that future
domain boundaries are not advertised prematurely. The existing Support
methods and Python special methods remain available where useful.

## Application integration and remaining limits

`Application` creates one native `Container`, registers configuration,
logging, HTTP, and Routing services, then registers application providers.
Config, Log, Http, and Route facades resolve application services from the
active application context. Native routes use the same container and request
scope. Explicit external `Application.providers` values remain a separate
private interoperability graph; they do not split native route or framework
service identity.

`ConfigServiceProvider` registers `ConfigRepository`, `ConfigReader`, and
`ConfigWriter` to the same instance. It conditionally registers typed access,
scoped overrides, diagnostics, and macros only when the selected repository
implements those capabilities. `LoggingServiceProvider` resolves that
contract, reads `logging` configuration, applies explicit bootstrap
configuration last, and registers the resulting manager and logger.

`Repository.override()` snapshots effective values and keeps scoped writes
in the current context layer; base values remain unchanged after exit. The
configuration repository does not promise concurrent mutation of base values.

The application validates core metadata and resolves configuration and the
logging manager during composition, but it does not preflight every arbitrary
user service graph. The current container has no non-instantiating whole-graph
validation API. `Application.startup` and `Application.shutdown` coordinate
provider boot, resource finalization, cancellation shielding, and context
restoration for ASGI hosts and standalone owners.

`Application.asgi` and the explicit route `providers` input are documented
FastAPI interoperability boundaries. The public `Settings` class still
inherits methods from its private Pydantic-backed implementation. Those
backend surfaces are not required by configuration repository consumers, but
they remain visible limitations of the current public objects.

`examples/hello-world/app.py` is also exercised through a real ASGI test. It
uses a native service provider, a contract binding, auto-injected config and
logging services, facades, a native route, request-local identifiers, and
lifespan cleanup.

The installed distribution, ordinary public signatures, and module import
boundaries are checked by `make public-api-check`, `make architecture-check`,
and `make architecture-integration-test`. These checks prove different
properties; they do not establish every structural signature or behavior.
Database, cache, queue, validation, and workflow contracts remain deferred.
