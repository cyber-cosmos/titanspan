---
title: "Testing Cache"
---

<span id="testing-cache"></span>

Cache.fake installs a context-local memory substitute through the
application-owned manager. Facade calls, injected repositories, and direct
manager repositories resolve the same fake while the scope is active.

~~~python
with Cache.fake() as cache:
    Cache.put("invoice:42", {"paid": True})
    cache.assert_has("invoice:42")
    cache.assert_missing("invoice:43")
    cache.assert_performed("put", "invoice:42")
~~~

Use a named store when a test should isolate one backend:

~~~python
with Cache.fake("redis") as cache:
    await Cache.store("redis").put_async("profile:42", {"active": True})
    cache.assert_has("profile:42", store="redis")
~~~

Fake scopes support synchronous and asynchronous context managers. Nested
scopes restore their previous fake after exit, including exceptions and
cancellation. A fake does not initialize or contact the configured
production backend.

CacheFake provides assert_has, assert_missing, assert_performed,
assert_not_performed, assert_hit, assert_missed, and assert_lock_acquired.
Its 10,000-entry operation ledger retains only operation names, keys, and
result flags. It drops the oldest records at capacity. Do not include
production values in assertions or diagnostics.

Test backend capabilities through the real memory integration. Redis
integration tests start a local redis-server when it is installed and skip
when the binary or optional redis package is unavailable. Tests should cover
the selected production backend when a local service is part of the
developer or CI environment.

Use explicit expiration values and bounded AnyIO task groups for
concurrency tests. Do not sleep for long intervals when a fake clock or a
short local Redis lease can test the behavior deterministically.
