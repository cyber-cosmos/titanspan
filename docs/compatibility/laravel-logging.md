# Laravel logging compatibility inventory

## Reference baseline

- Laravel framework release: `v13.44.1`.
- Exact source commit: `8a8c4a84852869e13190d89f9da873cd9a70f14c`.
- Verification date: 2026-11-25.
- [Pinned `LogManager.php`](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Log/LogManager.php)
- [Pinned `Logger.php`](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Log/Logger.php)
- [Pinned logging tests](https://github.com/laravel/framework/tree/8a8c4a84852869e13190d89f9da873cd9a70f14c/tests/Log)
- [Laravel 13 logging documentation](https://laravel.com/docs/13.x/logging)

The API inventory below covers public methods of `LogManager`, `Logger`,
`LogServiceProvider`, and the `MessageLogged` event. Protected Monolog
construction helpers are implementation hooks, not public method parity
requirements. The separate `Illuminate\Log\Context\Repository` API is
listed after the logging component inventory because it is a related context
service rather than a `LogManager` or `Logger` public method.

## Status key

- **Exact behavioural parity** means equivalent results and lifecycle for
  representable inputs.
- **Python-adapted parity** means the same capability with Python syntax,
  typed contracts, or async-aware lifecycle differences.
- **Delegated** means the corresponding behavior is owned by another
  Titanspan component and verified through that boundary.
- **Blocked** means the necessary framework component is not implemented.
- **Not applicable** means a PHP/backend-specific operation has no safe,
  useful Titanspan public equivalent.
- **Pending** means the capability remains to be implemented or verified.

## `Illuminate\Log\LogManager`

| Upstream API | Titanspan API | Implementation and evidence | Status and difference |
| --- | --- | --- | --- |
| `__construct($app)` | `LogManager(configuration, ...)` | `logging/manager.py`; manager and configuration tests | Python-adapted; receives native settings and factories, not a Laravel app container. |
| `build($config)` | `build(configuration)` | `manager.py`; `test_logging_public_api.py` | Python-adapted; built channels have explicit ownership and context management. |
| `stack($channels, $channel)` | `stack(channels, channel=...)` | `manager.py`, `drivers/stack.py`; `test_stack.py` | Python-adapted; deterministic ordered delivery and typed partial outcomes. |
| `channel($channel)` | `channel(name=None)` | `manager.py`; `test_manager.py` | Python-adapted; returns a native `Logger`. |
| `driver($driver)` | `driver(name=None)` | `manager.py`; `test_logging_public_api.py` | Python-adapted alias for channel resolution. |
| `shareContext($context)` | `share_context(...)`, `shareContext(...)` | `manager.py`; `test_manager_contracts.py` | Python-adapted; values live in the active execution context. |
| `sharedContext()` | `shared_context()`, `sharedContext()` | `manager.py`; `test_manager_contracts.py` | Python-adapted; returns a detached mapping snapshot. |
| `withoutContext($keys)` | `without_context(...)`, `withoutContext(...)` | `manager.py`; `test_manager_contracts.py` | Python-adapted; removes local and shared values in this execution context. |
| `flushSharedContext()` | `flush_shared_context()`, `flushSharedContext()` | `manager.py`; `test_manager_contracts.py` | Python-adapted; context-variable reset is task-local. |
| `getDefaultDriver()` | `get_default_driver()`, `getDefaultDriver()` | `manager.py`; `test_manager_contracts.py` | Python-adapted; returns the default channel name. |
| `setDefaultDriver($name)` | `set_default_driver(name)`, `setDefaultDriver(name)` | `manager.py`; `test_manager_contracts.py` | Python-adapted; validates against configured channel names. |
| `extend($driver, $callback)` | `extend(name, factory)` | `manager.py`; `test_logging_public_api.py`, `test_manager_contracts.py` | Python-adapted; factories return native `LogDriver` implementations. |
| `forgetChannel($driver)` | `forget_channel(name)`, `forgetChannel(name)`, `purge(name)` | `manager.py`; `test_manager_contracts.py` | Python-adapted; dependent cached stacks are also invalidated. |
| `getChannels()` | `get_channels()`, `getChannels()` | `manager.py`; `test_manager_contracts.py` | Python-adapted; returns a read-only snapshot of resolved channels. |
| `emergency($message, $context)` | `emergency(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted; context is a structured mapping plus keyword fields. |
| `alert($message, $context)` | `alert(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `critical($message, $context)` | `critical(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `error($message, $context)` | `error(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `warning($message, $context)` | `warning(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `notice($message, $context)` | `notice(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `info($message, $context)` | `info(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `debug($message, $context)` | `debug(...)` | `manager.py`, `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `log($level, $message, $context)` | `log(level, message, context, **values)` | `manager.py`, `logger.py`; `test_manager_contracts.py` | Python-adapted; accepts native enum, name, or RFC numeric severity. |
| `setApplication($app)` | None | `foundation/application.py` owns the manager lifecycle. | Not applicable; a manager is bound to an application at construction. |
| `__call($method, $parameters)` | Explicit typed methods | `manager.py` and `facades/log.py` | Not applicable; dynamic PHP magic forwarding is intentionally excluded. |

## `Illuminate\Log\Logger`

| Upstream API | Titanspan API | Implementation and evidence | Status and difference |
| --- | --- | --- | --- |
| `__construct($logger, $dispatcher)` | `Logger(channel, ...)` | `logging/logger.py`; manager and lifecycle tests | Python-adapted; accepts a native Titanspan channel, not a backend logger. |
| `emergency($message, $context)` | `emergency(...)`, `emergency_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted; async variant is Titanspan-specific. |
| `alert($message, $context)` | `alert(...)`, `alert_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `critical($message, $context)` | `critical(...)`, `critical_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `error($message, $context)` | `error(...)`, `error_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `warning($message, $context)` | `warning(...)`, `warning_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `notice($message, $context)` | `notice(...)`, `notice_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `info($message, $context)` | `info(...)`, `info_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `debug($message, $context)` | `debug(...)`, `debug_async(...)` | `logger.py`; `test_logging_public_api.py` | Python-adapted. |
| `log($level, $message, $context)` | `log(...)`, `log_async(...)` | `logger.py`; manager and background tests | Python-adapted; explicit async path offloads or awaits a native async driver. |
| `write($level, $message, $context)` | `write(...)` | `logger.py`; facade and manager public API tests | Python-adapted alias for dynamic severity logging. |
| `withContext($context)` | `with_context(...)`, `withContext(...)` | `logger.py`; `test_events.py` | Python-adapted; returns a bound logger rather than mutating it. |
| `withoutContext($keys)` | `without_context(...)`, `withoutContext(...)` | `logger.py`; `test_events.py` | Python-adapted; derived logger does not mutate the parent. |
| `listen($callback)` | `listen(callback)` | `channel.py`; `test_events.py` | Python-adapted; listeners receive `MessageLogged` after channel delivery status is known. |
| `getLogger()` | None | Private backend modules only. | Not applicable; exposes implementation-specific logger objects upstream. |
| `getEventDispatcher()` | None | The event dispatcher component is not implemented. | Not applicable; Titanspan exposes channel listeners, not a backend dispatcher. |
| `setEventDispatcher($dispatcher)` | None | The event dispatcher component is not implemented. | Not applicable; no global dispatcher can be installed on a logger. |
| `__call($method, $parameters)` | Explicit typed methods | `logger.py` | Not applicable; arbitrary backend method forwarding is excluded. |

## Provider and event

| Upstream API | Titanspan API | Implementation and evidence | Status and difference |
| --- | --- | --- | --- |
| `LogServiceProvider::register()` | `Application.logging` manager ownership | `foundation/application.py`; `test_logging_lifecycle.py` | Delegated; the application owns configuration, request binding, and shutdown. There is no independent service-provider abstraction yet. |
| `MessageLogged(level, message, context)` | `MessageLogged(record, status)` | `logging/events.py`, `channel.py`; `test_events.py` | Python-adapted; a sanitized immutable native record and explicit delivery status replace separate mutable fields. |

## Driver and capability inventory

| Upstream capability | Titanspan status | Evidence or difference |
| --- | --- | --- |
| Console / error output | **Python-adapted parity** | `console`, `stdout`, `stderr`, and `errorlog`; output uses native formatters. |
| Single file | **Python-adapted parity** | `single` delegates file ownership to standard logging handlers. |
| Daily file | **Python-adapted parity** | `daily` rotates at midnight and uses handler retention. |
| Size-rotating file | **Python-adapted parity** | `rotating` delegates rotation to a standard handler. |
| Monthly file | **Python-adapted parity** | A standard-library timed handler subclass rotates at UTC month boundaries and retains only matching monthly archives. |
| Syslog | **Python-adapted parity** | RFC severity is preserved through the private syslog adapter. |
| Slack | **Python-adapted parity** | Native JSON `text` payload to an explicit webhook; no Slack SDK dependency. |
| Stack and dynamic channels | **Python-adapted parity** | Native stack driver and owned on-demand channels. |
| Custom channel factories | **Python-adapted parity** | `LogManager.extend` registers native typed factories. |
| Custom formatter | **Python-adapted parity** | `extend_formatter` registers native formatter factories. |
| Tap customizers | **Python-adapted parity** | `ChannelConfiguration.tap` names registered native customizers that run once during channel construction; failures close unpublished resources. |
| Deprecation channel | **Pending** | Deprecation warning routing is not integrated with Python warnings. |
| Monolog handler / processor interoperability | **Not applicable** | Titanspan contracts and native drivers replace Monolog-specific extension objects. |
| Emergency fallback | **Python-adapted parity** | Minimal stderr fallback avoids recursion through the configured logger. |
| Laravel context repository persistence and hidden values | **Pending** | Context scopes, lookup, sharing, removal, and flushing exist; hidden, hydration, and dehydration operations do not. |
| Global event dispatcher integration | **Blocked** | Titanspan's general event dispatcher component is not implemented. Channel-local listeners are available. |

## Inventory counts

The method-level tables contain 45 public API entries: 39 applicable methods
have a Titanspan implementation or lifecycle delegation, and 6 backend- or
container-specific methods are marked not applicable. Thus the applicable
method mapping is **39 / 39 (100%)**. This percentage measures only those
listed public method endpoints; it does not claim full component parity.

The separate capability inventory includes pending and blocked Laravel
features. Upstream PHPUnit tests have been inspected as a specification, but
they have not yet been translated as a complete test suite. Existing
Titanspan unit and integration tests verify the implementation paths cited
above. Do not describe the component as fully Laravel-compatible until every
pending capability is resolved and upstream test traceability is complete.

## Implementation notes

The component uses Python's standard library logging handlers for streams,
files, rotation, and syslog, plus Structlog for isolated structured
dispatch. The public API exposes only Titanspan records, contracts, drivers,
formatters, processors, errors, and lifecycle operations. See
[Python handler documentation](https://docs.python.org/3/library/logging.handlers.html)
and the [Structlog standard-library integration guide](https://www.structlog.org/en/stable/standard-library.html).
