---
title: "Facade behavioral specification"
---

<span id="facade-behavioral-specification"></span>

The shared `Facade` base resolves application-owned contracts through the
active Foundation context. Component facades retain explicit typed methods.
They do not keep an independent service registry or forward unknown
attributes.

## Implemented API

| API | Behavior | Evidence |
| --- | --- | --- |
| `service_contract` | Declares the native contract used by the facade. | `tests/integration/test_framework_cohesion.py` |
| `resolve_service()` | Resolves the contract through the active Container. | `tests/unit/facades/test_base.py` |
| `resolve_from_container(container)` | Resolves the declared contract from an explicit `ServiceContainer`. | `tests/integration/test_framework_cohesion.py` |
| `active_container()` | Returns the Container selected by the active application context. | `tests/integration/test_framework_cohesion.py` |
| `use(service)` | Returns the Container's temporary replacement context for this contract. | `tests/unit/facades/test_base.py` |

The shared base is used by `Config`, `Log`, `Http`, `Route`, and `Event`.
Dedicated HTTP, Routing, Events, Configuration, and Logging integration tests
verify their production service paths.

## Resolution and ownership

- Each call resolves through the active application context.
- The Container owns service lifetimes and shared instance identity.
- The Facade base does not cache services.
- A facade replacement uses the canonical Container override mechanism.
- The caller owns an instance passed to `use()`.
- Container-created resources in the override graph follow Container cleanup
  rules.
- Component fake state remains local to its component's test facility.

`use()` accepts a service instance that satisfies the facade's declared
contract. It does not create an independent registry. The Container rejects
unsafe overrides during active scopes or when an existing singleton would
retain a replaced dependency.

## Context restoration

The Container override mechanism isolates nested and concurrent execution
contexts. It restores the prior graph after normal exit, exceptions, and
cancellation. Applications remain independent because each application owns
its own Container.

`Log.fake()` installs a temporary manager through `Log.use()` and keeps only
fake assertion state in a ContextVar. The fake manager closes when its scope
exits. The supplied manager remains caller-owned when passed to `use()`.

## Limitations

- Facades require an active application context.
- `Facade.use()` replaces instances only; use the Container API when a
  temporary factory or asynchronous resource is required.
- A facade does not expose arbitrary service-container methods.
- Component fakes may have distinct activation and assertion APIs.

## Verification

The base tests cover nested replacement, exception restoration, concurrent
task isolation, and cancellation. Cross-component tests verify configuration
replacement through direct resolution and Support helpers, and verify that
injected and facade-resolved logging use one fake service.
