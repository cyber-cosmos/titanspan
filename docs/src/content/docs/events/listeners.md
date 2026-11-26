---
title: "Listeners and discovery"
---

# Listeners and discovery

Register listeners explicitly through the active `Event` facade or an
injected `EventDispatcher`. Runtime registration remains available after
application startup. The dispatcher synchronizes registry changes and takes
stable listener snapshots before it runs application code.

## Listener forms

The dispatcher accepts functions, callable objects, listener classes, and
`ListenerReference` values. Listener classes are resolved on each dispatch
through the active native container. The container controls their lifetime.
Explicit listener instances remain owned by the registration that retains
them.

A function decorator declares discovery metadata. It does not register a
listener during import:

```python
@listener(DocumentProcessed)
async def update_index(event: DocumentProcessed) -> None:
    """Update the search index after document processing.

    Args:
        event: Completed document information.
    """
    await search_index.update(event.document_id)
```

## Subscribers

A subscriber groups related handlers. Implement `subscribe(dispatcher)` to
register methods directly or return an event-to-handler mapping. Mark a class
with `@subscriber` to include it in configured discovery. Discovery resolves
subscriber classes through the container during application startup.

Class subscribers retain their class and method names. The Container resolves
each method in the active dispatch scope. An explicit instance subscriber
retains that instance through its method references. Pass application-lifetime
instances when those methods outlive their creation scope.

## Trusted discovery

Set `events.discovery_modules` to explicit importable application modules.
The provider imports only those modules during application startup. It does
not scan installed dependencies or arbitrary filesystem paths.

Discovery registers decorated functions, classes with `handle()`, methods
named `handle_*`, and explicitly marked subscribers. Listener method event
parameters require resolved type hints. Union annotations register each
member in order. Inherited methods are found by Python inspection; discovery
does not infer an event from an unannotated method.

Import errors and unresolved annotations fail startup with
`EventDiscoveryError`. Review configured modules as trusted application
code.

## Discovery manifests

Set `events.manifest_path` to enable a JSON discovery manifest. The manifest
stores trusted module names, module source hashes, versioned listener
metadata, and a document digest. It does not store callbacks, event objects,
containers, or live resources. The loader rejects stale, malformed, or
untrusted metadata.

Use `inspect_events()`, `cache_events()`, and `clear_event_cache()` from
`titanspan.events` to inspect or manage a manifest. These functions use the
same trusted module list as startup discovery.

The Console component does not yet provide event list, cache, or clear
commands. Those commands require integration with the canonical CLI and
application loading conventions.

## Configuration

Events reads its settings from the canonical `ConfigRepository` under the
`events` key. `EventsConfiguration` rejects unknown fields and validates:

| Setting | Default | Purpose |
| --- | --- | --- |
| `discovery_modules` | `()` | Trusted modules to inspect at startup. |
| `manifest_path` | `None` | Optional JSON manifest path. |
| `deferred_buffer_limit` | `10000` | Maximum events per deferred or pushed buffer. |
| `max_dispatch_depth` | `32` | Maximum nested dispatch depth per execution. |

Configuration values are validated through the existing Pydantic settings
capability. Events does not read environment variables directly.
