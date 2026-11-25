# Laravel Configuration compatibility inventory

## Pinned reference

- Laravel framework release: `v13.44.1`.
- Exact source commit: `8a8c4a84852869e13190d89f9da873cd9a70f14c`.
- Verified: 2026-11-25.
- [Pinned Repository implementation](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Config/Repository.php)
- [Pinned Config contract](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Contracts/Config/Repository.php)
- [Pinned Config facade](https://github.com/laravel/framework/blob/8a8c4a84852869e13190d89f9da873cd9a70f14c/src/Illuminate/Support/Facades/Config.php)
- [Laravel configuration documentation](https://laravel.com/docs/13.x/configuration)
- [Pydantic Settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

The inventory covers direct Repository methods, its inherited Macroable
surface, Config contract methods, and static methods declared by the Config
facade. The facade's annotated methods forward to the same Repository API;
they do not represent duplicate implementations. Source loading, environment
bootstrap, and CLI commands are inventoried separately because they are
Foundation behavior rather than Repository methods.

## Status key

- **Exact behavioural parity:** Equivalent behavior for representable inputs.
- **Python-adapted parity:** Verified behavior with Python-specific syntax,
  typing, or lifecycle semantics.
- **Delegated:** Implemented and verified by another Titanspan component.
- **Blocked:** Requires an unavailable owning component.
- **Not applicable:** PHP-specific behavior without a useful Python equivalent.
- **Pending:** Not implemented or not verified.

## `Illuminate\Config\Repository`

| Upstream API | Titanspan API | Owner and evidence | Status and differences |
| --- | --- | --- | --- |
| `__construct($items = [])` | `Repository(items=None)` | `config/repository.py`; `test_repository.py` | Python-adapted; accepts a string-keyed Mapping, not PHP arrays. |
| `has($key)` | `has(key)` | `test_repository.py` | Exact for dotted paths, literal dotted keys, and explicit `None`. |
| `get($key, $default = null)` | `get(key, default=None)` | `test_repository.py` | Python-adapted; accepts path sequences and per-path default mappings. |
| `getMany($keys)` | `get_many(keys)`, `getMany(keys)` | `test_repository.py` | Python-adapted; supports ordered path sequences or string-keyed default mappings. |
| `string($key, $default = null)` | `string(key, default=None)` | `test_repository.py` | Python-adapted; strict type validation and safe native error. |
| `integer($key, $default = null)` | `integer(key, default=None)` | `test_repository.py` | Python-adapted; exact `int` check rejects `bool`. |
| `float($key, $default = null)` | `float(key, default=None)` | `test_repository.py` | Python-adapted; exact `float` check rejects integer values. |
| `boolean($key, $default = null)` | `boolean(key, default=None)` | `test_repository.py` | Python-adapted; exact `bool` check avoids integer coercion. |
| `array($key, $default = null)` | `array(key, default=None)` | `test_repository.py` | Python-adapted; returns a Mapping or list without coercion. |
| `collection($key, $default = null)` | — | `titanspan.collections` is not implemented. | **Blocked**; no duplicate Collection type is introduced. |
| `all()` | `all()` | `test_repository.py` | Python-adapted; returns a copied, read-only mapping snapshot. |
| `set($key, $value = null)` | `set(key, value=None)` | `test_repository.py` | Python-adapted; batch writes are atomic at the root assignment boundary. |
| `prepend($key, $value)` | `prepend(key, value)` | `test_repository.py` | Python-adapted; list-valued configuration is required. |
| `push($key, $value)` | `push(key, value)` | `test_repository.py` | Python-adapted; list-valued configuration is required. |
| `offsetExists($key)` | `key in repository` | `test_repository.py` | Python-adapted through `__contains__`. |
| `offsetGet($key)` | `repository[key]` | `test_repository.py` | Python-adapted; a missing key raises Python `KeyError`. |
| `offsetSet($key, $value)` | `repository[key] = value` | `test_repository.py` | Python-adapted through `__setitem__`; dotted paths are supported. |
| `offsetUnset($key)` | `del repository[key]` | `test_repository.py` | Exact observable mutation; writes `None` instead of removing the path. |

## Macroable behavior

| Upstream API | Titanspan API | Owner and evidence | Status and differences |
| --- | --- | --- | --- |
| `macro($name, $macro)` | `macro(name, callback)` | Support `Macroable`; repository macro tests | Python-adapted; registration is class-level. |
| `mixin($mixin, $replace = true)` | `mixin(mixin, replace=True)` | Support `Macroable`; repository macro tests | Python-adapted; methods are callback factories. |
| `hasMacro($name)` | `has_macro(name)`, `hasMacro(name)` | Support `Macroable`; repository macro tests | Python-adapted; includes inherited registrations. |
| `flushMacros()` | `flush_macros()`, `flushMacros()` | Support `Macroable`; repository macro tests | Python-adapted; clears registrations owned by the class. |
| `__call` / `__callStatic` | `call_macro(name, ...)`, `invoke_macro(name, ...)` | Support `Macroable`; repository and facade macro tests | Python-adapted; no dynamic attribute dispatch; static type discovery is explicit. |

## `Illuminate\Contracts\Config\Repository`

| Upstream API | Titanspan contract | Evidence | Status and differences |
| --- | --- | --- | --- |
| `has($key) -> bool` | `ConfigRepository.has(key)` | contract tests and config application integration | Python-adapted; key is a dotted string path. |
| `get($key, $default = null) -> mixed` | overloaded `ConfigRepository.get(key, default=None)` | contract tests and repository tests | Python-adapted; a list or tuple selects many values in Python. |
| `all() -> array` | `ConfigRepository.all()` | contract tests and repository tests | Python-adapted; the returned repository snapshot is read-only. |
| `set($key, $value = null) -> void` | `ConfigRepository.set(key, value=None)` | contract tests and repository tests | Python-adapted; accepts mappings of dotted assignments. |
| `prepend($key, $value) -> void` | `ConfigRepository.prepend(key, value)` | contract tests and repository tests | Python-adapted; requires list semantics for the stored value. |
| `push($key, $value) -> void` | `ConfigRepository.push(key, value)` | contract tests and repository tests | Python-adapted; requires list semantics for the stored value. |

The contract intentionally remains smaller than the concrete Repository.
`getMany`, typed accessors, mapping operations, macros, and scoped overrides
are concrete extensions rather than obligations imposed on every structural
implementation.

## `Illuminate\Support\Facades\Config`

| Upstream facade method | Titanspan API | Evidence | Status and differences |
| --- | --- | --- | --- |
| `has` | `Config.has(key)` | `test_facade.py` | Python-adapted; resolves the active execution-local repository. |
| `get` | `Config.get(key, default=None)` | `test_facade.py` | Python-adapted; supports sequences and default mappings. |
| `getMany` | `Config.get_many(keys)`, `Config.getMany(keys)` | `test_facade.py` | Python-adapted. |
| `string` | `Config.string(key, default=None)` | `test_facade.py` | Python-adapted. |
| `integer` | `Config.integer(key, default=None)` | `test_facade.py` | Python-adapted; strict Python type semantics. |
| `float` | `Config.float(key, default=None)` | `test_facade.py` | Python-adapted; strict Python type semantics. |
| `boolean` | `Config.boolean(key, default=None)` | `test_facade.py` | Python-adapted. |
| `array` | `Config.array(key, default=None)` | `test_facade.py` | Python-adapted; mappings or lists are supported. |
| `collection` | — | Collections component pending. | **Blocked**. |
| `set` | `Config.set(key, value=None)` | `test_facade.py` | Python-adapted. |
| `prepend` | `Config.prepend(key, value)` | `test_facade.py` | Python-adapted. |
| `push` | `Config.push(key, value)` | `test_facade.py` | Python-adapted. |
| `all` | `Config.all()` | `test_facade.py` | Python-adapted; read-only mapping snapshot. |
| `macro` | `Config.macro(name, callback)` | `test_facade.py` | Delegated to the Repository's Support macro registry. |
| `mixin` | `Config.mixin(mixin, replace=True)` | `test_facade.py` | Delegated to the Repository's Support macro registry. |
| `hasMacro` | `Config.has_macro(name)`, `Config.hasMacro(name)` | `test_facade.py` | Delegated to the Repository's Support macro registry. |
| `flushMacros` | `Config.flush_macros()`, `Config.flushMacros()` | `test_facade.py` | Delegated to the Repository's Support macro registry. |
| `getFacadeAccessor()` | — | Protected Laravel implementation hook. | **Not applicable**; the Python facade binds with `Config.use()`. |
| Facade magic forwarding | Explicit typed methods and `call_macro()` | `test_facade.py` | Python-adapted; no global resolved-facade cache or arbitrary dynamic forwarding. |

## Environment, source loading, and commands

| Laravel capability | Titanspan API | Evidence | Status and differences |
| --- | --- | --- | --- |
| `config()` helper read | `titanspan.support.config(key, default=None)` | `test_facade.py` | Delegated to the active `Config` facade context. |
| `config()` helper write | `config(mapping)` | `test_facade.py` | Python-adapted batch mutation. |
| `config()` helper repository | `config()` | `test_facade.py` | Python-adapted; requires an active application or test binding. |
| `env()` helper | `titanspan.support.env(key, default=None)` | Support environment tests and config integration tests | Delegated to Support; process variables precede the selected dotenv mapping. |
| Config file discovery | `ConfigLoader` | `test_loader.py`; config application integration | Python-adapted; trusted `.py`, `.json`, and `.toml` files. |
| Environment bootstrap | `ConfigLoader` / `Settings.from_environment()` | loader and settings tests | Python-adapted; no `os.environ` mutation or automatic environment-specific file search. |
| `config:cache` | `titanspan config:cache` | `test_config_cli.py`, `test_cache.py` | Python-adapted; safe JSON only, not generated executable code. |
| `config:clear` | `titanspan config:clear` | `test_config_cli.py`, `test_cache.py` | Python-adapted; removes only the configured cache file. |
| `config:show` | `titanspan config:show [key]` | `test_config_cli.py` | Python-adapted; common secret-shaped keys are redacted. |
| `config:validate` | `titanspan config:validate` | `test_config_cli.py` | Titanspan-specific addition. |
| Environment encryption | — | No encryption service exists. | **Pending**; not implemented or advertised. |
| Configuration publishing | — | No package publishing command exists. | **Pending**; application files are never overwritten. |

## Source precedence and differences

Fresh loads apply framework defaults, package defaults, application files,
explicit built-in `Settings` fields, then bootstrap overrides. Nested mapping
defaults merge recursively; lists and scalars replace. This composition is a
Titanspan convention, not a claim that all Laravel bootstrap semantics match.

The loader selects one explicit dotenv path or the root `.env`. It does not
search `.env.<environment>`. Environment parsing follows the canonical
Support `Env` implementation. A valid cache bypasses fresh files and
environment sources unless explicit Settings or bootstrap overrides were
provided. `config:show` and `config:validate` intentionally inspect fresh
sources.

## Test traceability

Laravel's pinned source and tests are the behavioral reference. Titanspan
tests exercise the translated contract and Python-specific boundaries; no
PHP runtime is required by the package or normal test suite.

- Repository and typed retrieval: `tests/unit/config/test_repository.py`.
- Facade, helper, macro, and overrides: `tests/unit/config/test_facade.py`.
- Loading and source precedence: `tests/unit/config/test_loader.py` and
  `tests/unit/config/test_config_manager.py`.
- Cache and settings: `tests/unit/config/test_cache.py` and
  `tests/unit/config/test_settings.py`.
- CLI commands: `tests/unit/config/test_config_cli.py`.
- Real FastAPI/Dishka and dotenv integration:
  `tests/integration/config/test_config_application_integration.py`.
