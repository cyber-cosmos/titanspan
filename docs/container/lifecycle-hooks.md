# Service extensions and resolution callbacks

## Service extensions

Register decorators before graph composition to transform a service in a
predictable order:

```python
container.extend(Repository, add_metrics)
container.extend(Repository, add_cache)
```

Extensions run in registration order when the dependency engine constructs
the service. The selected lifetime caches the final decorated result. A
synchronous extension works with `make`; an asynchronous extension requires
`make_async` and causes synchronous preflight to raise
`AsyncResolutionRequiredError` before constructing a partial cached value.

An extension must return a value satisfying the registered service contract.
If it wraps an owned resource, the wrapper must forward cleanup to the
resource it owns. The container cannot infer arbitrary ownership introduced
inside extension code.

## Resolution callbacks

Use lifecycle callbacks to observe or validate public service requests:

```python
container.before_resolving(Repository, record_request)
container.resolving(Repository, validate_repository)
container.after_resolving(Repository, emit_ready_event)
```

Callbacks run for each public root request, including retrieval of a cached
value. Ordering is: matching before callbacks, resolution, matching resolving
callbacks, then matching after callbacks. Register `None` as the service key
to observe all root requests. A callback failure propagates and prevents later
callbacks from running.

Synchronous callbacks run on the calling thread. If any matching callback is
asynchronous, sync resolution raises `AsyncResolutionRequiredError` before
constructing the requested service; use `make_async`. Callbacks do not run for
each dependency created internally by a graph. Recursive resolution of the
same service from its callback is rejected. Registration freezes with the
container graph.
