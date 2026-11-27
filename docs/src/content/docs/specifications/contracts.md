---
title: "Contracts component specification"
---

<span id="contracts-component-specification"></span>

`titanspan.contracts` contains dependency-independent Python interfaces,
organized by the domain that owns each shared boundary. The top-level package
provides convenience re-exports without declaring duplicate objects. A
contract defines a stable Titanspan-owned boundary; it does not imply that a
concrete framework service exists.

```text
contracts/
├── cache/
├── config/
├── container/
├── console/
├── events/
├── filesystem/
├── foundation/
├── hashing/
├── http/
├── logging/
├── pipeline/
├── queue/
├── routing/
├── support/
└── validation/
```

Add a domain package only when its first shared contract is established.
Component-private protocols remain in their owning component.

## Implemented public contracts

| Contract | Purpose | Owner or evidence |
| --- | --- | --- |
| `ConfigRepository` | Typed hierarchical configuration access and mutation | `titanspan.config.Repository`; `tests/unit/config/` |
| `ServiceContainer`, `AsyncServiceContainer` | Typed resolution and temporary context-local overrides | `titanspan.container.Container`; `tests/unit/container/`, `tests/unit/facades/` |
| `ServiceRegistry` | Native instance, transient, singleton, and scoped registration | `titanspan.container.Container`; provider conformance tests |
| `InstanceRegistration` | Explicit instance registration | `titanspan.container` |
| `HtmlRenderable`, `DeferredDisplayValue` | Trusted and deferred HTML boundaries | Support implementation and tests |
| `MessageBagProtocol`, `MessageProvider` | Read and provide keyed validation messages | `tests/unit/support/test_message_bag.py` |
| `LogDriver`, `AsyncLogDriver` | Synchronous and asynchronous record delivery | `titanspan.logging`; logging tests |
| `LogFormatter`, `LogProcessor`, `LogCustomizer` | Format, transform, and customize component records | `titanspan.logging`; logging tests |
| `DeliveryStatus` | Report the outcome known at the logging call boundary | `titanspan.logging`; delivery tests |
| `HttpRequest`, `HttpResponse`, `ResponseFactory`, `HttpMiddleware`, `ParameterizedHttpMiddleware`, `MiddlewareDeclaration` | Share request, response, and immutable middleware parameters | `titanspan.http`; ASGI routing integration tests |
| `HttpClient`, `HttpClientResponse` | Share pooled outgoing request behavior | HTTPX adapter; loopback integration tests |
| `EventDispatcher` | Register, inspect, defer, fake, and dispatch application events | `NativeEventDispatcher`; service-provider and application integration tests |
| `FileMetadata`, `StorageDisk`, `StorageManager` | Describe named disks and backend-independent file metadata | `titanspan.filesystem`; real fsspec and application integration tests |
| `Hasher`, `HashMetadata`, `HashVerification` | Hash creation, verification results, and encoding metadata | `HashingManager` over `argon2-cffi` and `bcrypt`; real Argon2, Bcrypt, and application integration tests <!-- pragma: allowlist secret -->
| `RouteCatalog`, `RouteInfo`, `UriUrlGenerator` | Share route inspection and URL generation | `titanspan.routing`; route and URI integration tests |
| `PipelineContinuation`, `PipelineMiddlewareHandler` | Type sequential continuation callbacks | `titanspan.pipeline`; Pipeline unit tests |
| `ValidationService`, `ValidationRule`, `AsyncValidationRule` | Validate typed values and apply ordered application rules | `titanspan.validation`; `tests/integration/validation/test_validation_application.py` |
| `CommandRegistrar`, `ConsoleCommand`, `ConsoleOutput`, `ProgressTask` | Share command registration and terminal output behavior | `titanspan.console.Console`, `TerminalOutput`; Console unit and Foundation integration tests |
| `CacheRepository`, `CacheStore`, `CacheLock`, `CacheCapabilities` | Share typed cache access, backend capabilities, and owner-checked locks | `titanspan.cache.CacheManager`; real memory and Redis integration tests |
| `QueueDispatcher`, `BusDispatcher`, `PendingDispatch`, `ChainBuilder`, `BatchBuilder`, `BatchHandle` | Share canonical job dispatch and native Bus builder behavior | `titanspan.queue.QueueManager`; application and real Redis worker tests |
| `JobContext`, `JobMiddleware`, `SyncJobMiddleware` | Expose immutable execution metadata and typed middleware continuation | `titanspan.queue`; native Container and job-scope integration tests |

`Scope` and `ServiceFactory` are container domain values in Contracts and are
re-exported by `titanspan.container` with canonical object identity.

Logging protocols are generic over the owning component's record or logger
type. The shared package therefore does not import concrete records, loggers,
or backend types. `titanspan.logging` re-exports the same contract objects
for application convenience.

Response conversion, generic mapping conversion, JSON-text, and general
rendering protocols are not public contracts. They had no production owner or
consumer; their fixture-only declarations were removed. Validation owns the
validated-data boundary through `ValidationService` and its typed result.

## Typing and semantics

- Use `Protocol` for structural behavior. Use abstract base classes only when
  nominal inheritance or shared behavior is required.
- Keep contracts small and capability-oriented. Do not require optional
  operations from every implementation.
- Use generics to preserve relationships between inputs and outputs.
- Use standard Python types and Titanspan domain types in public signatures.
  Backend types and exceptions belong behind adapters.
- Document missing values, failures, side effects, mutation, ordering,
  lifecycle, and concurrency semantics when they apply.
- Runtime protocol checks detect attribute presence only. They do not prove
  signature or behavioral conformance.

## Deferred boundaries

Contracts for Database, AI, workflows, telemetry, and other unimplemented
components remain deferred until their owning architecture is established.
A roadmap item is not a public contract.

## Verification

Unit contract checks are in `tests/unit/contracts/`. Real component
conformance is tested in `tests/integration/` alongside each implemented
owner. Container integration tests verify that native contracts are valid
dependency keys without exposing the dependency engine.
