# Laravel Contracts compatibility inventory

## Pinned upstream baseline

- Laravel framework release: `v13.44.1`.
- Exact commit: `8a8c4a84852869e13190d89f9da873cd9a70f14c`.
- Verified against the official Laravel release history on 2026-11-25.
- Immutable source tree: [Laravel at `8a8c4a84852869e13190d89f9da873cd9a70f14c`](https://github.com/laravel/framework/tree/8a8c4a84852869e13190d89f9da873cd9a70f14c).
- Official API guide: [Laravel Contracts 13.x](https://laravel.com/docs/13.x/contracts).

The exact release and commit match the Support and Logging compatibility baseline. Inventory data was read from the pinned source archive; the moving `13.x` branch is not used as the implementation target.

## Inventory scope and measurement

The pinned source tree contains **145 interfaces** and **11 concrete class declarations** across **39 namespaces**. The matrix lists every method declared directly by those interfaces. Inherited contracts are listed in each interface's parent declaration and their members are inventoried at the parent declaration rather than duplicated. The inventory contains all direct interface methods, including marker interfaces with no methods.

The counts below use direct interface method declarations as the denominator. They do not expand inherited methods or count the concrete exception/helper classes. Upstream PHPDoc parameter and return types are recorded where present. The source link is authoritative for full behavioral semantics. A matching method name alone is not compatibility evidence.

No Laravel implementation or PHPUnit test code was copied or adapted for this contract slice. The existing third-party notice retains the project's MIT attribution for its pinned API reference.

## Inherited API surfaces

Internal Illuminate parent interfaces are recorded at their own declarations above; a child inherits those methods without a second method row. The upstream tree also extends external standards and PHP built-in interfaces. Their inherited methods are listed here so the surface is accounted for without inflating the direct Laravel method compatibility percentage.

| Parent interface/API | Titanspan equivalent | Status | Evidence and difference | Reference |
| --- | --- | --- | --- | --- |
| `Psr\SimpleCache\CacheInterface.get` <code>(string $key, mixed $default = null) -> mixed</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.set` <code>(string $key, mixed $value, null&#124;int&#124;DateInterval $ttl = null) -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.delete` <code>(string $key) -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.clear` <code>() -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.getMultiple` <code>(iterable&lt;string&gt; $keys, mixed $default = null) -> iterable&lt;string, mixed&gt;</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.setMultiple` <code>(iterable $values, null&#124;int&#124;DateInterval $ttl = null) -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.deleteMultiple` <code>(iterable&lt;string&gt; $keys) -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\SimpleCache\CacheInterface.has` <code>(string $key) -> bool</code> | — | **Blocked** | Cache repository is not implemented. | [PSR-16 source 3.0.0](https://github.com/php-fig/simple-cache/blob/3.0.0/src/CacheInterface.php) |
| `Psr\Container\ContainerInterface.get` <code>(string $id) -> mixed</code> | `ServiceContainer.get` / `get_async` | **Python-adapted compatibility** | Titanspan uses typed class keys and explicit synchronous or asynchronous methods, so this is not a PSR-11 implementation. | [PSR-11 source 2.0.2](https://github.com/php-fig/container/blob/2.0.2/src/ContainerInterface.php) |
| `Psr\Container\ContainerInterface.has` <code>(string $id) -> bool</code> | — | **Blocked** | No native container adapter or entry-existence operation exists. | [PSR-11 source 2.0.2](https://github.com/php-fig/container/blob/2.0.2/src/ContainerInterface.php) |
| `Monolog\Processor\ProcessorInterface.__invoke` <code>(LogRecord $record) -> LogRecord</code> | — | **Not applicable** | Titanspan's logging processor uses its native `process` method and record type. Monolog types are not public Contracts API. | [Monolog source 3.9.0](https://github.com/Seldaek/monolog/blob/3.9.0/src/Monolog/Processor/ProcessorInterface.php) |
| PHP `ArrayAccess.offsetExists` <code>(mixed $offset) -> bool</code> | — | **Not applicable** | `ValidatedData` is a read-only Python mapping view and does not promise PHP offset-presence semantics. | [PHP manual](https://www.php.net/manual/en/class.arrayaccess.php) |
| PHP `ArrayAccess.offsetGet` <code>(mixed $offset) -> mixed</code> | `ValidatedData.__getitem__` | **Contract defined, implementation pending** | Typed mapping retrieval adapts the read operation; no production ValidatedData implementation exists. | [PHP manual](https://www.php.net/manual/en/class.arrayaccess.php) |
| PHP `ArrayAccess.offsetSet` <code>(mixed $offset, mixed $value) -> void</code> | — | **Not applicable** | Validated data is intentionally exposed read-only. | [PHP manual](https://www.php.net/manual/en/class.arrayaccess.php) |
| PHP `ArrayAccess.offsetUnset` <code>(mixed $offset) -> void</code> | — | **Not applicable** | Validated data is intentionally exposed read-only. | [PHP manual](https://www.php.net/manual/en/class.arrayaccess.php) |
| PHP `IteratorAggregate.getIterator` <code>() -> Traversable</code> | `ValidatedData.__iter__` | **Contract defined, implementation pending** | Iteration is expressed through Python's iterator protocol; no production ValidatedData implementation exists. | [PHP manual](https://www.php.net/manual/en/class.iteratoraggregate.php) |
| PHP `Countable.count` <code>() -> int</code> | `MessageBag.__len__` | **Python-adapted compatibility** | Verified against the canonical Support implementation in `tests/unit/support/test_message_bag.py`. | [PHP manual](https://www.php.net/manual/en/class.countable.php) |

The inherited API inventory contains 16 unique members beyond the 564 direct Laravel interface methods. `ContainerInterface.get` is listed for traceability but is already declared directly by Laravel, so it is not counted twice. The additional members come from PSR-16, PSR-11, Monolog, and PHP's built-in interfaces.

## Upstream namespaces

The inventory covers every namespace directory in the pinned source tree:

- `Illuminate\Contracts\Auth`
- `Illuminate\Contracts\Auth\Access`
- `Illuminate\Contracts\Auth\Middleware`
- `Illuminate\Contracts\Broadcasting`
- `Illuminate\Contracts\Bus`
- `Illuminate\Contracts\Cache`
- `Illuminate\Contracts\Concurrency`
- `Illuminate\Contracts\Config`
- `Illuminate\Contracts\Console`
- `Illuminate\Contracts\Container`
- `Illuminate\Contracts\Cookie`
- `Illuminate\Contracts\Database`
- `Illuminate\Contracts\Database\Eloquent`
- `Illuminate\Contracts\Database\Events`
- `Illuminate\Contracts\Database\Query`
- `Illuminate\Contracts\Debug`
- `Illuminate\Contracts\Encryption`
- `Illuminate\Contracts\Events`
- `Illuminate\Contracts\Filesystem`
- `Illuminate\Contracts\Foundation`
- `Illuminate\Contracts\Hashing`
- `Illuminate\Contracts\Http`
- `Illuminate\Contracts\Image`
- `Illuminate\Contracts\JsonSchema`
- `Illuminate\Contracts\Log`
- `Illuminate\Contracts\Mail`
- `Illuminate\Contracts\Notifications`
- `Illuminate\Contracts\Pagination`
- `Illuminate\Contracts\Pipeline`
- `Illuminate\Contracts\Process`
- `Illuminate\Contracts\Queue`
- `Illuminate\Contracts\Redis`
- `Illuminate\Contracts\Routing`
- `Illuminate\Contracts\Session`
- `Illuminate\Contracts\Session\Middleware`
- `Illuminate\Contracts\Support`
- `Illuminate\Contracts\Translation`
- `Illuminate\Contracts\Validation`
- `Illuminate\Contracts\View`

## Status definitions

- **Exact behavioural compatibility:** verified equivalent behavior for directly representable inputs.
- **Python-adapted compatibility:** behavior is verified with a deliberate Python typing or naming adaptation.
- **Verified implementation:** a native contract/implementation pair has behavioral evidence but is not counted as Laravel parity.
- **Contract defined, implementation pending:** Titanspan owns a typed contract, but no production implementation currently satisfies it.
- **Blocked:** requires an unavailable owning component.
- **Not applicable:** the upstream concept has no meaningful Python equivalent.
- **Pending:** not implemented or not yet verified; no compatibility claim is made.

### `Illuminate\Contracts\Auth\Authenticatable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getAuthIdentifierName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>getAuthIdentifier() -&gt; mixed</code> | Parameters: none. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>getAuthPasswordName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>getAuthPassword() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>getRememberToken() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>setRememberToken($value) -&gt; void</code> | Parameters: <code>$value</code>: <code>string&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |
| <code>getRememberTokenName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Authenticatable.php) |

### `Illuminate\Contracts\Auth\CanResetPassword`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/CanResetPassword.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getEmailForPasswordReset() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/CanResetPassword.php) |
| <code>sendPasswordResetNotification($token) -&gt; void</code> | Parameters: <code>$token</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/CanResetPassword.php) |

### `Illuminate\Contracts\Auth\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>guard($name = null) -&gt; \Illuminate\Contracts\Auth\Guard&#124;\Illuminate\Contracts\Auth\StatefulGuard</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Auth\Guard&#124;\Illuminate\Contracts\Auth\StatefulGuard</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Factory.php) |
| <code>shouldUse($name) -&gt; void</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Factory.php) |

### `Illuminate\Contracts\Auth\Guard`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>check() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>guest() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>user() -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;null</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>id() -&gt; int&#124;string&#124;null</code> | Parameters: none. Return contract: <code>int&#124;string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>validate(array $credentials = []) -&gt; bool</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>hasUser() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |
| <code>setUser(Authenticatable $user) -&gt; $this</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Guard.php) |

### `Illuminate\Contracts\Auth\MustVerifyEmail`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>hasVerifiedEmail() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php) |
| <code>markEmailAsVerified() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php) |
| <code>markEmailAsUnverified() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php) |
| <code>sendEmailVerificationNotification() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php) |
| <code>getEmailForVerification() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/MustVerifyEmail.php) |

### `Illuminate\Contracts\Auth\PasswordBroker`

- Parents: `none`.
- Constants: `RESET_LINK_SENT = 'passwords.sent'`, `PASSWORD_RESET = 'passwords.reset'`, `INVALID_USER = 'passwords.user'`, `INVALID_TOKEN = 'passwords.token'`, `RESET_THROTTLED = 'passwords.throttled'` <!-- pragma: allowlist secret: public upstream status constants -->
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/PasswordBroker.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>sendResetLink(array $credentials, ?Closure $callback = null) -&gt; string</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/PasswordBroker.php) |
| <code>reset(array $credentials, Closure $callback) -&gt; mixed</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/PasswordBroker.php) |

### `Illuminate\Contracts\Auth\PasswordBrokerFactory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/PasswordBrokerFactory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>broker($name = null) -&gt; \Illuminate\Contracts\Auth\PasswordBroker</code> | Parameters: <code>$name</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Auth\PasswordBroker</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/PasswordBrokerFactory.php) |

### `Illuminate\Contracts\Auth\StatefulGuard`

- Parents: `extends Guard`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>attempt(array $credentials = [], $remember = false) -&gt; bool</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>once(array $credentials = []) -&gt; bool</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>login(Authenticatable $user, $remember = false) -&gt; void</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>loginUsingId($id, $remember = false) -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;false</code> | Parameters: <code>$id</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;false</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>onceUsingId($id) -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;false</code> | Parameters: <code>$id</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;false</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>viaRemember() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |
| <code>logout() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/StatefulGuard.php) |

### `Illuminate\Contracts\Auth\SupportsBasicAuth`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/SupportsBasicAuth.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>basic($field = &#x27;email&#x27;, $extraConditions = []) -&gt; \Symfony\Component\HttpFoundation\Response&#124;null</code> | Parameters: <code>$field</code>: <code>string</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Response&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/SupportsBasicAuth.php) |
| <code>onceBasic($field = &#x27;email&#x27;, $extraConditions = []) -&gt; \Symfony\Component\HttpFoundation\Response&#124;null</code> | Parameters: <code>$field</code>: <code>string</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Response&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/SupportsBasicAuth.php) |

### `Illuminate\Contracts\Auth\UserProvider`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>retrieveById($identifier) -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;null</code> | Parameters: <code>$identifier</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |
| <code>retrieveByToken($identifier, #[\SensitiveParameter] $token) -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;null</code> | Parameters: <code>$identifier</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |
| <code>updateRememberToken(Authenticatable $user, #[\SensitiveParameter] $token) -&gt; void</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |
| <code>retrieveByCredentials(#[\SensitiveParameter] array $credentials) -&gt; \Illuminate\Contracts\Auth\Authenticatable&#124;null</code> | Parameters: <code>$credentials</code>: <code>array</code>. Return contract: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |
| <code>validateCredentials(Authenticatable $user, #[\SensitiveParameter] array $credentials) -&gt; bool</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |
| <code>rehashPasswordIfRequired(Authenticatable $user, #[\SensitiveParameter] array $credentials, bool $force = false) -&gt; void</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable</code>; <code>$force</code>: <code>bool</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.auth; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/UserProvider.php) |

### `Illuminate\Contracts\Auth\Access\Authorizable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Authorizable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>can($abilities, $arguments = []) -&gt; bool</code> | Parameters: <code>$abilities</code>: <code>\UnitEnum&#124;iterable&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Authorizable.php) |

### `Illuminate\Contracts\Auth\Access\Gate`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>has($ability) -&gt; bool</code> | Parameters: <code>$ability</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>define($ability, $callback) -&gt; $this</code> | Parameters: <code>$ability</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>resource($name, $class, ?array $abilities = null) -&gt; $this</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$abilities</code>: <code>array&#124;null</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>policy($class, $policy) -&gt; $this</code> | Parameters: <code>$class</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>before(callable $callback) -&gt; $this</code> | Parameters: <code>$callback</code>: <code>callable</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>after(callable $callback) -&gt; $this</code> | Parameters: <code>$callback</code>: <code>callable</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>allows($ability, $arguments = []) -&gt; bool</code> | Parameters: <code>$ability</code>: <code>iterable&#124;\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>denies($ability, $arguments = []) -&gt; bool</code> | Parameters: <code>$ability</code>: <code>iterable&#124;\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>check($abilities, $arguments = []) -&gt; bool</code> | Parameters: <code>$abilities</code>: <code>iterable&#124;\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>any($abilities, $arguments = []) -&gt; bool</code> | Parameters: <code>$abilities</code>: <code>iterable&#124;\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>authorize($ability, $arguments = []) -&gt; \Illuminate\Auth\Access\Response</code> | Parameters: <code>$ability</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>\Illuminate\Auth\Access\Response</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>inspect($ability, $arguments = []) -&gt; \Illuminate\Auth\Access\Response</code> | Parameters: <code>$ability</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>\Illuminate\Auth\Access\Response</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>raw($ability, $arguments = []) -&gt; mixed</code> | Parameters: <code>$ability</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>getPolicyFor($class) -&gt; mixed</code> | Parameters: <code>$class</code>: <code>object&#124;string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>forUser($user) -&gt; static</code> | Parameters: <code>$user</code>: <code>\Illuminate\Contracts\Auth\Authenticatable&#124;mixed</code>. Return contract: <code>static</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |
| <code>abilities() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Access/Gate.php) |

### `Illuminate\Contracts\Auth\Middleware\AuthenticatesRequests`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Middleware/AuthenticatesRequests.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Auth\Middleware\AuthenticatesRequests</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Auth/Middleware/AuthenticatesRequests.php) |

### `Illuminate\Contracts\Broadcasting\Broadcaster`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Broadcaster.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>auth($request) -&gt; mixed</code> | Parameters: <code>$request</code>: <code>\Illuminate\Http\Request</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Broadcaster.php) |
| <code>validAuthenticationResponse($request, $result) -&gt; mixed</code> | Parameters: <code>$request</code>: <code>\Illuminate\Http\Request</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Broadcaster.php) |
| <code>broadcast(array $channels, $event, array $payload = []) -&gt; void</code> | Parameters: <code>$channels</code>: <code>array</code>; <code>$payload</code>: <code>array</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Broadcaster.php) |

### `Illuminate\Contracts\Broadcasting\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>connection($name = null) -&gt; \Illuminate\Contracts\Broadcasting\Broadcaster</code> | Parameters: <code>$name</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Broadcasting\Broadcaster</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/Factory.php) |

### `Illuminate\Contracts\Broadcasting\HasBroadcastChannel`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/HasBroadcastChannel.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>broadcastChannelRoute() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/HasBroadcastChannel.php) |
| <code>broadcastChannel() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/HasBroadcastChannel.php) |

### `Illuminate\Contracts\Broadcasting\ShouldBeUnique`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBeUnique.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Broadcasting\ShouldBeUnique</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker declaration; uniqueness lifecycle and storage semantics belong to a future queue contract. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBeUnique.php) |

### `Illuminate\Contracts\Broadcasting\ShouldBroadcast`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBroadcast.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>broadcastOn() -&gt; \Illuminate\Broadcasting\Channel&#124;\Illuminate\Broadcasting\Channel[]&#124;string[]&#124;string</code> | Parameters: none. Return contract: <code>\Illuminate\Broadcasting\Channel&#124;\Illuminate\Broadcasting\Channel[]&#124;string[]&#124;string</code>. | <code>—</code> | **Blocked** | Requires broadcasting integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBroadcast.php) |

### `Illuminate\Contracts\Broadcasting\ShouldBroadcastNow`

- Parents: `extends ShouldBroadcast`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBroadcastNow.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Broadcasting\ShouldBroadcastNow</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker or dispatch declaration; broadcast execution semantics are pending the broadcasting integration. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldBroadcastNow.php) |

### `Illuminate\Contracts\Broadcasting\ShouldRescue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldRescue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Broadcasting\ShouldRescue</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker or dispatch declaration; broadcast execution semantics are pending the broadcasting integration. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Broadcasting/ShouldRescue.php) |

### `Illuminate\Contracts\Bus\Dispatcher`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>dispatch($command) -&gt; mixed</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>dispatchSync($command, $handler = null) -&gt; mixed</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>dispatchNow($command, $handler = null) -&gt; mixed</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>dispatchAfterResponse($command, $handler = null) -&gt; void</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>chain($jobs = null) -&gt; mixed</code> | Parameters: <code>$jobs</code>: <code>\Illuminate\Support\Collection&#124;array&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>hasCommandHandler($command) -&gt; bool</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>getCommandHandler($command) -&gt; mixed</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>pipeThrough(array $pipes) -&gt; $this</code> | Parameters: <code>$pipes</code>: <code>array</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |
| <code>map(array $map) -&gt; $this</code> | Parameters: <code>$map</code>: <code>array</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/Dispatcher.php) |

### `Illuminate\Contracts\Bus\QueueingDispatcher`

- Parents: `extends Dispatcher`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/QueueingDispatcher.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>findBatch(string $batchId) -&gt; \Illuminate\Bus\Batch&#124;null</code> | Parameters: <code>$batchId</code>: <code>string</code>. Return contract: <code>\Illuminate\Bus\Batch&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/QueueingDispatcher.php) |
| <code>batch($jobs) -&gt; \Illuminate\Bus\PendingBatch</code> | Parameters: <code>$jobs</code>: <code>\Illuminate\Support\Collection&#124;array</code>. Return contract: <code>\Illuminate\Bus\PendingBatch</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/QueueingDispatcher.php) |
| <code>dispatchToQueue($command) -&gt; mixed</code> | Parameters: <code>$command</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Bus/QueueingDispatcher.php) |

### `Illuminate\Contracts\Cache\CanFlushLocks`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/CanFlushLocks.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>flushLocks() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/CanFlushLocks.php) |
| <code>hasSeparateLockStore() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/CanFlushLocks.php) |

### `Illuminate\Contracts\Cache\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>store($name = null) -&gt; \Illuminate\Contracts\Cache\Repository</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Cache\Repository</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Factory.php) |

### `Illuminate\Contracts\Cache\Lock`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get($callback = null) -&gt; mixed</code> | Parameters: <code>$callback</code>: <code>callable&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php) |
| <code>block($seconds, $callback = null) -&gt; mixed</code> | Parameters: <code>$seconds</code>: <code>int</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php) |
| <code>release() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php) |
| <code>owner() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php) |
| <code>forceRelease() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Lock.php) |

### `Illuminate\Contracts\Cache\LockProvider`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/LockProvider.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>lock($name, $seconds = 0, $owner = null) -&gt; \Illuminate\Contracts\Cache\Lock</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$owner</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Cache\Lock</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/LockProvider.php) |
| <code>restoreLock($name, $owner) -&gt; \Illuminate\Contracts\Cache\Lock</code> | Parameters: <code>$name</code>: <code>string</code>. Return contract: <code>\Illuminate\Contracts\Cache\Lock</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/LockProvider.php) |

### `Illuminate\Contracts\Cache\Repository`

- Parents: `extends CacheInterface`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>pull($key, $default = null) -&gt; (TCacheValue is null ? mixed : TCacheValue)</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;array&#124;string</code>. Return contract: <code>(TCacheValue is null ? mixed : TCacheValue)</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>put($key, $value, $ttl = null) -&gt; bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>; <code>$ttl</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int&#124;null</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>add($key, $value, $ttl = null) -&gt; bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>; <code>$ttl</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int&#124;null</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>increment($key, $value = 1) -&gt; int&#124;bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>int&#124;bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>decrement($key, $value = 1) -&gt; int&#124;bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>int&#124;bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>forever($key, $value) -&gt; bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>remember($key, $ttl, Closure $callback) -&gt; TCacheValue</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>; <code>$callback</code>: <code>\Closure(): TCacheValue</code>. Return contract: <code>TCacheValue</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>sear($key, Closure $callback) -&gt; TCacheValue</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>TCacheValue</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>rememberForever($key, Closure $callback) -&gt; TCacheValue</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>TCacheValue</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>touch($key, $ttl) -&gt; bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>forget($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>\UnitEnum&#124;string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |
| <code>getStore() -&gt; \Illuminate\Contracts\Cache\Store</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Cache\Store</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Repository.php) |

### `Illuminate\Contracts\Cache\Store`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get($key) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>many(array $keys) -&gt; array</code> | Parameters: <code>$keys</code>: <code>array</code>. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>put($key, $value, $seconds) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string</code>; <code>$seconds</code>: <code>int</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>putMany(array $values, $seconds) -&gt; bool</code> | Parameters: <code>$values</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>increment($key, $value = 1) -&gt; int&#124;bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>int&#124;bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>decrement($key, $value = 1) -&gt; int&#124;bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>int&#124;bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>forever($key, $value) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>touch($key, $seconds) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>forget($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>flush() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |
| <code>getPrefix() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.cache; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/Store.php) |

### `Illuminate\Contracts\Concurrency\Driver`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Concurrency/Driver.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>run(Closure&#124;array $tasks, CarbonInterval&#124;int&#124;null $timeout = null) -&gt; array</code> | Parameters: none. Return contract: <code>not declared</code>. | <code>—</code> | **Blocked** | Requires titanspan.concurrency; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Concurrency/Driver.php) |
| <code>defer(Closure&#124;array $tasks) -&gt; DeferredCallback</code> | Parameters: none. Return contract: <code>not declared</code>. | <code>—</code> | **Blocked** | Requires titanspan.concurrency; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Concurrency/Driver.php) |

### `Illuminate\Contracts\Config\Repository`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>has($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>titanspan.contracts.config_repository.has</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |
| <code>get($key, $default = null) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>array&#124;string</code>. Return contract: <code>mixed</code>. | <code>titanspan.contracts.config_repository.get</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |
| <code>all() -&gt; array&lt;string, mixed&gt;</code> | Parameters: none. Return contract: <code>array&lt;string, mixed&gt;</code>. | <code>titanspan.contracts.config_repository.all</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |
| <code>set($key, $value = null) -&gt; void</code> | Parameters: <code>$key</code>: <code>array&#124;string</code>. Return contract: <code>void</code>. | <code>titanspan.contracts.config_repository.set</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |
| <code>prepend($key, $value) -&gt; void</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>void</code>. | <code>titanspan.contracts.config_repository.prepend</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |
| <code>push($key, $value) -&gt; void</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>void</code>. | <code>titanspan.contracts.config_repository.push</code> | **Verified implementation** | Native Repository conforms to the protocol and is behavior-tested. Test evidence: tests/unit/contracts/test_contracts.py and tests/unit/config/test_repository.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php) |

### `Illuminate\Contracts\Console\Application`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Application.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>call($command, array $parameters = [], $outputBuffer = null) -&gt; int</code> | Parameters: <code>$command</code>: <code>string</code>; <code>$outputBuffer</code>: <code>\Symfony\Component\Console\Output\OutputInterface&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Application.php) |
| <code>output() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Application.php) |

### `Illuminate\Contracts\Console\Isolatable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Isolatable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Console\Isolatable</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Isolatable.php) |

### `Illuminate\Contracts\Console\Kernel`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>bootstrap() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>handle($input, $output = null) -&gt; int</code> | Parameters: <code>$input</code>: <code>\Symfony\Component\Console\Input\InputInterface</code>. Return contract: <code>int</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>call($command, array $parameters = [], $outputBuffer = null) -&gt; int</code> | Parameters: <code>$command</code>: <code>string</code>; <code>$outputBuffer</code>: <code>\Symfony\Component\Console\Output\OutputInterface&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>queue($command, array $parameters = []) -&gt; \Illuminate\Foundation\Bus\PendingDispatch</code> | Parameters: <code>$command</code>: <code>string</code>. Return contract: <code>\Illuminate\Foundation\Bus\PendingDispatch</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>all() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>output() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |
| <code>terminate($input, $status) -&gt; void</code> | Parameters: <code>$input</code>: <code>\Symfony\Component\Console\Input\InputInterface</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.console. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/Kernel.php) |

### `Illuminate\Contracts\Console\PromptsForMissingInput`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/PromptsForMissingInput.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Console\PromptsForMissingInput</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Console/PromptsForMissingInput.php) |

### `Illuminate\Contracts\Container\Container`

- Parents: `extends ContainerInterface`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get(string $id) -&gt; ($id is class-string&lt;TClass&gt; ? TClass : mixed)</code> | Parameters: <code>$id</code>: <code>string&#124;class-string&lt;TClass&gt;</code>. Return contract: <code>($id is class-key typed and offers explicit sync/async variants)</code> | <code>ServiceContainer.get</code> / <code>get_async</code> | **Python-adapted compatibility** | The concrete container also supports string aliases. Test evidence: tests/unit/container/test_execution_modes.py and tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>bound($abstract) -&gt; bool</code> | Parameters: <code>$abstract</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>alias($abstract, $alias) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>tag($abstracts, $tags) -&gt; void</code> | Parameters: <code>$abstracts</code>: <code>array&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>tagged($tag) -&gt; iterable</code> | Parameters: <code>$tag</code>: <code>string</code>. Return contract: <code>iterable</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>bind($abstract, $concrete = null, $shared = false) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>; <code>$shared</code>: <code>bool</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>bindMethod($method, $callback) -&gt; void</code> | Parameters: <code>$method</code>: <code>array&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>bindIf($abstract, $concrete = null, $shared = false) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>; <code>$shared</code>: <code>bool</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>singleton($abstract, $concrete = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>singletonIf($abstract, $concrete = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>scoped($abstract, $concrete = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>scopedIf($abstract, $concrete = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>extend($abstract, Closure $closure) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>instance($abstract, $instance) -&gt; TInstance</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>TInstance</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>addContextualBinding($concrete, $abstract, $implementation) -&gt; void</code> | Parameters: <code>$concrete</code>: <code>string</code>; <code>$implementation</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>when($concrete) -&gt; \Illuminate\Contracts\Container\ContextualBindingBuilder</code> | Parameters: <code>$concrete</code>: <code>string&#124;array</code>. Return contract: <code>\Illuminate\Contracts\Container\ContextualBindingBuilder</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>factory($abstract) -&gt; ($abstract is class-string&lt;TClass&gt; ? \Closure(): TClass : \Closure(): mixed)</code> | Parameters: <code>$abstract</code>: <code>string&#124;class-string&lt;TClass&gt;</code>. Return contract: <code>($abstract is class-string&lt;TClass&gt; ? \Closure(): TClass : \Closure(): mixed)</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>flush() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>make($abstract, array $parameters = []) -&gt; ($abstract is class-string&lt;TClass&gt; ? TClass : mixed)</code> | Parameters: <code>$abstract</code>: <code>string&#124;class-string&lt;TClass&gt;</code>. Return contract: <code>($abstract is class-string&lt;TClass&gt; ? TClass : mixed)</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>call($callback, array $parameters = [], $defaultMethod = null) -&gt; mixed</code> | Parameters: <code>$callback</code>: <code>callable&#124;string</code>; <code>$defaultMethod</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>resolved($abstract) -&gt; bool</code> | Parameters: <code>$abstract</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>beforeResolving($abstract, ?Closure $callback = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>resolving($abstract, ?Closure $callback = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |
| <code>afterResolving($abstract, ?Closure $callback = null) -&gt; void</code> | Parameters: <code>$abstract</code>: <code>\Closure&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/Container.php) |

### `Illuminate\Contracts\Container\ContextualAttribute`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualAttribute.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Container\ContextualAttribute</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualAttribute.php) |

### `Illuminate\Contracts\Container\ContextualBindingBuilder`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualBindingBuilder.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>needs($abstract) -&gt; $this</code> | Parameters: <code>$abstract</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualBindingBuilder.php) |
| <code>give($implementation) -&gt; $this</code> | Parameters: <code>$implementation</code>: <code>\Closure&#124;string&#124;array</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualBindingBuilder.php) |
| <code>giveTagged($tag) -&gt; $this</code> | Parameters: <code>$tag</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualBindingBuilder.php) |
| <code>giveConfig($key, $default = null) -&gt; $this</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.container. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/ContextualBindingBuilder.php) |

### `Illuminate\Contracts\Container\SelfBuilding`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/SelfBuilding.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Container\SelfBuilding</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/SelfBuilding.php) |

### `Illuminate\Contracts\Cookie\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>make($name, $value, $minutes = 0, $path = null, $domain = null, $secure = null, $httpOnly = true, $raw = false, $sameSite = null) -&gt; \Symfony\Component\HttpFoundation\Cookie</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$minutes</code>: <code>int</code>; <code>$domain</code>: <code>string&#124;null</code>; <code>$httpOnly</code>: <code>bool</code>; <code>$sameSite</code>: <code>string&#124;null</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Cookie</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/Factory.php) |
| <code>forever($name, $value, $path = null, $domain = null, $secure = null, $httpOnly = true, $raw = false, $sameSite = null) -&gt; \Symfony\Component\HttpFoundation\Cookie</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$path</code>: <code>string&#124;null</code>; <code>$secure</code>: <code>bool&#124;null</code>; <code>$raw</code>: <code>bool</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Cookie</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/Factory.php) |
| <code>forget($name, $path = null, $domain = null) -&gt; \Symfony\Component\HttpFoundation\Cookie</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$domain</code>: <code>string&#124;null</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Cookie</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/Factory.php) |

### `Illuminate\Contracts\Cookie\QueueingFactory`

- Parents: `extends Factory`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/QueueingFactory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>queue(...$parameters) -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/QueueingFactory.php) |
| <code>unqueue($name, $path = null) -&gt; void</code> | Parameters: <code>$name</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/QueueingFactory.php) |
| <code>getQueuedCookies() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cookie/QueueingFactory.php) |

### `Illuminate\Contracts\Database\ConcurrencyErrorDetector`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/ConcurrencyErrorDetector.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>causedByConcurrencyError(Throwable $e) -&gt; bool</code> | Parameters: <code>$e</code>: <code>\Throwable</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.database; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/ConcurrencyErrorDetector.php) |

### `Illuminate\Contracts\Database\LostConnectionDetector`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/LostConnectionDetector.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>causedByLostConnection(Throwable $e) -&gt; bool</code> | Parameters: <code>$e</code>: <code>\Throwable</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.database; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/LostConnectionDetector.php) |

### `Illuminate\Contracts\Database\Eloquent\Builder`

- Parents: `extends BaseContract`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/Builder.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Database\Eloquent\Builder</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/Builder.php) |

### `Illuminate\Contracts\Database\Eloquent\Castable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/Castable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>static castUsing(array $arguments) -&gt; class-string&lt;CastsAttributes&#124;CastsInboundAttributes&gt;&#124;CastsAttributes&#124;CastsInboundAttributes</code> | Parameters: <code>$arguments</code>: <code>string[]</code>. Return contract: <code>class-string&lt;CastsAttributes&#124;CastsInboundAttributes&gt;&#124;CastsAttributes&#124;CastsInboundAttributes</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/Castable.php) |

### `Illuminate\Contracts\Database\Eloquent\CastsAttributes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/CastsAttributes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get(Model $model, string $key, mixed $value, array $attributes) -&gt; TGet&#124;null</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>mixed</code>. Return contract: <code>TGet&#124;null</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/CastsAttributes.php) |
| <code>set(Model $model, string $key, mixed $value, array $attributes) -&gt; mixed</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>TSet&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/CastsAttributes.php) |

### `Illuminate\Contracts\Database\Eloquent\CastsInboundAttributes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/CastsInboundAttributes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>set(Model $model, string $key, mixed $value, array $attributes) -&gt; mixed</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/CastsInboundAttributes.php) |

### `Illuminate\Contracts\Database\Eloquent\ComparesCastableAttributes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/ComparesCastableAttributes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>compare(Model $model, string $key, mixed $firstValue, mixed $secondValue) -&gt; bool</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$firstValue</code>: <code>mixed</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/ComparesCastableAttributes.php) |

### `Illuminate\Contracts\Database\Eloquent\DeviatesCastableAttributes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/DeviatesCastableAttributes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>increment($model, string $key, $value, array $attributes) -&gt; mixed</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/DeviatesCastableAttributes.php) |
| <code>decrement($model, string $key, $value, array $attributes) -&gt; mixed</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/DeviatesCastableAttributes.php) |

### `Illuminate\Contracts\Database\Eloquent\SerializesCastableAttributes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SerializesCastableAttributes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>serialize(Model $model, string $key, mixed $value, array $attributes) -&gt; mixed</code> | Parameters: <code>$model</code>: <code>\Illuminate\Database\Eloquent\Model</code>; <code>$value</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SerializesCastableAttributes.php) |

### `Illuminate\Contracts\Database\Eloquent\SupportsPartialRelations`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SupportsPartialRelations.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>ofMany($column = &#x27;id&#x27;, $aggregate = &#x27;MAX&#x27;, $relation = null) -&gt; $this</code> | Parameters: <code>$column</code>: <code>string&#124;null</code>; <code>$relation</code>: <code>string&#124;null</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SupportsPartialRelations.php) |
| <code>isOneOfMany() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SupportsPartialRelations.php) |
| <code>getOneOfManySubQuery() -&gt; \Illuminate\Database\Eloquent\Builder&#124;void</code> | Parameters: none. Return contract: <code>\Illuminate\Database\Eloquent\Builder&#124;void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Eloquent/SupportsPartialRelations.php) |

### `Illuminate\Contracts\Database\Events\MigrationEvent`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Events/MigrationEvent.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Database\Events\MigrationEvent</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Events/MigrationEvent.php) |

### `Illuminate\Contracts\Database\Query\Builder`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/Builder.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Database\Query\Builder</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/Builder.php) |

### `Illuminate\Contracts\Database\Query\ConditionExpression`

- Parents: `extends Expression`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/ConditionExpression.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Database\Query\ConditionExpression</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/ConditionExpression.php) |

### `Illuminate\Contracts\Database\Query\Expression`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/Expression.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getValue(Grammar $grammar) -&gt; string&#124;int&#124;float</code> | Parameters: <code>$grammar</code>: <code>\Illuminate\Database\Grammar</code>. Return contract: <code>string&#124;int&#124;float</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/Query/Expression.php) |

### `Illuminate\Contracts\Debug\ExceptionHandler`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ExceptionHandler.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>report(Throwable $e) -&gt; void</code> | Parameters: <code>$e</code>: <code>\Throwable</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires foundation exception handling (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ExceptionHandler.php) |
| <code>shouldReport(Throwable $e) -&gt; bool</code> | Parameters: <code>$e</code>: <code>\Throwable</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires foundation exception handling (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ExceptionHandler.php) |
| <code>render($request, Throwable $e) -&gt; \Symfony\Component\HttpFoundation\Response</code> | Parameters: <code>$request</code>: <code>\Illuminate\Http\Request</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Response</code>. | <code>—</code> | **Blocked** | Requires foundation exception handling (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ExceptionHandler.php) |
| <code>renderForConsole($output, Throwable $e) -&gt; void</code> | Parameters: <code>$output</code>: <code>\Symfony\Component\Console\Output\OutputInterface</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires foundation exception handling (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ExceptionHandler.php) |

### `Illuminate\Contracts\Debug\ShouldntReport`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ShouldntReport.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Debug\ShouldntReport</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Debug/ShouldntReport.php) |

### `Illuminate\Contracts\Encryption\Encrypter`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>encrypt(#[\SensitiveParameter] $value, $serialize = true) -&gt; string</code> | Parameters: <code>$value</code>: <code>mixed</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php) |
| <code>decrypt($payload, $unserialize = true) -&gt; mixed</code> | Parameters: <code>$payload</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php) |
| <code>getKey() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php) |
| <code>getAllKeys() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php) |
| <code>getPreviousKeys() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/Encrypter.php) |

### `Illuminate\Contracts\Encryption\StringEncrypter`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/StringEncrypter.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>encryptString(#[\SensitiveParameter] $value) -&gt; string</code> | Parameters: <code>$value</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/StringEncrypter.php) |
| <code>decryptString($payload) -&gt; string</code> | Parameters: <code>$payload</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/StringEncrypter.php) |

### `Illuminate\Contracts\Events\Dispatcher`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>listen($events, $listener = null) -&gt; void</code> | Parameters: <code>$events</code>: <code>\Closure&#124;string&#124;array</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>hasListeners($eventName) -&gt; bool</code> | Parameters: <code>$eventName</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>subscribe($subscriber) -&gt; void</code> | Parameters: <code>$subscriber</code>: <code>object&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>until($event, $payload = []) -&gt; mixed</code> | Parameters: <code>$event</code>: <code>string&#124;object</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>dispatch($event, $payload = [], $halt = false) -&gt; array&#124;null</code> | Parameters: <code>$event</code>: <code>string&#124;object</code>; <code>$halt</code>: <code>bool</code>. Return contract: <code>array&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>push($event, $payload = []) -&gt; void</code> | Parameters: <code>$event</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>flush($event) -&gt; void</code> | Parameters: <code>$event</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>forget($event) -&gt; void</code> | Parameters: <code>$event</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |
| <code>forgetPushed() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/Dispatcher.php) |

### `Illuminate\Contracts\Events\ShouldBeDiscovered`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldBeDiscovered.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>static shouldBeDiscovered() -&gt; bool</code> | Parameters: none. Return contract: <code>not declared</code>. | <code>—</code> | **Blocked** | Requires titanspan.events; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldBeDiscovered.php) |

### `Illuminate\Contracts\Events\ShouldDispatchAfterCommit`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldDispatchAfterCommit.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Events\ShouldDispatchAfterCommit</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldDispatchAfterCommit.php) |

### `Illuminate\Contracts\Events\ShouldHandleEventsAfterCommit`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldHandleEventsAfterCommit.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Events\ShouldHandleEventsAfterCommit</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Events/ShouldHandleEventsAfterCommit.php) |

### `Illuminate\Contracts\Filesystem\Cloud`

- Parents: `extends Filesystem`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Cloud.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>url($path) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Cloud.php) |

### `Illuminate\Contracts\Filesystem\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>disk($name = null) -&gt; \Illuminate\Contracts\Filesystem\Filesystem</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Filesystem\Filesystem</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Factory.php) |

### `Illuminate\Contracts\Filesystem\Filesystem`

- Parents: `none`.
- Constants: `VISIBILITY_PUBLIC = 'public'`, `VISIBILITY_PRIVATE = 'private'`
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>path($path) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>exists($path) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>get($path) -&gt; string&#124;null</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>readStream($path) -&gt; resource&#124;null The path resource or null on failure.</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>resource&#124;null The path resource or null on failure.</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>put($path, $contents, $options = []) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$options</code>: <code>mixed</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>putFile($path, $file = null, $options = []) -&gt; string&#124;false</code> | Parameters: <code>$path</code>: <code>\Illuminate\Http\File&#124;\Illuminate\Http\UploadedFile&#124;string</code>; <code>$options</code>: <code>mixed</code>. Return contract: <code>string&#124;false</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>putFileAs($path, $file, $name = null, $options = []) -&gt; string&#124;false</code> | Parameters: <code>$path</code>: <code>\Illuminate\Http\File&#124;\Illuminate\Http\UploadedFile&#124;string</code>; <code>$name</code>: <code>string&#124;array&#124;null</code>. Return contract: <code>string&#124;false</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>writeStream($path, $resource, array $options = []) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$options</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>getVisibility($path) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>setVisibility($path, $visibility) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>prepend($path, $data) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>append($path, $data) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>delete($paths) -&gt; bool</code> | Parameters: <code>$paths</code>: <code>string&#124;array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>copy($from, $to) -&gt; bool</code> | Parameters: <code>$from</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>move($from, $to) -&gt; bool</code> | Parameters: <code>$from</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>size($path) -&gt; int</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>lastModified($path) -&gt; int</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>files($directory = null, $recursive = false) -&gt; array&lt;string&gt;</code> | Parameters: <code>$directory</code>: <code>string&#124;null</code>. Return contract: <code>array&lt;string&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>allFiles($directory = null) -&gt; array&lt;string&gt;</code> | Parameters: <code>$directory</code>: <code>string&#124;null</code>. Return contract: <code>array&lt;string&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>directories($directory = null, $recursive = false) -&gt; array&lt;string&gt;</code> | Parameters: <code>$directory</code>: <code>string&#124;null</code>. Return contract: <code>array&lt;string&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>allDirectories($directory = null) -&gt; array&lt;string&gt;</code> | Parameters: <code>$directory</code>: <code>string&#124;null</code>. Return contract: <code>array&lt;string&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>makeDirectory($path) -&gt; bool</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |
| <code>deleteDirectory($directory) -&gt; bool</code> | Parameters: <code>$directory</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.filesystem; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/Filesystem.php) |

### `Illuminate\Contracts\Foundation\Application`

- Parents: `extends Container`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>version() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>basePath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>bootstrapPath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>configPath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>databasePath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>langPath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>publicPath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>resourcePath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>storagePath($path = &#x27;&#x27;) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>environment(...$environments) -&gt; string&#124;bool</code> | Parameters: none. Return contract: <code>string&#124;bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>runningInConsole() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>runningUnitTests() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>hasDebugModeEnabled() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>maintenanceMode() -&gt; \Illuminate\Contracts\Foundation\MaintenanceMode</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Foundation\MaintenanceMode</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>isDownForMaintenance() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>registerConfiguredProviders() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>register($provider, $force = false) -&gt; \Illuminate\Support\ServiceProvider</code> | Parameters: <code>$provider</code>: <code>\Illuminate\Support\ServiceProvider&#124;string</code>. Return contract: <code>\Illuminate\Support\ServiceProvider</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>registerDeferredProvider($provider, $service = null) -&gt; void</code> | Parameters: <code>$provider</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>resolveProvider($provider) -&gt; \Illuminate\Support\ServiceProvider</code> | Parameters: <code>$provider</code>: <code>string</code>. Return contract: <code>\Illuminate\Support\ServiceProvider</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>boot() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>booting($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>callable</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>booted($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>callable</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>bootstrapWith(array $bootstrappers) -&gt; void</code> | Parameters: <code>$bootstrappers</code>: <code>array</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>getLocale() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>getNamespace() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>getProviders($provider) -&gt; array</code> | Parameters: <code>$provider</code>: <code>\Illuminate\Support\ServiceProvider&#124;string</code>. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>hasBeenBootstrapped() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>loadDeferredProviders() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>setLocale($locale) -&gt; void</code> | Parameters: <code>$locale</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>shouldSkipMiddleware() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>terminating($callback) -&gt; \Illuminate\Contracts\Foundation\Application</code> | Parameters: <code>$callback</code>: <code>callable&#124;string</code>. Return contract: <code>\Illuminate\Contracts\Foundation\Application</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |
| <code>terminate() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/Application.php) |

### `Illuminate\Contracts\Foundation\CachesConfiguration`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesConfiguration.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>configurationIsCached() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesConfiguration.php) |
| <code>getCachedConfigPath() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesConfiguration.php) |
| <code>getCachedServicesPath() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesConfiguration.php) |

### `Illuminate\Contracts\Foundation\CachesRoutes`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesRoutes.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>routesAreCached() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesRoutes.php) |
| <code>getCachedRoutesPath() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/CachesRoutes.php) |

### `Illuminate\Contracts\Foundation\ExceptionRenderer`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/ExceptionRenderer.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>render($throwable) -&gt; string</code> | Parameters: <code>$throwable</code>: <code>\Throwable</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/ExceptionRenderer.php) |

### `Illuminate\Contracts\Foundation\MaintenanceMode`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/MaintenanceMode.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>activate(array $payload) -&gt; void</code> | Parameters: <code>$payload</code>: <code>array</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/MaintenanceMode.php) |
| <code>deactivate() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/MaintenanceMode.php) |
| <code>active() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/MaintenanceMode.php) |
| <code>data() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.foundation. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Foundation/MaintenanceMode.php) |

### `Illuminate\Contracts\Hashing\Hasher`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Hashing/Hasher.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>info($hashedValue) -&gt; array</code> | Parameters: <code>$hashedValue</code>: <code>string</code>. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Hashing/Hasher.php) |
| <code>make(#[\SensitiveParameter] $value, array $options = []) -&gt; string</code> | Parameters: <code>$value</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Hashing/Hasher.php) |
| <code>check(#[\SensitiveParameter] $value, $hashedValue, array $options = []) -&gt; bool</code> | Parameters: <code>$value</code>: <code>string</code>; <code>$options</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Hashing/Hasher.php) |
| <code>needsRehash($hashedValue, array $options = []) -&gt; bool</code> | Parameters: <code>$hashedValue</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Hashing/Hasher.php) |

### `Illuminate\Contracts\Http\Kernel`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Http/Kernel.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>bootstrap() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Http/Kernel.php) |
| <code>handle($request) -&gt; \Symfony\Component\HttpFoundation\Response</code> | Parameters: <code>$request</code>: <code>\Symfony\Component\HttpFoundation\Request</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Response</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Http/Kernel.php) |
| <code>terminate($request, $response) -&gt; void</code> | Parameters: <code>$request</code>: <code>\Symfony\Component\HttpFoundation\Request</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Http/Kernel.php) |
| <code>getApplication() -&gt; \Illuminate\Contracts\Foundation\Application</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Foundation\Application</code>. | <code>—</code> | **Blocked** | Requires titanspan.http; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Http/Kernel.php) |

### `Illuminate\Contracts\Image\Driver`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Driver.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>process(string $contents, ImagePipeline $pipeline) -&gt; string</code> | Parameters: none. Return contract: <code>not declared</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Driver.php) |
| <code>dimensions(string $contents) -&gt; array</code> | Parameters: none. Return contract: <code>array{0: int, 1: int}</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Driver.php) |
| <code>dominantColor(string $contents) -&gt; string</code> | Parameters: none. Return contract: <code>not declared</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Driver.php) |
| <code>transformUsing(string $transformation, callable $callback) -&gt; static</code> | Parameters: <code>$transformation</code>: <code>class-string&lt;\Illuminate\Contracts\Image\Transformation&gt;</code>. Return contract: <code>not declared</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Driver.php) |

### `Illuminate\Contracts\Image\Transformation`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Transformation.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Image\Transformation</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Image/Transformation.php) |

### `Illuminate\Contracts\JsonSchema\JsonSchema`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>object(Closure&#124;array $properties = []) -&gt; \Illuminate\JsonSchema\Types\ObjectType</code> | Parameters: <code>$properties</code>: <code>(Closure(JsonSchema): array&lt;string, \Illuminate\JsonSchema\Types\Type&gt;)&#124;array&lt;string, \Illuminate\JsonSchema\Types\Type&gt;</code>. Return contract: <code>\Illuminate\JsonSchema\Types\ObjectType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>array() -&gt; \Illuminate\JsonSchema\Types\ArrayType</code> | Parameters: none. Return contract: <code>\Illuminate\JsonSchema\Types\ArrayType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>string() -&gt; \Illuminate\JsonSchema\Types\StringType</code> | Parameters: none. Return contract: <code>\Illuminate\JsonSchema\Types\StringType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>integer() -&gt; \Illuminate\JsonSchema\Types\IntegerType</code> | Parameters: none. Return contract: <code>\Illuminate\JsonSchema\Types\IntegerType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>number() -&gt; \Illuminate\JsonSchema\Types\NumberType</code> | Parameters: none. Return contract: <code>\Illuminate\JsonSchema\Types\NumberType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>boolean() -&gt; \Illuminate\JsonSchema\Types\BooleanType</code> | Parameters: none. Return contract: <code>\Illuminate\JsonSchema\Types\BooleanType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>union(array $types) -&gt; \Illuminate\JsonSchema\Types\UnionType</code> | Parameters: <code>$types</code>: <code>array&lt;int, string&gt;</code>. Return contract: <code>\Illuminate\JsonSchema\Types\UnionType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |
| <code>anyOf(Closure&#124;array $schemas) -&gt; \Illuminate\JsonSchema\Types\AnyOfType</code> | Parameters: <code>$schemas</code>: <code>(Closure(JsonSchema): array&lt;int, \Illuminate\JsonSchema\Types\Type&gt;)&#124;array&lt;int, \Illuminate\JsonSchema\Types\Type&gt;</code>. Return contract: <code>\Illuminate\JsonSchema\Types\AnyOfType</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/JsonSchema/JsonSchema.php) |

### `Illuminate\Contracts\Log\ContextLogProcessor`

- Parents: `extends ProcessorInterface`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Log/ContextLogProcessor.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Log\ContextLogProcessor</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Log/ContextLogProcessor.php) |

### `Illuminate\Contracts\Mail\Attachable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Attachable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toMailAttachment() -&gt; \Illuminate\Mail\Attachment</code> | Parameters: none. Return contract: <code>\Illuminate\Mail\Attachment</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Attachable.php) |

### `Illuminate\Contracts\Mail\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>mailer($name = null) -&gt; \Illuminate\Contracts\Mail\Mailer</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Mail\Mailer</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Factory.php) |

### `Illuminate\Contracts\Mail\MailQueue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/MailQueue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>queue($view, $queue = null) -&gt; mixed</code> | Parameters: <code>$view</code>: <code>\Illuminate\Contracts\Mail\Mailable&#124;string&#124;array</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/MailQueue.php) |
| <code>later($delay, $view, $queue = null) -&gt; mixed</code> | Parameters: <code>$delay</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int</code>; <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/MailQueue.php) |

### `Illuminate\Contracts\Mail\Mailable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>send($mailer) -&gt; \Illuminate\Mail\SentMessage&#124;null</code> | Parameters: <code>$mailer</code>: <code>\Illuminate\Contracts\Mail\Factory&#124;\Illuminate\Contracts\Mail\Mailer</code>. Return contract: <code>\Illuminate\Mail\SentMessage&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>queue(Queue $queue) -&gt; mixed</code> | Parameters: <code>$queue</code>: <code>\Illuminate\Contracts\Queue\Factory</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>later($delay, Queue $queue) -&gt; mixed</code> | Parameters: <code>$delay</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>cc($address, $name = null) -&gt; $this</code> | Parameters: <code>$address</code>: <code>object&#124;array&#124;string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>bcc($address, $name = null) -&gt; $this</code> | Parameters: <code>$address</code>: <code>object&#124;array&#124;string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>to($address, $name = null) -&gt; $this</code> | Parameters: <code>$address</code>: <code>object&#124;array&#124;string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>locale($locale) -&gt; $this</code> | Parameters: <code>$locale</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |
| <code>mailer($mailer) -&gt; $this</code> | Parameters: <code>$mailer</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailable.php) |

### `Illuminate\Contracts\Mail\Mailer`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>to($users) -&gt; \Illuminate\Mail\PendingMail</code> | Parameters: <code>$users</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Mail\PendingMail</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |
| <code>cc($users) -&gt; \Illuminate\Mail\PendingMail</code> | Parameters: <code>$users</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Mail\PendingMail</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |
| <code>bcc($users) -&gt; \Illuminate\Mail\PendingMail</code> | Parameters: <code>$users</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Mail\PendingMail</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |
| <code>raw($text, $callback) -&gt; \Illuminate\Mail\SentMessage&#124;null</code> | Parameters: <code>$text</code>: <code>string</code>. Return contract: <code>\Illuminate\Mail\SentMessage&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |
| <code>send($view, array $data = [], $callback = null) -&gt; \Illuminate\Mail\SentMessage&#124;null</code> | Parameters: <code>$view</code>: <code>\Illuminate\Contracts\Mail\Mailable&#124;string&#124;array</code>; <code>$callback</code>: <code>\Closure&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Mail\SentMessage&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |
| <code>sendNow($mailable, array $data = [], $callback = null) -&gt; \Illuminate\Mail\SentMessage&#124;null</code> | Parameters: <code>$mailable</code>: <code>\Illuminate\Contracts\Mail\Mailable&#124;string&#124;array</code>; <code>$callback</code>: <code>\Closure&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Mail\SentMessage&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.mail; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Mail/Mailer.php) |

### `Illuminate\Contracts\Notifications\Dispatcher`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Dispatcher.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>send($notifiables, $notification) -&gt; void</code> | Parameters: <code>$notifiables</code>: <code>\Illuminate\Support\Collection&#124;mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.notifications; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Dispatcher.php) |
| <code>sendNow($notifiables, $notification, ?array $channels = null) -&gt; void</code> | Parameters: <code>$notifiables</code>: <code>\Illuminate\Support\Collection&#124;mixed</code>; <code>$channels</code>: <code>array&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.notifications; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Dispatcher.php) |

### `Illuminate\Contracts\Notifications\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>channel($name = null) -&gt; mixed</code> | Parameters: <code>$name</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.notifications; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Factory.php) |
| <code>send($notifiables, $notification) -&gt; void</code> | Parameters: <code>$notifiables</code>: <code>\Illuminate\Support\Collection&#124;mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.notifications; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Factory.php) |
| <code>sendNow($notifiables, $notification) -&gt; void</code> | Parameters: <code>$notifiables</code>: <code>\Illuminate\Support\Collection&#124;mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.notifications; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Notifications/Factory.php) |

### `Illuminate\Contracts\Pagination\CursorPaginator`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>url($cursor) -&gt; string</code> | Parameters: <code>$cursor</code>: <code>\Illuminate\Pagination\Cursor&#124;null</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>appends($key, $value = null) -&gt; $this</code> | Parameters: <code>$key</code>: <code>array&#124;string&#124;null</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>fragment($fragment = null) -&gt; ($fragment is null ? string&#124;null : $this)</code> | Parameters: <code>$fragment</code>: <code>string&#124;null</code>. Return contract: <code>($fragment is null ? string&#124;null : $this)</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>withQueryString() -&gt; $this</code> | Parameters: none. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>previousPageUrl() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>nextPageUrl() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>items() -&gt; array&lt;TKey, TValue&gt;</code> | Parameters: none. Return contract: <code>array&lt;TKey, TValue&gt;</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>previousCursor() -&gt; \Illuminate\Pagination\Cursor&#124;null</code> | Parameters: none. Return contract: <code>\Illuminate\Pagination\Cursor&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>nextCursor() -&gt; \Illuminate\Pagination\Cursor&#124;null</code> | Parameters: none. Return contract: <code>\Illuminate\Pagination\Cursor&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>perPage() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>cursor() -&gt; \Illuminate\Pagination\Cursor&#124;null</code> | Parameters: none. Return contract: <code>\Illuminate\Pagination\Cursor&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>hasPages() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>hasMorePages() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>path() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>isEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>isNotEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |
| <code>render($view = null, $data = []) -&gt; \Illuminate\Contracts\Support\Htmlable</code> | Parameters: <code>$view</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Support\Htmlable</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/CursorPaginator.php) |

### `Illuminate\Contracts\Pagination\LengthAwarePaginator`

- Parents: `extends Paginator`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/LengthAwarePaginator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getUrlRange($start, $end) -&gt; array</code> | Parameters: <code>$start</code>: <code>int</code>. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/LengthAwarePaginator.php) |
| <code>total() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/LengthAwarePaginator.php) |
| <code>lastPage() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/LengthAwarePaginator.php) |

### `Illuminate\Contracts\Pagination\Paginator`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>url($page) -&gt; string</code> | Parameters: <code>$page</code>: <code>int</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>appends($key, $value = null) -&gt; $this</code> | Parameters: <code>$key</code>: <code>array&#124;string&#124;null</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>fragment($fragment = null) -&gt; ($fragment is null ? string&#124;null : $this)</code> | Parameters: <code>$fragment</code>: <code>string&#124;null</code>. Return contract: <code>($fragment is null ? string&#124;null : $this)</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>withQueryString() -&gt; $this</code> | Parameters: none. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>nextPageUrl() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>previousPageUrl() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>items() -&gt; array&lt;TKey, TValue&gt;</code> | Parameters: none. Return contract: <code>array&lt;TKey, TValue&gt;</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>firstItem() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>lastItem() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>perPage() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>currentPage() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>hasPages() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>hasMorePages() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>path() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>isEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>isNotEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |
| <code>render($view = null, $data = []) -&gt; \Illuminate\Contracts\Support\Htmlable</code> | Parameters: <code>$view</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Support\Htmlable</code>. | <code>—</code> | **Blocked** | Requires HTTP/routing pagination (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pagination/Paginator.php) |

### `Illuminate\Contracts\Pipeline\Hub`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Hub.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>pipe($object, $pipeline = null) -&gt; mixed</code> | Parameters: <code>$object</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.pipeline; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Hub.php) |

### `Illuminate\Contracts\Pipeline\Pipeline`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Pipeline.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>send($passable) -&gt; $this</code> | Parameters: <code>$passable</code>: <code>mixed</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.pipeline; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Pipeline.php) |
| <code>through($pipes) -&gt; $this</code> | Parameters: <code>$pipes</code>: <code>mixed</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.pipeline; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Pipeline.php) |
| <code>via($method) -&gt; $this</code> | Parameters: <code>$method</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.pipeline; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Pipeline.php) |
| <code>then(Closure $destination) -&gt; mixed</code> | Parameters: <code>$destination</code>: <code>\Closure</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.pipeline; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Pipeline/Pipeline.php) |

### `Illuminate\Contracts\Process\InvokedProcess`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>id() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>command() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>signal(int $signal) -&gt; $this</code> | Parameters: <code>$signal</code>: <code>int</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>running() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>output() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>errorOutput() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>latestOutput() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>latestErrorOutput() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>wait(?callable $output = null) -&gt; \Illuminate\Process\ProcessResult</code> | Parameters: <code>$output</code>: <code>callable&#124;null</code>. Return contract: <code>\Illuminate\Process\ProcessResult</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |
| <code>waitUntil(?callable $output = null) -&gt; \Illuminate\Process\ProcessResult</code> | Parameters: <code>$output</code>: <code>callable&#124;null</code>. Return contract: <code>\Illuminate\Process\ProcessResult</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/InvokedProcess.php) |

### `Illuminate\Contracts\Process\ProcessResult`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>command() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>successful() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>failed() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>exitCode() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>output() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>seeInOutput(string $output) -&gt; bool</code> | Parameters: <code>$output</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>errorOutput() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>seeInErrorOutput(string $output) -&gt; bool</code> | Parameters: <code>$output</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>throw(?callable $callback = null) -&gt; $this</code> | Parameters: <code>$callback</code>: <code>callable&#124;null</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |
| <code>throwIf(bool $condition, ?callable $callback = null) -&gt; $this</code> | Parameters: <code>$condition</code>: <code>bool</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Process/ProcessResult.php) |

### `Illuminate\Contracts\Queue\ClearableQueue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ClearableQueue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>clear($queue) -&gt; int</code> | Parameters: <code>$queue</code>: <code>string</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ClearableQueue.php) |

### `Illuminate\Contracts\Queue\EntityResolver`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/EntityResolver.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>resolve($type, $id) -&gt; mixed</code> | Parameters: <code>$type</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/EntityResolver.php) |

### `Illuminate\Contracts\Queue\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>connection($name = null) -&gt; \Illuminate\Contracts\Queue\Queue</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Queue\Queue</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Factory.php) |

### `Illuminate\Contracts\Queue\Interruptible`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Interruptible.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>interrupted(int $signal) -&gt; void</code> | Parameters: <code>$signal</code>: <code>int</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Interruptible.php) |

### `Illuminate\Contracts\Queue\Job`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>uuid() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>getJobId() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>payload() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>fire() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>release($delay = 0) -&gt; void</code> | Parameters: <code>$delay</code>: <code>int</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>isReleased() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>delete() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>isDeleted() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>isDeletedOrReleased() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>attempts() -&gt; int</code> | Parameters: none. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>hasFailed() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>markAsFailed() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>fail($e = null) -&gt; void</code> | Parameters: <code>$e</code>: <code>\Throwable&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>maxTries() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>maxExceptions() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>timeout() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>retryUntil() -&gt; int&#124;null</code> | Parameters: none. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>getName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>resolveName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>resolveQueuedJobClass() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>getConnectionName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>getQueue() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |
| <code>getRawBody() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Job.php) |

### `Illuminate\Contracts\Queue\Monitor`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Monitor.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>starting($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Monitor.php) |
| <code>looping($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Monitor.php) |
| <code>failing($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Monitor.php) |
| <code>stopping($callback) -&gt; void</code> | Parameters: <code>$callback</code>: <code>mixed</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Monitor.php) |

### `Illuminate\Contracts\Queue\PreparesForDispatch`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/PreparesForDispatch.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>prepareForDispatch() -&gt; bool&#124;void</code> | Parameters: none. Return contract: <code>bool&#124;void</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/PreparesForDispatch.php) |

### `Illuminate\Contracts\Queue\Queue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>size($queue = null) -&gt; int</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>pendingSize($queue = null) -&gt; int</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>delayedSize($queue = null) -&gt; int</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>reservedSize($queue = null) -&gt; int</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>int</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>creationTimeOfOldestPendingJob($queue = null) -&gt; int&#124;null</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>int&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>push($job, $data = &#x27;&#x27;, $queue = null) -&gt; mixed</code> | Parameters: <code>$job</code>: <code>string&#124;object</code>; <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>pushOn($queue, $job, $data = &#x27;&#x27;) -&gt; mixed</code> | Parameters: <code>$queue</code>: <code>string</code>; <code>$data</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>pushRaw($payload, $queue = null, array $options = []) -&gt; mixed</code> | Parameters: <code>$payload</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>later($delay, $job, $data = &#x27;&#x27;, $queue = null) -&gt; mixed</code> | Parameters: <code>$delay</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int</code>; <code>$data</code>: <code>mixed</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>laterOn($queue, $delay, $job, $data = &#x27;&#x27;) -&gt; mixed</code> | Parameters: <code>$queue</code>: <code>string</code>; <code>$job</code>: <code>string&#124;object</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>bulk($jobs, $data = &#x27;&#x27;, $queue = null) -&gt; mixed</code> | Parameters: <code>$jobs</code>: <code>array</code>; <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>pop($queue = null) -&gt; \Illuminate\Contracts\Queue\Job&#124;null</code> | Parameters: <code>$queue</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Contracts\Queue\Job&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>getConnectionName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |
| <code>setConnectionName($name) -&gt; $this</code> | Parameters: <code>$name</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/Queue.php) |

### `Illuminate\Contracts\Queue\QueueableCollection`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableCollection.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getQueueableClass() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableCollection.php) |
| <code>getQueueableIds() -&gt; array&lt;int, mixed&gt;</code> | Parameters: none. Return contract: <code>array&lt;int, mixed&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableCollection.php) |
| <code>getQueueableRelations() -&gt; array&lt;int, string&gt;</code> | Parameters: none. Return contract: <code>array&lt;int, string&gt;</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableCollection.php) |
| <code>getQueueableConnection() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableCollection.php) |

### `Illuminate\Contracts\Queue\QueueableEntity`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableEntity.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getQueueableId() -&gt; mixed</code> | Parameters: none. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableEntity.php) |
| <code>getQueueableRelations() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableEntity.php) |
| <code>getQueueableConnection() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.queue; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/QueueableEntity.php) |

### `Illuminate\Contracts\Queue\ShouldBeEncrypted`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeEncrypted.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Queue\ShouldBeEncrypted</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeEncrypted.php) |

### `Illuminate\Contracts\Queue\ShouldBeUnique`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeUnique.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Queue\ShouldBeUnique</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker declaration; uniqueness lifecycle and storage semantics belong to a future queue contract. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeUnique.php) |

### `Illuminate\Contracts\Queue\ShouldBeUniqueUntilProcessing`

- Parents: `extends ShouldBeUnique`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeUniqueUntilProcessing.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Queue\ShouldBeUniqueUntilProcessing</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldBeUniqueUntilProcessing.php) |

### `Illuminate\Contracts\Queue\ShouldQueue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldQueue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Queue\ShouldQueue</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldQueue.php) |

### `Illuminate\Contracts\Queue\ShouldQueueAfterCommit`

- Parents: `extends ShouldQueue`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldQueueAfterCommit.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Queue\ShouldQueueAfterCommit</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/ShouldQueueAfterCommit.php) |

### `Illuminate\Contracts\Redis\Connection`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connection.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>subscribe($channels, Closure $callback) -&gt; void</code> | Parameters: <code>$channels</code>: <code>array&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connection.php) |
| <code>psubscribe($channels, Closure $callback) -&gt; void</code> | Parameters: <code>$channels</code>: <code>array&#124;string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connection.php) |
| <code>command($method, array $parameters = []) -&gt; mixed</code> | Parameters: <code>$method</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connection.php) |

### `Illuminate\Contracts\Redis\Connector`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connector.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>connect(array $config, array $options) -&gt; \Illuminate\Redis\Connections\Connection</code> | Parameters: <code>$config</code>: <code>array</code>. Return contract: <code>\Illuminate\Redis\Connections\Connection</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connector.php) |
| <code>connectToCluster(array $config, array $clusterOptions, array $options) -&gt; \Illuminate\Redis\Connections\Connection</code> | Parameters: <code>$config</code>: <code>array</code>; <code>$options</code>: <code>array</code>. Return contract: <code>\Illuminate\Redis\Connections\Connection</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Connector.php) |

### `Illuminate\Contracts\Redis\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>connection($name = null) -&gt; \Illuminate\Redis\Connections\Connection</code> | Parameters: <code>$name</code>: <code>\UnitEnum&#124;string&#124;null</code>. Return contract: <code>\Illuminate\Redis\Connections\Connection</code>. | <code>—</code> | **Blocked** | Requires cache or queue Redis adapters (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/Factory.php) |

### `Illuminate\Contracts\Routing\BindingRegistrar`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/BindingRegistrar.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>bind($key, $binder) -&gt; void</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/BindingRegistrar.php) |
| <code>getBindingCallback($key) -&gt; \Closure&#124;null</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>\Closure&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/BindingRegistrar.php) |

### `Illuminate\Contracts\Routing\Registrar`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>post($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>put($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>delete($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>patch($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>options($uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$uri</code>: <code>string</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>match($methods, $uri, $action) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$methods</code>: <code>array&#124;string</code>; <code>$action</code>: <code>array&#124;string&#124;callable</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>resource($name, $controller, array $options = []) -&gt; \Illuminate\Routing\PendingResourceRegistration</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$options</code>: <code>array</code>. Return contract: <code>\Illuminate\Routing\PendingResourceRegistration</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>group(array $attributes, $routes) -&gt; void</code> | Parameters: <code>$attributes</code>: <code>array</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>substituteBindings($route) -&gt; \Illuminate\Routing\Route</code> | Parameters: <code>$route</code>: <code>\Illuminate\Routing\Route</code>. Return contract: <code>\Illuminate\Routing\Route</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |
| <code>substituteImplicitBindings($route) -&gt; void</code> | Parameters: <code>$route</code>: <code>\Illuminate\Routing\Route</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/Registrar.php) |

### `Illuminate\Contracts\Routing\ResponseFactory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>make($content = &#x27;&#x27;, $status = 200, array $headers = []) -&gt; \Illuminate\Http\Response</code> | Parameters: <code>$content</code>: <code>array&#124;string</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Illuminate\Http\Response</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>noContent($status = 204, array $headers = []) -&gt; \Illuminate\Http\Response</code> | Parameters: <code>$status</code>: <code>int</code>. Return contract: <code>\Illuminate\Http\Response</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>view($view, $data = [], $status = 200, array $headers = []) -&gt; \Illuminate\Http\Response</code> | Parameters: <code>$view</code>: <code>string&#124;array</code>; <code>$status</code>: <code>int</code>. Return contract: <code>\Illuminate\Http\Response</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>json($data = [], $status = 200, array $headers = [], $options = 0) -&gt; \Illuminate\Http\JsonResponse</code> | Parameters: <code>$data</code>: <code>mixed</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Illuminate\Http\JsonResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>jsonp($callback, $data = [], $status = 200, array $headers = [], $options = 0) -&gt; \Illuminate\Http\JsonResponse</code> | Parameters: <code>$callback</code>: <code>string</code>; <code>$status</code>: <code>int</code>; <code>$options</code>: <code>int</code>. Return contract: <code>\Illuminate\Http\JsonResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>eventStream(Closure $callback, array $headers = [], StreamedEvent&#124;string&#124;null $endStreamWith = &#x27;&lt;/stream&gt;&#x27;) -&gt; \Symfony\Component\HttpFoundation\StreamedResponse</code> | Parameters: <code>$callback</code>: <code>\Closure</code>; <code>$endStreamWith</code>: <code>\Illuminate\Http\StreamedEvent&#124;string&#124;null</code>. Return contract: <code>\Symfony\Component\HttpFoundation\StreamedResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>stream($callback, $status = 200, array $headers = []) -&gt; \Symfony\Component\HttpFoundation\StreamedResponse</code> | Parameters: <code>$callback</code>: <code>callable</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Symfony\Component\HttpFoundation\StreamedResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>streamJson($data, $status = 200, $headers = [], $encodingOptions = 15) -&gt; \Symfony\Component\HttpFoundation\StreamedJsonResponse</code> | Parameters: <code>$data</code>: <code>array</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Symfony\Component\HttpFoundation\StreamedJsonResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>streamDownload($callback, $name = null, array $headers = [], $disposition = &#x27;attachment&#x27;) -&gt; \Symfony\Component\HttpFoundation\StreamedResponse</code> | Parameters: <code>$callback</code>: <code>callable</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Symfony\Component\HttpFoundation\StreamedResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>download($file, $name = null, array $headers = [], $disposition = &#x27;attachment&#x27;) -&gt; \Symfony\Component\HttpFoundation\BinaryFileResponse</code> | Parameters: <code>$file</code>: <code>\SplFileInfo&#124;string</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Symfony\Component\HttpFoundation\BinaryFileResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>file($file, array $headers = []) -&gt; \Symfony\Component\HttpFoundation\BinaryFileResponse</code> | Parameters: <code>$file</code>: <code>\SplFileInfo&#124;string</code>. Return contract: <code>\Symfony\Component\HttpFoundation\BinaryFileResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>redirectTo($path, $status = 302, $headers = [], $secure = null) -&gt; \Illuminate\Http\RedirectResponse</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Illuminate\Http\RedirectResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>redirectToRoute($route, $parameters = [], $status = 302, $headers = []) -&gt; \Illuminate\Http\RedirectResponse</code> | Parameters: <code>$route</code>: <code>\BackedEnum&#124;string</code>; <code>$status</code>: <code>int</code>. Return contract: <code>\Illuminate\Http\RedirectResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>redirectToAction($action, $parameters = [], $status = 302, $headers = []) -&gt; \Illuminate\Http\RedirectResponse</code> | Parameters: <code>$action</code>: <code>array&#124;string</code>; <code>$status</code>: <code>int</code>. Return contract: <code>\Illuminate\Http\RedirectResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>redirectGuest($path, $status = 302, $headers = [], $secure = null) -&gt; \Illuminate\Http\RedirectResponse</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Illuminate\Http\RedirectResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |
| <code>redirectToIntended($default = &#x27;/&#x27;, $status = 302, $headers = [], $secure = null) -&gt; \Illuminate\Http\RedirectResponse</code> | Parameters: <code>$default</code>: <code>string</code>; <code>$headers</code>: <code>array</code>. Return contract: <code>\Illuminate\Http\RedirectResponse</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/ResponseFactory.php) |

### `Illuminate\Contracts\Routing\UrlGenerator`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>current() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>previous($fallback = false) -&gt; string</code> | Parameters: <code>$fallback</code>: <code>mixed</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>to($path, $extra = [], $secure = null) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$secure</code>: <code>bool&#124;null</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>secure($path, $parameters = []) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>asset($path, $secure = null) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>route($name, $parameters = [], $absolute = true) -&gt; string</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$absolute</code>: <code>bool</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>signedRoute($name, $parameters = [], $expiration = null, $absolute = true) -&gt; string</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$expiration</code>: <code>\DateTimeInterface&#124;\DateInterval&#124;int&#124;null</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>temporarySignedRoute($name, $expiration, $parameters = [], $absolute = true) -&gt; string</code> | Parameters: <code>$name</code>: <code>string</code>; <code>$parameters</code>: <code>array</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>query($path, $query = [], $extra = [], $secure = null) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$extra</code>: <code>mixed</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>action($action, $parameters = [], $absolute = true) -&gt; string</code> | Parameters: <code>$action</code>: <code>string&#124;array</code>; <code>$absolute</code>: <code>bool</code>. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>getRootControllerNamespace() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |
| <code>setRootControllerNamespace($rootNamespace) -&gt; $this</code> | Parameters: <code>$rootNamespace</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlGenerator.php) |

### `Illuminate\Contracts\Routing\UrlRoutable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlRoutable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getRouteKey() -&gt; mixed</code> | Parameters: none. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlRoutable.php) |
| <code>getRouteKeyName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlRoutable.php) |
| <code>resolveRouteBinding($value, $field = null) -&gt; \Illuminate\Database\Eloquent\Model&#124;null</code> | Parameters: <code>$value</code>: <code>mixed</code>. Return contract: <code>\Illuminate\Database\Eloquent\Model&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlRoutable.php) |
| <code>resolveChildRouteBinding($childType, $value, $field) -&gt; \Illuminate\Database\Eloquent\Model&#124;null</code> | Parameters: <code>$childType</code>: <code>string</code>; <code>$field</code>: <code>string&#124;null</code>. Return contract: <code>\Illuminate\Database\Eloquent\Model&#124;null</code>. | <code>—</code> | **Blocked** | Requires titanspan.routing; no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Routing/UrlRoutable.php) |

### `Illuminate\Contracts\Session\Session`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getName() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>setName($name) -&gt; void</code> | Parameters: <code>$name</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>getId() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>setId($id) -&gt; void</code> | Parameters: <code>$id</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>start() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>save() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>all() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>exists($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string&#124;array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>has($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string&#124;array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>get($key, $default = null) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>pull($key, $default = null) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>put($key, $value = null) -&gt; void</code> | Parameters: <code>$key</code>: <code>string&#124;array</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>flash(string $key, $value = true) -&gt; void</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>token() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>regenerateToken() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>remove($key) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>forget($keys) -&gt; void</code> | Parameters: <code>$keys</code>: <code>string&#124;array</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>flush() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>invalidate() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>regenerate($destroy = false) -&gt; bool</code> | Parameters: <code>$destroy</code>: <code>bool</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>migrate($destroy = false) -&gt; bool</code> | Parameters: <code>$destroy</code>: <code>bool</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>isStarted() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>previousUrl() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>setPreviousUrl($url) -&gt; void</code> | Parameters: <code>$url</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>getHandler() -&gt; \SessionHandlerInterface</code> | Parameters: none. Return contract: <code>\SessionHandlerInterface</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>handlerNeedsRequest() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |
| <code>setRequestOnHandler($request) -&gt; void</code> | Parameters: <code>$request</code>: <code>\Illuminate\Http\Request</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires session/authentication integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Session.php) |

### `Illuminate\Contracts\Session\Middleware\AuthenticatesSessions`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Middleware/AuthenticatesSessions.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Session\Middleware\AuthenticatesSessions</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Session/Middleware/AuthenticatesSessions.php) |

### `Illuminate\Contracts\Support\Arrayable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Arrayable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toArray() -&gt; array&lt;TKey, TValue&gt;</code> | Parameters: none. Return contract: <code>array&lt;TKey, TValue&gt;</code>. | <code>Arrayable.to_array; LaravelArrayable.toArray</code> | **Contract defined, implementation pending** | The protocols define shape only; no Titanspan production value currently implements the array-conversion contract. Test evidence: tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Arrayable.php) |

### `Illuminate\Contracts\Support\CanBeEscapedWhenCastToString`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/CanBeEscapedWhenCastToString.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>escapeWhenCastingToString($escape = true) -&gt; $this</code> | Parameters: <code>$escape</code>: <code>bool</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.support. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/CanBeEscapedWhenCastToString.php) |

### `Illuminate\Contracts\Support\DeferrableProvider`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/DeferrableProvider.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>provides() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.support. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/DeferrableProvider.php) |

### `Illuminate\Contracts\Support\DeferringDisplayableValue`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/DeferringDisplayableValue.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>resolveDisplayableValue() -&gt; \Illuminate\Contracts\Support\Htmlable&#124;string</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Support\Htmlable&#124;string</code>. | <code>DeferringDisplayableValue.resolve_displayable_value; LaravelDeferringDisplayableValue.resolveDisplayableValue</code> | **Python-adapted compatibility** | Separate protocols accept either spelling; resolved values are escaped or retained as trusted HTML by the Support implementation. Test evidence: tests/unit/support/test_html_strings.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/DeferringDisplayableValue.php) |

### `Illuminate\Contracts\Support\HasOnceHash`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/HasOnceHash.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>onceHash() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under titanspan.support. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/HasOnceHash.php) |

### `Illuminate\Contracts\Support\Htmlable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Htmlable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toHtml() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>Htmlable.to_html; LaravelHtmlable.toHtml</code> | **Python-adapted compatibility** | The Python spelling is canonical; the legacy spelling is accepted through a separate protocol. Test evidence: tests/unit/support/test_html_strings.py; tests/unit/support/test_uri.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Htmlable.php) |

### `Illuminate\Contracts\Support\Jsonable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Jsonable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toJson($options = 0) -&gt; string</code> | Parameters: <code>$options</code>: <code>int</code>. Return contract: <code>string</code>. | <code>Jsonable.to_json; LaravelJsonable.toJson</code> | **Contract defined, implementation pending** | PHP JSON option bits are not translated into Python serializer options; no concrete serializer contract implementation exists. Test evidence: tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Jsonable.php) |

### `Illuminate\Contracts\Support\MessageBag`

- Parents: `extends Arrayable, Countable`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>keys() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>MessageBagData.keys</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>add($key, $message) -&gt; $this</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>MessageBagData.add</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>merge($messages) -&gt; $this</code> | Parameters: <code>$messages</code>: <code>\Illuminate\Contracts\Support\MessageProvider&#124;array</code>. Return contract: <code>$this</code>. | <code>MessageBagData.merge</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>has($key) -&gt; bool</code> | Parameters: <code>$key</code>: <code>string&#124;array</code>. Return contract: <code>bool</code>. | <code>MessageBagData.has</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>first($key = null, $format = null) -&gt; string</code> | Parameters: <code>$key</code>: <code>string&#124;null</code>. Return contract: <code>string</code>. | <code>MessageBagData.first</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>get($key, $format = null) -&gt; array</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>array</code>. | <code>MessageBagData.get</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>all($format = null) -&gt; array</code> | Parameters: <code>$format</code>: <code>string&#124;null</code>. Return contract: <code>array</code>. | <code>MessageBagData.all</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>forget($key) -&gt; $this</code> | Parameters: <code>$key</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>MessageBagData.forget</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>getMessages() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>MessageBagData.get_messages / getMessages</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>getFormat() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>MessageBagData.get_format / getFormat</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>setFormat($format = &#x27;:message&#x27;) -&gt; $this</code> | Parameters: <code>$format</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>MessageBagData.set_format / setFormat</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>isEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>MessageBagData.is_empty / isEmpty</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |
| <code>isNotEmpty() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>MessageBagData.is_not_empty / isNotEmpty</code> | **Python-adapted compatibility** | The concrete bag keeps Laravel spellings and Python aliases on one implementation; Python key and mapping semantics apply. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageBag.php) |

### `Illuminate\Contracts\Support\MessageProvider`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageProvider.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>getMessageBag() -&gt; \Illuminate\Contracts\Support\MessageBag</code> | Parameters: none. Return contract: <code>\Illuminate\Contracts\Support\MessageBag</code>. | <code>MessageProvider.get_message_bag; titanspan.support.MessageBag.getMessageBag</code> | **Python-adapted compatibility** | The concrete Support value exposes both method spellings; the native protocol remains snake_case. Test evidence: tests/unit/support/test_message_bag.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/MessageProvider.php) |

### `Illuminate\Contracts\Support\Renderable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Renderable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>render() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>Renderable.render</code> | **Contract defined, implementation pending** | The text-rendering protocol is defined; no view/rendering component currently implements it. Test evidence: tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Renderable.php) |

### `Illuminate\Contracts\Support\Responsable`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Responsable.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toResponse($request) -&gt; \Symfony\Component\HttpFoundation\Response</code> | Parameters: <code>$request</code>: <code>\Illuminate\Http\Request</code>. Return contract: <code>\Symfony\Component\HttpFoundation\Response</code>. | <code>Responsable.to_response; LaravelResponsable.toResponse</code> | **Contract defined, implementation pending** | Generic request/response types avoid framework dependencies; the HTTP response integration is not implemented. Test evidence: tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/Responsable.php) |

### `Illuminate\Contracts\Support\ValidatedData`

- Parents: `extends Arrayable, ArrayAccess, IteratorAggregate`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/ValidatedData.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Support\ValidatedData</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `ValidatedData` (titanspan.contracts.support) | **Contract defined, implementation pending** | Inherits upstream array conversion, array access, and iteration obligations. The Titanspan protocol models typed mapping access and conversion; no production implementation currently advertises this behavior. Evidence: tests/unit/contracts/test_contracts.py. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Support/ValidatedData.php) |

### `Illuminate\Contracts\Translation\HasLocalePreference`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/HasLocalePreference.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>preferredLocale() -&gt; string&#124;null</code> | Parameters: none. Return contract: <code>string&#124;null</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/HasLocalePreference.php) |

### `Illuminate\Contracts\Translation\Loader`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Loader.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>load($locale, $group, $namespace = null) -&gt; array</code> | Parameters: <code>$locale</code>: <code>string</code>; <code>$namespace</code>: <code>string&#124;null</code>. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Loader.php) |
| <code>addNamespace($namespace, $hint) -&gt; void</code> | Parameters: <code>$namespace</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Loader.php) |
| <code>addJsonPath($path) -&gt; void</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Loader.php) |
| <code>namespaces() -&gt; array&lt;string, string&gt;</code> | Parameters: none. Return contract: <code>array&lt;string, string&gt;</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Loader.php) |

### `Illuminate\Contracts\Translation\Translator`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Translator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get($key, array $replace = [], $locale = null) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>string</code>; <code>$locale</code>: <code>string&#124;null</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Translator.php) |
| <code>choice($key, $number, array $replace = [], $locale = null) -&gt; string</code> | Parameters: <code>$key</code>: <code>string</code>; <code>$replace</code>: <code>array</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Translator.php) |
| <code>getLocale() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Translator.php) |
| <code>setLocale($locale) -&gt; void</code> | Parameters: <code>$locale</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Translation/Translator.php) |

### `Illuminate\Contracts\Validation\CompilableRules`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/CompilableRules.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>compile($attribute, $value, $data = null, $context = null) -&gt; \stdClass</code> | Parameters: <code>$attribute</code>: <code>string</code>; <code>$data</code>: <code>mixed</code>. Return contract: <code>\stdClass</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/CompilableRules.php) |

### `Illuminate\Contracts\Validation\DataAwareRule`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/DataAwareRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>setData(array $data) -&gt; $this</code> | Parameters: <code>$data</code>: <code>array</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/DataAwareRule.php) |

### `Illuminate\Contracts\Validation\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>make(array $data, array $rules, array $messages = [], array $attributes = []) -&gt; \Illuminate\Contracts\Validation\Validator</code> | Parameters: <code>$data</code>: <code>array</code>; <code>$messages</code>: <code>array</code>. Return contract: <code>\Illuminate\Contracts\Validation\Validator</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Factory.php) |
| <code>extend($rule, $extension, $message = null) -&gt; void</code> | Parameters: <code>$rule</code>: <code>string</code>; <code>$message</code>: <code>string&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Factory.php) |
| <code>extendImplicit($rule, $extension, $message = null) -&gt; void</code> | Parameters: <code>$rule</code>: <code>string</code>; <code>$message</code>: <code>string&#124;null</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Factory.php) |
| <code>replacer($rule, $replacer) -&gt; void</code> | Parameters: <code>$rule</code>: <code>string</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Factory.php) |

### `Illuminate\Contracts\Validation\ImplicitRule`

- Parents: `extends Rule`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ImplicitRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>Illuminate\Contracts\Validation\ImplicitRule</code> marker declaration | No direct methods. Inherited methods, if any, are listed at the parent interface. | `—` (—) | **Pending** | Marker interface; no direct methods are declared. Its semantics remain pending unless explicitly noted in the contract notes. Evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ImplicitRule.php) |

### `Illuminate\Contracts\Validation\InvokableRule`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/InvokableRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>__invoke(string $attribute, mixed $value, Closure $fail) -&gt; void</code> | Parameters: <code>$attribute</code>: <code>string</code>; <code>$fail</code>: <code>\Closure(string, ?string=): \Illuminate\Translation\PotentiallyTranslatedString</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/InvokableRule.php) |

### `Illuminate\Contracts\Validation\ParameterizedRule`

- Parents: `extends Stringable`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ParameterizedRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>toArray() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ParameterizedRule.php) |

### `Illuminate\Contracts\Validation\Rule`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Rule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>passes($attribute, $value) -&gt; bool</code> | Parameters: <code>$attribute</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Rule.php) |
| <code>message() -&gt; string&#124;array</code> | Parameters: none. Return contract: <code>string&#124;array</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Rule.php) |

### `Illuminate\Contracts\Validation\UncompromisedVerifier`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/UncompromisedVerifier.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>verify($data) -&gt; bool</code> | Parameters: <code>$data</code>: <code>array</code>. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/UncompromisedVerifier.php) |

### `Illuminate\Contracts\Validation\ValidatesWhenResolved`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidatesWhenResolved.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>validateResolved() -&gt; void</code> | Parameters: none. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidatesWhenResolved.php) |

### `Illuminate\Contracts\Validation\ValidationRule`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidationRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>validate(string $attribute, mixed $value, Closure $fail) -&gt; void</code> | Parameters: <code>$attribute</code>: <code>string</code>; <code>$fail</code>: <code>\Closure(string, ?string=): \Illuminate\Translation\PotentiallyTranslatedString</code>. Return contract: <code>void</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidationRule.php) |

### `Illuminate\Contracts\Validation\Validator`

- Parents: `extends MessageProvider`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>validate() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>validated() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>fails() -&gt; bool</code> | Parameters: none. Return contract: <code>bool</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>failed() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>sometimes($attribute, $rules, callable $callback) -&gt; $this</code> | Parameters: <code>$attribute</code>: <code>string&#124;array</code>; <code>$callback</code>: <code>callable</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>after($callback) -&gt; $this</code> | Parameters: <code>$callback</code>: <code>callable&#124;string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |
| <code>errors() -&gt; \Illuminate\Support\MessageBag</code> | Parameters: none. Return contract: <code>\Illuminate\Support\MessageBag</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/Validator.php) |

### `Illuminate\Contracts\Validation\ValidatorAwareRule`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidatorAwareRule.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>setValidator(Validator $validator) -&gt; $this</code> | Parameters: <code>$validator</code>: <code>\Illuminate\Validation\Validator</code>. Return contract: <code>$this</code>. | <code>—</code> | **Blocked** | Requires Pydantic-backed validation integration (not yet implemented); no compatible Titanspan contract or implementation is currently available. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Validation/ValidatorAwareRule.php) |

### `Illuminate\Contracts\View\Engine`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Engine.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>get($path, array $data = []) -&gt; string</code> | Parameters: <code>$path</code>: <code>string</code>. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Engine.php) |

### `Illuminate\Contracts\View\Factory`

- Parents: `none`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>exists($view) -&gt; bool</code> | Parameters: <code>$view</code>: <code>string</code>. Return contract: <code>bool</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>file($path, $data = [], $mergeData = []) -&gt; \Illuminate\Contracts\View\View</code> | Parameters: <code>$path</code>: <code>string</code>; <code>$mergeData</code>: <code>array</code>. Return contract: <code>\Illuminate\Contracts\View\View</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>make($view, $data = [], $mergeData = []) -&gt; \Illuminate\Contracts\View\View</code> | Parameters: <code>$view</code>: <code>string</code>; <code>$mergeData</code>: <code>array</code>. Return contract: <code>\Illuminate\Contracts\View\View</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>share($key, $value = null) -&gt; mixed</code> | Parameters: <code>$key</code>: <code>array&#124;string</code>. Return contract: <code>mixed</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>composer($views, $callback) -&gt; array</code> | Parameters: <code>$views</code>: <code>array&#124;string</code>. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>creator($views, $callback) -&gt; array</code> | Parameters: <code>$views</code>: <code>array&#124;string</code>. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>addNamespace($namespace, $hints) -&gt; $this</code> | Parameters: <code>$namespace</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |
| <code>replaceNamespace($namespace, $hints) -&gt; $this</code> | Parameters: <code>$namespace</code>: <code>string</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/Factory.php) |

### `Illuminate\Contracts\View\View`

- Parents: `extends Renderable`.
- Constants: none.
- Source: [pinned declaration](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/View.php).

| Upstream interface/API | Parameters and return semantics | Titanspan equivalent and owner | Status | Evidence and differences | Source |
| --- | --- | --- | --- | --- | --- |
| <code>name() -&gt; string</code> | Parameters: none. Return contract: <code>string</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/View.php) |
| <code>with($key, $value = null) -&gt; $this</code> | Parameters: <code>$key</code>: <code>string&#124;array</code>. Return contract: <code>$this</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/View.php) |
| <code>getData() -&gt; array</code> | Parameters: none. Return contract: <code>array</code>. | <code>—</code> | **Pending** | No equivalent public contract or verified behavior exists under no established Titanspan owner. Test evidence: —. | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/View.php) |

## Concrete declarations in the Contracts tree

The source tree also contains concrete exception and helper classes. They are inventoried separately because they are not interfaces and are not copied into Titanspan's abstraction layer.

| Upstream class | Public methods | Public properties | Titanspan owner | Status | Source |
| --- | --- | --- | --- | --- | --- |
| `Illuminate\Contracts\Cache\LockTimeoutException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Cache/LockTimeoutException.php) |
| `Illuminate\Contracts\Container\BindingResolutionException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/BindingResolutionException.php) |
| `Illuminate\Contracts\Container\CircularDependencyException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Container/CircularDependencyException.php) |
| `Illuminate\Contracts\Database\ModelIdentifier` | `__construct`, `useCollectionClass`, `getClass`, `useMorphMap` | `$class`, `$id`, `$relations`, `$connection`, `$collectionClass` | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Database/ModelIdentifier.php) |
| `Illuminate\Contracts\Encryption\DecryptException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/DecryptException.php) |
| `Illuminate\Contracts\Encryption\EncryptException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Encryption/EncryptException.php) |
| `Illuminate\Contracts\Filesystem\FileNotFoundException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/FileNotFoundException.php) |
| `Illuminate\Contracts\Filesystem\LockTimeoutException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Filesystem/LockTimeoutException.php) |
| `Illuminate\Contracts\Queue\EntityNotFoundException` | `__construct` | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Queue/EntityNotFoundException.php) |
| `Illuminate\Contracts\Redis\LimiterTimeoutException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Redis/LimiterTimeoutException.php) |
| `Illuminate\Contracts\View\ViewCompilationException` | none | none | No concrete exception/helper owner selected. | **Pending** | [source](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/View/ViewCompilationException.php) |

## Compatibility totals

- Direct upstream interface methods: **564**.
- Additional unique inherited API methods: **16**.
- Total unique method-level inventory: **580**.
- Marker interface declarations: **25**.
- Concrete class declarations: **11**.
- Exact behavioural compatibility: **0** methods.
- Python-adapted compatibility: **16** methods.
- Verified implementation: **6** methods.
- Contract defined, implementation pending: **5** methods.
- Blocked: **363** methods.
- Not applicable: **0** methods.
- Pending: **174** methods.
- Verified direct Laravel method compatibility: **16/564 (2.84%)**.
- Verified compatibility across direct and inherited APIs: **17/580 (2.93%)**; the additional verified inherited method is PHP `Countable.count` adapted to Python `MessageBag.__len__`.
- Marker declarations with exact behavioural compatibility: **0**.
- Marker declarations with python-adapted compatibility: **0**.
- Marker declarations with verified implementation: **0**.
- Marker declarations with contract defined, implementation pending: **1**.
- Marker declarations with blocked: **0**.
- Marker declarations with not applicable: **0**.
- Marker declarations with pending: **24**.
- Concrete declarations with exact behavioural compatibility: **0**.
- Concrete declarations with python-adapted compatibility: **0**.
- Concrete declarations with verified implementation: **0**.
- Concrete declarations with contract defined, implementation pending: **0**.
- Concrete declarations with blocked: **0**.
- Concrete declarations with not applicable: **0**.
- Concrete declarations with pending: **11**.

The denominator includes only methods declared directly by upstream interfaces. Concrete class declarations and inherited methods are accounted for separately and do not inflate the verified percentage. This component does not claim complete Laravel Contracts parity.

## Ownership and implementation policy

Titanspan's current canonical contracts remain dependency-independent. The Support, configuration, and container protocols are declared in `src/titanspan/contracts/`; Logging contracts remain owned by `src/titanspan/logging/contracts/` to avoid a duplicate identity or a dependency cycle. Dishka remains the current container engine, while the native configuration Repository implements the canonical ConfigRepository contract. Pydantic Settings stays private to typed settings validation. The async container protocol still has no adapter.

The Laravel framework is the API reference, not an affiliation or runtime dependency. Python naming, asynchronous resolution, mapping semantics, and application-owned HTTP request/response types are documented adaptations. The full API inventory may contain future work, but pending rows are not supported Titanspan APIs.

The upstream configuration contract uses `get` for either one string key or
an array of keys; it does not declare a separate `getMany` method. Titanspan
models the multi-key form as an overload accepting a list or tuple. The
concrete configuration Repository adds strict string, integer, float,
boolean, and array accessors; the minimal protocol does not require them.
