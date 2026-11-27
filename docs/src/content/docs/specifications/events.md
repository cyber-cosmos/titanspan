---
title: "Events behavioral specification"
---

# Events behavioral specification

This specification describes verified behavior in `titanspan.events`. It
also identifies reference capabilities that await other Titanspan
components. Laravel 13 informed the developer experience and semantics; it
does not define a compatibility contract for Titanspan.

## Reference pin and implementation boundary

The behavioral review used Laravel framework commit
[`321caf77d6c037577434e177c3bf280abb2b3513`](https://github.com/laravel/framework/tree/321caf77d6c037577434e177c3bf280abb2b3513)
and the [Laravel 13 Events documentation](https://laravel.com/docs/13.x/events).
Laravel's event system is released under the MIT License. Titanspan uses it
as a behavioral reference and does not include Laravel source code or claim
Laravel compatibility.

Blinker `1.9.0` owns listener registration and receiver references. The
adapter uses its public `Signal.connect()`, `disconnect()`, and
`receivers_for()` APIs, plus the documented `Signal.set_class` customization
point. A private ordered receiver set preserves Titanspan's ordering policy
because Blinker does not promise default receiver order. Titanspan adapts
Blinker's registration snapshots for its result, short-circuit, and
sequential-await semantics. It does not keep a second listener registry.

## Capability inventory

| Laravel 13 capability | Titanspan status | Python behavior or limitation |
| --- | --- | --- |
| Object and named event dispatch | Adapted | Uses ordinary Python objects, class selectors, or names. Events are not automatically serialized. |
| Listener registration and lookup | Implemented | Functions, callable objects, listener classes, method references, duplicate registrations, lookup, removal, and removable handles. |
| Inheritance and interface listeners | Adapted | Uses `isinstance()` for Python base classes and runtime-checkable protocols. Other protocols fail clearly. |
| Wildcard event listeners | Adapted | Uses fully qualified Python names and `fnmatchcase()` patterns. Matching runs at dispatch time without a name cache. |
| Listener response collection | Adapted | Returns ordered Python lists; exact `False` stops propagation and is excluded. |
| Halting dispatch | Implemented | `until()` returns the first non-`None` response, including false-like values. |
| Sync and async listener execution | Adapted | Explicit sync and async methods; mixed listeners run sequentially on the async path. |
| Listener dependency injection | Adapted | Listener classes and remaining callback parameters use the active Titanspan Container. Explicit event arguments win. |
| Event subscribers | Implemented | Imperative registration and returned event-to-handler mappings; class instances resolve through the Container. |
| Listener decorators and discovery | Adapted | Metadata decorators avoid import-time global registration. Only configured trusted modules load. |
| Discovery manifest and cache | Adapted | Deterministic JSON, module hashes, digest validation, and explicit inspect/cache/clear functions. No executable object serialization. |
| Event facade and dispatch helpers | Implemented | Facade, helpers, injected contract, and app dispatcher resolve one canonical service. |
| Event fakes and assertions | Adapted | Context-local all, selected, or except fakes; nested restoration; records and count/predicate assertions. |
| Deferred events | Adapted | Bounded sync and async context managers; successful frames flush in order and failed frames discard. |
| Pushed events | Adapted | Named payloads remain in memory after flush, repeat on later flush, and clear explicitly. |
| Queued listeners, retries, and queue metadata | Deferred | Queue owns jobs, serialization, backoff, uniqueness, middleware, and failure handling. Events does not execute queued listeners inline. |
| Dispatch after database commit | Deferred | Database owns transaction state and nested callbacks; Events still needs an explicit adapter for transaction-aware dispatch. |
| Broadcasting and remote delivery | Deferred | Broadcasting must own channels, authorization, brokers, delivery, and distributed guarantees. |
| Event CLI inspection | Implemented | The native Console exposes event list, cache, and clear commands through the discovery API. |
| Event generation | Deferred | Console artifact generators remain pending. |
| Automatic application event guessing | Adapted | Explicit module configuration and decorators or annotations replace framework path guessing. |
| PHP namespaces and object serialization rules | Not applicable | Titanspan uses Python module identity and ordinary in-process object references. |

## Event selection and payloads

Class events use the event object's fully qualified `module.qualname` for
diagnostics and wildcard matching. Exact class registrations compare by
identity. Base classes and runtime-checkable protocols use `isinstance()`.
Invalid protocol checks raise `EventRegistrationError` rather than hiding a
Python `TypeError`.

Named event strings must not be empty. Exact named listeners receive one
explicit payload argument. An omitted payload invokes a zero-argument
listener; explicit `None` is passed as a real value. A named wildcard
listener receives the canonical event name followed by the payload. An
omitted wildcard payload uses an empty tuple. A wildcard listener for a class
event receives the canonical class name and a one-element tuple containing
the original event object.

Patterns use `fnmatchcase()` behavior (`*`, `?`, and character classes).
This is a Python-specific extension of the reference's star-pattern syntax.
No wildcard cache exists, so user-generated names do not grow an unbounded
cache.

## Ordering and results

The dispatcher takes one receiver snapshot before listener execution. Exact
class or name matches run first, wildcard matches second, and inherited
class or protocol matches third. Each category retains registration order.
When one registration contains multiple matching selectors, it runs once in
the highest-priority category. Separate duplicate registrations each run.

Registration and removal during listener execution affect later dispatches.
They do not mutate the current snapshot. The dispatcher never holds its
registry lock while application callbacks execute.

Ordinary `dispatch()` and `dispatch_async()` return one Python list of
responses. `None`, zero, empty strings, and empty collections are retained.
Only the exact boolean `False` halts ordinary propagation, and that response
is omitted. `until()` and `until_async()` stop at the first non-`None`
response and return it.

Listener exceptions propagate unchanged and prevent later listeners from
running. Async dispatch awaits each listener before invoking the next. Sync
dispatch rejects coroutine functions and declared awaitable return types
before invoking any listener. An awaitable returned behind a broad or
unresolved annotation is detected at invocation time. Dispatch closes
coroutine results and raises `AsyncDispatchRequiredError`; earlier sync
listeners may have run. The Container has no public non-resolving inspection
for async-only dependency paths, so a listener whose injected dependency
requires async construction can fail after earlier listeners run. Container
resolution and listener construction failures propagate normally.

## Registration and injection

`listen()` accepts functions, callable objects, classes with `handle()`, and
`ListenerReference(target, method)` values. It returns a handle that removes
one registration. `forget()` removes matching selector registrations and can
also restrict removal to the same target object.

Event payload parameters take precedence over automatic injection. Listener
classes resolve from the active Container for each dispatch and are not
cached by Events. The Container owns singleton and scoped instance lifetime.
Functions, bound methods, and callable objects use the Container's explicit
`call()` or `call_async()` capabilities for remaining dependencies.

## Subscribers and discovery

Subscribers expose `subscribe(dispatcher)`. They can register listeners
directly or return a mapping from event selectors to method names or listener
objects. Class subscribers retain class and method metadata. Dispatch resolves
the method in the active scope. Explicit instance subscribers remain owned by
their registration. `subscribe_async()` supports async subscribers.
Discovery requires the `@subscriber` marker for subscriber classes.

Discovery inspects only configured absolute module names. It registers
decorated functions, class `handle()` methods, and methods named `handle_*`
with resolved event type hints. A union annotation registers its class
members. Discovery fails on import errors, unsupported event annotations,
or unresolved type hints. It does not scan dependency packages or arbitrary
paths.

`DiscoveryEntry` stores module and qualified member names, optional method
names, selectors, and subscriber markers. The JSON manifest stores those
entries, configured modules, source digests, and a manifest digest. Loading
imports configured trusted modules first, checks source and document hashes,
and resolves members from those modules. A stale or malformed manifest fails
closed. Modules backed by non-source or dynamically generated code cannot
use the manifest cache.

Application startup runs the `EventServiceProvider` after registration.
Configured discovery completes before application work begins. Runtime
listener registration remains synchronized and available after startup.

## Deferred and pushed dispatch

`defer()` and `defer_async()` use `ContextVar` frames and bounded event lists.
An event is buffered by the first active frame whose selector matches. A
nonmatching inner frame allows the event to reach a matching parent frame.
Successful frames dispatch their own events at exit. Nested successful
frames flush before the parent resumes. Exceptions and cancellation discard
the exiting frame's events and restore previous context state.

Child tasks inherit context values under Python `ContextVar` rules. A child
dispatch joins an active inherited frame. If that frame closes before the
child dispatches, the child follows any active parent frame or dispatches
normally. Deferred work is not durable and is not tied to database
transactions.

`push(name, payload)` stores a bounded in-memory payload. `flush(name)`
dispatches a snapshot and retains stored payloads for repeat flushes.
`forget_pushed()` clears all pushed values. Push and flush do not submit jobs
to a queue.

## Fakes

`fake()` intercepts all events or a selected set. `fake_except()` intercepts
all events outside its exclusion set. Fakes store event and payload object
references, not serialized copies. Nested fake contexts restore their
predecessor after success, failure, or cancellation. Independent async task
contexts do not share mutable fake stacks; a child task inherits the stack it
is created under. A fake is inactive after its context exits.

The fake supports filtering by event selector or predicate, dispatch count
assertions, negative assertions, and empty-dispatch assertions. It intercepts
the canonical dispatcher, so facade, helper, and injected calls use the same
behavior.

## Configuration and lifecycle

Events reads `events` values from `ConfigRepository` and validates them with
`EventsConfiguration`, a Pydantic model. Defaults are an empty discovery
module tuple, no manifest, a 10,000-event buffer limit, and a dispatch depth
limit of 32. Unknown settings fail application composition.

Each `Application` owns a single dispatcher registered under both the
`EventDispatcher` contract and `NativeEventDispatcher` implementation. The
facade resolves the contract from the active application. Independent
applications do not share listener registries. The global registry lock
protects only Blinker registration and snapshots. Listeners run outside the
lock; async listeners are sequential within one dispatch.

The depth limit prevents unbounded direct recursion. Events does not create
threads, processes, tasks, or event loops. Cancellation propagates through
async dispatch and resource cleanup remains owned by the Container and
Application lifecycles.

## Pending component integrations

| Component | Required ownership before integration |
| --- | --- |
| Queue | Durable jobs, safe payload serialization, retries, backoff, uniqueness, queue selection, middleware, and worker lifecycle. |
| Database | Transaction state and nested commit and rollback callbacks; Events must register dispatch through the canonical Database boundary. |
| Broadcasting | Remote channels, authorization, brokers, delivery guarantees, and transaction-aware publication. |
| Console | Application and event/listener generators. |
| Streaming | Bounded high-frequency token and progress streams. |
| Workflows | Replay-safe event delivery and checkpoint coordination. |

No pending integration silently executes inline, serializes arbitrary
closures, or claims durable, distributed, transactional, or exactly-once
delivery.

## Verification and performance

Unit and real Application integration tests live under `tests/unit/events/`
and `tests/integration/events/`. Informational dispatch, listener, wildcard,
container, asynchronous, discovery, and high-volume benchmarks live in
`benchmarks/test_events.py`. Benchmarks compare the component with direct
Python invocation and report measured results without a shared-runner
threshold.
