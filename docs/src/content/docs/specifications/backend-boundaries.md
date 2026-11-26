---
title: "Public backend boundaries"
---

<span id="public-backend-boundaries"></span>

Titanspan owns public contracts, application integration, and lifecycle rules.
Selected libraries own mature infrastructure behind private adapters.

| Component | Delegated infrastructure | Titanspan-owned behavior |
| --- | --- | --- |
| Container | Dishka graph validation, construction, caching, and resource cleanup | Native bindings, discovery, contextual injection, scopes, and exceptions |
| Config | Pydantic Settings validation and `python-dotenv` parsing | Repository behavior, source precedence, safe diagnostics, and cache format |
| Logging | Structlog processing and Python logging handlers | Records, channels, redaction, delivery policy, and application lifecycle |
| HTTP server | Starlette request, response, and ASGI handling | Typed contracts, request limits, and request resource ownership |
| HTTP client | HTTPX2 transports, pools, and protocol handling | Immutable request options, retry policy, and application ownership |
| Routing | FastAPI and Starlette matching and ASGI hosting | Route catalog, metadata, controller dispatch, constraints, and URL generation |
| Collections | Python iterators, mappings, and standard operations | Ordered eager and lazy APIs, including equality for unhashable values |
| CLI | Typer parsing and Rich terminal output | Framework commands and application service integration |

## Public interoperability boundaries

| Surface | Purpose | Limitation |
| --- | --- | --- |
| `Application.asgi` | Expose the configured ASGI host | FastAPI APIs remain backend-specific outside Titanspan's HTTP and Routing APIs. |
| `Application.providers` | Accept explicit external provider integrations | This optional input may create a separate private provider graph. Native services use the application Container. |
| `Settings` | Define typed application settings | The native class subclasses a private Pydantic Settings base. Inherited Pydantic methods remain visible through its method resolution order. |

Native routes and framework services use the same application Container.
The external provider boundary remains for explicit interoperability.
Ordinary native application code does not need backend imports.

## Delegation rule

Keep an adapter when it provides a stable Titanspan contract, security policy,
lifecycle ownership, or application integration. Delegate protocol parsing,
transport pools, graph execution, route matching, and retry scheduling to the
selected libraries. Do not add an adapter that only renames a backend type.

The public Settings inheritance limit needs a separate API design. A
composition-based replacement must preserve typed fields, validation, source
precedence, and editor support.
