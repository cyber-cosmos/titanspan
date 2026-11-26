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
├── config/
├── container/
├── events/
├── foundation/
├── http/
├── logging/
├── routing/
└── support/
```

Add a domain package only when its first shared contract is established.
Component-private protocols remain in their owning component.

## Implemented public contracts

| Contract | Purpose | Owner or evidence |
| --- | --- | --- |
| `ConfigRepository` | Typed hierarchical configuration access and mutation | `titanspan.config.Repository`; `tests/unit/config/` |
| `ServiceContainer`, `AsyncServiceContainer` | Typed sync-safe and async dependency resolution | `titanspan.container.Container`; `tests/unit/container/` |
| `ServiceRegistry` | Native instance, transient, singleton, and scoped registration | `titanspan.container.Container`; provider conformance tests |
| `InstanceRegistration` | Explicit instance registration | `titanspan.container` |
| `HtmlRenderable`, `DeferredDisplayValue` | Trusted and deferred HTML boundaries | Support implementation and tests |
| `MessageBagProtocol`, `MessageProvider` | Read and provide keyed validation messages | `tests/unit/support/test_message_bag.py` |
| `LogDriver`, `AsyncLogDriver` | Synchronous and asynchronous record delivery | `titanspan.logging`; logging tests |
| `LogFormatter`, `LogProcessor`, `LogCustomizer` | Format, transform, and customize component records | `titanspan.logging`; logging tests |
| `DeliveryStatus` | Report the outcome known at the logging call boundary | `titanspan.logging`; delivery tests |
| `HttpRequest`, `HttpResponse`, `ResponseFactory`, `HttpMiddleware` | Share request, response, and middleware behavior | `titanspan.http`; ASGI and lifecycle tests |
| `HttpClient`, `HttpClientResponse` | Share pooled outgoing request behavior | HTTPX adapter; loopback integration tests |
| `EventDispatcher` | Register, inspect, defer, fake, and dispatch application events | `NativeEventDispatcher`; service-provider and application integration tests |
| `RouteCatalog`, `RouteInfo`, `UriUrlGenerator` | Share route inspection and URL generation | `titanspan.routing`; route and URI integration tests |

`Scope` and `ServiceFactory` are container domain values in Contracts and are
re-exported by `titanspan.container` with canonical object identity.

Logging protocols are generic over the owning component's record or logger
type. The shared package therefore does not import concrete records, loggers,
or backend types. `titanspan.logging` re-exports the same contract objects
for application convenience.

Response conversion, validated-data, generic mapping conversion, JSON-text,
and general rendering protocols are not public contracts. They had no
production owner or consumer; their fixture-only declarations were removed.
Validation contracts remain pending until that component has a production
implementation and a tested application boundary.

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

Contracts for database, cache, queue, filesystem, AI, workflows, telemetry,
and other unimplemented components remain deferred until their owning
architecture is established. A roadmap item is not a public contract.

## Verification

Unit contract checks are in `tests/unit/contracts/`. Real component
conformance is tested in `tests/integration/` alongside each implemented
owner. Container integration tests verify that native contracts are valid
dependency keys without exposing the dependency engine.
