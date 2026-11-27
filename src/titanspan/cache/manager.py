"""Own configured cache stores for one application service graph.

The manager resolves named backends lazily and closes every instance it
creates during application shutdown.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from threading import RLock
from typing import TYPE_CHECKING, cast

from titanspan.cache._backends.failover import FailoverStore
from titanspan.cache._backends.memory import MemoryStore
from titanspan.cache._backends.null import NullStore
from titanspan.cache._serialization import JSONSerializer
from titanspan.cache.configuration import (
    CacheConfiguration,
    CacheStoreConfiguration,
)
from titanspan.cache.events import CacheEvent
from titanspan.cache.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
)
from titanspan.cache.expiration import normalize_ttl
from titanspan.cache.lock import Lock
from titanspan.cache.repository import MemoRepository, Repository
from titanspan.contracts.cache import (
    CacheRepository,
    CacheStore,
    CacheTTL,
    PrefixClearStore,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from titanspan.contracts.config import ConfigRepository
    from titanspan.contracts.events import EventDispatcher

type CacheDriverFactory = Callable[[CacheStoreConfiguration], CacheStore]

_BUILTIN_DRIVERS = ("failover", "memory", "null", "redis")
_UNKNOWN_STORE_ERROR = "The requested cache store is not configured."
_DUPLICATE_DRIVER_ERROR = "A cache driver name is already registered."
_INVALID_DRIVER_ERROR = "A cache driver registration is invalid."
_DRIVER_FAILURE_ERROR = "The configured cache backend could not be created."
_LOCK_OWNER_TOKEN_LENGTH = 32
_MINIMUM_FAILOVER_STORES = 2
_FAKE_OPERATION_LIMIT = 10_000


class CacheManager:
    """Resolve named repository views and own their backend lifecycles.

    Args:
        configuration: Immutable cache settings for this application.
        drivers: Trusted custom drivers keyed by driver name.
        events: Optional application dispatcher for metadata-only events.
    """

    def __init__(
        self,
        configuration: CacheConfiguration | None = None,
        *,
        drivers: Mapping[str, CacheDriverFactory] | None = None,
        events: EventDispatcher | None = None,
    ) -> None:
        """Create an application-owned manager without opening connections.

        Raises:
            CacheConfigurationError: If driver registrations conflict.
        """
        self._configuration = configuration or CacheConfiguration()
        factories = dict(drivers or {})
        for name, factory in factories.items():
            if (
                not name.isidentifier()
                or name in _BUILTIN_DRIVERS
                or not callable(factory)
            ):
                raise CacheConfigurationError(_INVALID_DRIVER_ERROR)
        self._factories = factories
        self._stores: dict[str, CacheStore] = {}
        self._repositories: dict[str, Repository] = {}
        self._memos: dict[str, MemoRepository] = {}
        self._versions = dict.fromkeys(
            self._configuration.store_configurations,
            0,
        )
        self._events = events
        self._lock = RLock()
        self._fake: ContextVar[CacheFake | None] = ContextVar(
            f"titanspan_cache_fake_{id(self)}",
            default=None,
        )
        self._closed = False
        self.serializer = JSONSerializer(self._configuration.max_value_bytes)

    @classmethod
    def from_repository(
        cls,
        repository: ConfigRepository,
        *,
        drivers: Mapping[str, CacheDriverFactory] | None = None,
        events: EventDispatcher | None = None,
    ) -> CacheManager:
        """Build one manager from the canonical application configuration.

        Args:
            repository: Application-owned Config repository.
            drivers: Trusted additional backend constructors.
            events: Optional application-owned event dispatcher.

        Returns:
            A manager that owns only its own lazily initialized stores.
        """
        return cls(
            CacheConfiguration.from_repository(repository),
            drivers=drivers,
            events=events,
        )

    @property
    def default_store(self) -> str:
        """Return the configured default store name.
        """  # fmt: skip
        return self._configuration.default

    @property
    def store_names(self) -> tuple[str, ...]:
        """Return configured names in stable application order.
        """  # fmt: skip
        return tuple(self._configuration.store_configurations)

    @property
    def driver_names(self) -> tuple[str, ...]:
        """Return built-in and trusted custom driver names.
        """  # fmt: skip
        return (*_BUILTIN_DRIVERS, *self._factories)

    @property
    def configuration(self) -> CacheConfiguration:
        """Return immutable settings without rendering secret options.
        """  # fmt: skip
        return self._configuration

    def lock(
        self,
        key: str,
        *,
        ttl: CacheTTL,
        store: str | None = None,
    ) -> Lock:
        """Create an owner-token lock for one application cache key.

        Args:
            key: Lock identifier within the selected store namespace.
            ttl: Positive seconds or timedelta lease duration.
            store: Named store, or the configured default.

        Returns:
            A lock handle with a new ownership token.
        """
        name = self.default_store if store is None else store
        if name not in self._configuration.store_configurations:
            raise CacheConfigurationError(_UNKNOWN_STORE_ERROR)
        seconds = normalize_ttl(ttl)
        if seconds is None or seconds <= 0:
            msg = "Cache lock lease must be a positive duration."
            raise CacheConfigurationError(msg)
        cast("Repository", self.store(name)).backend_key(key)
        return Lock(self, name, key, seconds)

    def restore_lock(
        self,
        key: str,
        owner: str,
        *,
        ttl: CacheTTL,
        store: str | None = None,
    ) -> Lock:
        """Restore a trusted owner token transferred by application code.

        Args:
            key: Logical lock identifier.
            owner: Token previously returned by a lock handle.
            ttl: Lease duration for future acquisition attempts.
            store: Named store, or the configured default.

        Returns:
            A lock handle for the transferred owner token.
        """
        if (
            type(owner) is not str
            or len(owner) != _LOCK_OWNER_TOKEN_LENGTH
            or any(character not in "0123456789abcdef" for character in owner)
        ):
            msg = "Cache lock owner token is invalid."
            raise CacheConfigurationError(msg)
        lock = self.lock(key, ttl=ttl, store=store)
        return Lock(
            self,
            lock.store_name,
            key,
            lock.lease_seconds,
            owner=owner,
        )

    def status(self, name: str | None = None) -> Mapping[str, object]:
        """Return safe store capabilities and aggregate backend statistics.
        """  # fmt: skip
        selected = (self.default_store,) if name is None else (name,)
        result: dict[str, object] = {}
        for store_name in selected:
            backend = self.resolve_backend(store_name)
            stats = getattr(backend, "stats", None)
            result[store_name] = {
                "driver": self._configuration.store_configurations[
                    store_name
                ].driver,
                "capabilities": backend.capabilities,
                "stats": stats() if callable(stats) else None,
            }
        return result

    async def status_async(
        self,
        name: str | None = None,
    ) -> Mapping[str, object]:
        """Asynchronously return safe store inspection data.
        """  # fmt: skip
        selected = (self.default_store,) if name is None else (name,)
        result: dict[str, object] = {}
        for store_name in selected:
            backend = self.resolve_backend(store_name)
            stats_async = cast(
                "Callable[[], Awaitable[object]] | None",
                getattr(backend, "stats_async", None),
            )
            stats_sync = cast(
                "Callable[[], object] | None",
                getattr(backend, "stats", None),
            )
            if stats_async is not None:
                details = await stats_async()
            else:
                details = stats_sync() if stats_sync is not None else None
            result[store_name] = {
                "driver": self._configuration.store_configurations[
                    store_name
                ].driver,
                "capabilities": backend.capabilities,
                "stats": details,
            }
        return result

    def store(self, name: str | None = None) -> CacheRepository:
        """Return a stable repository view without initializing a backend.

        Args:
            name: Configured store name, or the default when omitted.

        Returns:
            A repository proxy that follows this manager's active fake scope.

        Raises:
            CacheConfigurationError: If the selected store is not configured.
        """
        selected = self.default_store if name is None else name
        if selected not in self._configuration.store_configurations:
            raise CacheConfigurationError(_UNKNOWN_STORE_ERROR)
        with self._lock:
            repository = self._repositories.get(selected)
            if repository is None:
                repository = Repository(self, selected)
                self._repositories[selected] = repository
            return repository

    def memo(self, name: str | None = None) -> MemoRepository:
        """Return a stable execution-local memo view for one named store.

        Args:
            name: Configured store name, or the default when omitted.

        Returns:
            A repository view that caches successful reads per execution.
        """
        selected = self.default_store if name is None else name
        if selected not in self._configuration.store_configurations:
            raise CacheConfigurationError(_UNKNOWN_STORE_ERROR)
        with self._lock:
            memo = self._memos.get(selected)
            if memo is None:
                memo = MemoRepository(self, selected)
                self._memos[selected] = memo
            return memo

    def version(self, name: str) -> int:
        """Return the store mutation generation used by memo views.
        """  # fmt: skip
        with self._lock:
            return self._versions.get(name, 0)

    def invalidate(self, name: str) -> None:
        """Invalidate all memoized values after a successful store mutation.
        """  # fmt: skip
        with self._lock:
            self._versions[name] = self._versions.get(name, 0) + 1

    def fake_identity(self) -> CacheFake | None:
        """Return the active execution fake for memo-scope isolation.
        """  # fmt: skip
        return self._fake.get()

    def extend(self, name: str, factory: CacheDriverFactory) -> None:
        """Register a trusted custom driver before any configured store uses it.

        Args:
            name: New driver identifier referenced by application settings.
            factory: Constructor receiving validated private store settings.

        Raises:
            CacheConfigurationError: If a driver conflicts or a store has
                already been resolved.
        """
        if (
            not name.isidentifier()
            or name in _BUILTIN_DRIVERS
            or name in self._factories
            or not callable(factory)
        ):
            raise CacheConfigurationError(_DUPLICATE_DRIVER_ERROR)
        with self._lock:
            if self._stores:
                msg = "Cache drivers must be registered before store use."
                raise CacheConfigurationError(msg)
            self._factories[name] = factory

    def fake(self, name: str | None = None) -> CacheFakeScope:
        """Create an execution-local fake for all application store views.

        Args:
            name: Optional store restricted to the fake scope. With no name,
                every application cache store is redirected.

        Returns:
            A context manager yielding assertion helpers.
        """
        return CacheFakeScope(self, name)

    def emit(self, action: str, store: str, *, success: bool = True) -> None:
        """Dispatch a metadata-only cache event when enabled.

        Args:
            action: Operation label such as ``hit`` or ``write``.
            store: Configured store identifier.
            success: Whether the operation completed successfully.
        """
        configuration = self._configuration.store_configurations[store]
        if self._events is None or not (
            self._configuration.events and configuration.events
        ):
            return
        self._events.dispatch(CacheEvent(action, store, success))

    async def emit_async(
        self,
        action: str,
        store: str,
        *,
        success: bool = True,
    ) -> None:
        """Asynchronously dispatch a metadata-only cache event.
        """  # fmt: skip
        configuration = self._configuration.store_configurations[store]
        if self._events is None or not (
            self._configuration.events and configuration.events
        ):
            return
        await self._events.dispatch_async(CacheEvent(action, store, success))

    async def aclose(self) -> None:
        """Close initialized stores in reverse construction order.

        Raises:
            CacheBackendError: If one or more store resources fail to close.
        """
        with self._lock:
            if self._closed:
                return
            stores = tuple(reversed(tuple(self._stores.values())))
            self._closed = True
        failures: list[Exception] = []
        for store in stores:
            try:
                await store.aclose()
            except Exception as error:
                failures.append(error)
        if failures:
            msg = "One or more cache backend resources could not be closed."
            raise CacheBackendError(msg) from failures[0]

    def resolve_backend(self, name: str) -> CacheStore:
        """Resolve one lazily built production or fake backend.

        Args:
            name: Configured store identifier.

        Returns:
            Active context fake or lazily constructed application backend.
        """
        fake = self._fake.get()
        if fake is not None:
            if fake.store_name is None or name == fake.store_name:
                return fake.backend
            msg = "Cache access was blocked by a scoped fake substitution."
            raise CacheBackendError(msg)
        with self._lock:
            if self._closed:
                msg = "The cache manager is closed."
                raise CacheBackendError(msg)
            store = self._stores.get(name)
            if store is not None:
                return store
            store_configuration = self._configuration.store_configurations.get(
                name
            )
            if store_configuration is None:
                raise CacheConfigurationError(_UNKNOWN_STORE_ERROR)
            try:
                store = self._create_backend(name, store_configuration)
            except CacheConfigurationError:
                raise
            except Exception as error:
                raise CacheBackendError(_DRIVER_FAILURE_ERROR) from error
            self._stores[name] = store
            return store

    def _create_backend(
        self,
        name: str,
        configuration: CacheStoreConfiguration,
    ) -> CacheStore:
        """Construct one built-in or application-registered backend.
        """  # fmt: skip
        if configuration.driver == "memory":
            limit = configuration.options.get("max_items", 10_000)
            if type(limit) is not int or limit < 1:
                msg = "Memory cache max_items must be positive."
                raise CacheConfigurationError(msg)
            return MemoryStore(max_items=limit)
        if configuration.driver == "null":
            return NullStore()
        if configuration.driver == "failover":
            return self._create_failover(name, configuration)
        if configuration.driver == "redis":
            # Keep the optional dependency unloaded until Redis is selected.
            from titanspan.cache._backends.redis import (  # noqa: PLC0415
                RedisStore,
            )

            return RedisStore(configuration, prefix=self.key_prefix(name))
        factory = self._factories.get(configuration.driver)
        if factory is None:
            raise CacheConfigurationError(_INVALID_DRIVER_ERROR)
        return factory(configuration)

    def _create_failover(
        self,
        name: str,
        configuration: CacheStoreConfiguration,
    ) -> FailoverStore:
        """Create an ordered wrapper over safely scoped child backends.
        """  # fmt: skip
        if set(configuration.options) != {"stores"}:
            msg = "Failover store options must contain only store names."
            raise CacheConfigurationError(msg)
        children = configuration.options.get("stores")
        if not isinstance(children, (list, tuple)):
            msg = "Failover stores require two or more unique child names."
            raise CacheConfigurationError(msg)
        child_values = cast("list[object] | tuple[object, ...]", children)
        if len(child_values) < _MINIMUM_FAILOVER_STORES:
            msg = "Failover stores require two or more unique child names."
            raise CacheConfigurationError(msg)
        selected_list: list[str] = []
        for child in child_values:
            if not isinstance(child, str):
                msg = "Failover child names must be strings."
                raise CacheConfigurationError(msg)
            selected_list.append(child)
        selected = tuple(selected_list)
        if len(set(selected)) != len(selected) or name in selected:
            msg = "Failover stores require two or more unique child names."
            raise CacheConfigurationError(msg)
        stores: list[CacheStore] = []
        clear_stores: list[PrefixClearStore] = []
        for child_name in selected:
            child_configuration = self._configuration.store_configurations.get(
                child_name
            )
            if (
                child_configuration is None
                or child_configuration.driver == "failover"
            ):
                msg = (
                    "Failover children must be configured non-failover stores."
                )
                raise CacheConfigurationError(msg)
            child = self.resolve_backend(child_name)
            if not child.capabilities.scoped_clear or not isinstance(
                child, PrefixClearStore
            ):
                msg = "Failover children must support safe scoped key clearing."
                raise CacheConfigurationError(msg)
            stores.append(child)
            clear_stores.append(child)
        return FailoverStore(
            tuple(stores),
            tuple(clear_stores),
            self.key_prefix(name),
            lambda: self.emit("failover", name),
        )

    def record_fake(
        self,
        store: str,
        operation: str,
        key: str | None,
        result: bool,
    ) -> None:
        """Record operations only in the matching execution fake.
        """  # fmt: skip
        fake = self._fake.get()
        if fake is not None and (
            fake.store_name is None or store == fake.store_name
        ):
            fake.record(operation, key, result)

    def key_prefix(self, name: str) -> str:
        """Return namespace and store prefix for a private backend adapter.
        """  # fmt: skip
        return (
            f"{self._configuration.prefix}:"
            f"{self._configuration.namespace}:{name}:"
        )

    def activate_fake(self, fake: CacheFake) -> Token[CacheFake | None]:
        """Bind one fake in the manager's current execution context.
        """  # fmt: skip
        return self._fake.set(fake)

    def restore_fake(self, token: Token[CacheFake | None]) -> None:
        """Restore the fake binding that preceded one test scope.
        """  # fmt: skip
        self._fake.reset(token)

    _configuration: CacheConfiguration
    _factories: dict[str, CacheDriverFactory]
    _stores: dict[str, CacheStore]
    _repositories: dict[str, Repository]
    _events: EventDispatcher | None
    _lock: RLock
    _fake: ContextVar[CacheFake | None]
    _closed: bool
    serializer: JSONSerializer


class CacheFake:
    """Record cache operations against an isolated in-memory test backend.
    """  # fmt: skip

    def __init__(
        self,
        name: str | None,
        prefixes: Mapping[str, str],
    ) -> None:
        """Create one fake backend and a bounded operation ledger.
        """  # fmt: skip
        self.store_name = name
        self._prefixes = dict(prefixes)
        self._store_names = tuple(prefixes)
        self.backend = MemoryStore(max_items=100_000)
        self.operations: deque[tuple[str, str | None, bool]] = deque(
            maxlen=_FAKE_OPERATION_LIMIT,
        )

    def record(
        self,
        operation: str,
        key: str | None,
        result: bool,
    ) -> None:
        """Append one result without retaining cached values.
        """  # fmt: skip
        self.operations.append((operation, key, result))

    def assert_has(self, key: str, *, store: str | None = None) -> None:
        """Assert the selected fake currently contains a key.
        """  # fmt: skip
        selected = (store,) if store is not None else self._store_names
        if not any(
            self.backend.contains_suffix(prefix, f":{key}")
            for prefix in (self._prefixes[name] for name in selected)
        ):
            msg = f"Expected cache key [{key}] to exist."
            raise AssertionError(msg)

    def assert_missing(self, key: str, *, store: str | None = None) -> None:
        """Assert the selected fake does not contain a key.
        """  # fmt: skip
        selected = (store,) if store is not None else self._store_names
        if any(
            self.backend.contains_suffix(prefix, f":{key}")
            for prefix in (self._prefixes[name] for name in selected)
        ):
            msg = f"Expected cache key [{key}] to be missing."
            raise AssertionError(msg)

    def assert_performed(self, operation: str, key: str | None = None) -> None:
        """Assert that a named operation was recorded by this fake.
        """  # fmt: skip
        if not any(
            action == operation and (key is None or selected == key)
            for action, selected, _ in self.operations
        ):
            msg = f"Expected cache operation [{operation}] was not recorded."
            raise AssertionError(msg)

    def assert_not_performed(
        self,
        operation: str,
        key: str | None = None,
    ) -> None:
        """Assert that one operation does not appear in the fake ledger.
        """  # fmt: skip
        if any(
            action == operation and (key is None or selected == key)
            for action, selected, _ in self.operations
        ):
            msg = f"Unexpected cache operation [{operation}] was recorded."
            raise AssertionError(msg)

    def assert_hit(self, key: str) -> None:
        """Assert that a recorded get returned a cached value.
        """  # fmt: skip
        if not any(
            action == "get" and selected == key and result
            for action, selected, result in self.operations
        ):
            msg = f"Expected cache key [{key}] to be read as a hit."
            raise AssertionError(msg)

    def assert_missed(self, key: str) -> None:
        """Assert that a recorded get missed the cached value.
        """  # fmt: skip
        if not any(
            action == "get" and selected == key and not result
            for action, selected, result in self.operations
        ):
            msg = f"Expected cache key [{key}] to be read as a miss."
            raise AssertionError(msg)

    def assert_lock_acquired(self, key: str) -> None:
        """Assert that an owner acquired a lease for one logical key.
        """  # fmt: skip
        if not any(
            action == "lock_acquire" and selected == key and result
            for action, selected, result in self.operations
        ):
            msg = f"Expected cache lock [{key}] to be acquired."
            raise AssertionError(msg)

    _prefixes: dict[str, str]
    _store_names: tuple[str, ...]


class CacheFakeScope:
    """Bind one fake through the manager's execution-local ContextVar.
    """  # fmt: skip

    def __init__(self, manager: CacheManager, name: str | None) -> None:
        """Create a scope for all stores or one configured store.
        """  # fmt: skip
        if name is not None and name not in manager.store_names:
            raise CacheConfigurationError(_UNKNOWN_STORE_ERROR)
        self._manager = manager
        names = manager.store_names if name is None else (name,)
        prefixes = {store: manager.key_prefix(store) for store in names}
        self._fake = CacheFake(name, prefixes)
        self._token: Token[CacheFake | None] | None = None

    def __enter__(self) -> CacheFake:
        """Redirect cache access in the current sync execution context.
        """  # fmt: skip
        if self._token is not None:
            msg = "A cache fake scope cannot be re-entered."
            raise RuntimeError(msg)
        self._token = self._manager.activate_fake(self._fake)
        return self._fake

    def __exit__(self, *exc_info: object) -> None:
        """Restore the prior execution-local backend substitution.
        """  # fmt: skip
        del exc_info
        token = self._token
        if token is None:
            msg = "The cache fake scope is not active."
            raise RuntimeError(msg)
        self._manager.restore_fake(token)
        self._token = None

    async def __aenter__(self) -> CacheFake:
        """Redirect cache access in the current async execution context.
        """  # fmt: skip
        return self.__enter__()

    async def __aexit__(self, *exc_info: object) -> None:
        """Restore fake substitution after async work or cancellation.
        """  # fmt: skip
        self.__exit__(*exc_info)

    _manager: CacheManager
    _fake: CacheFake
    _token: Token[CacheFake | None] | None


__all__ = ["CacheDriverFactory", "CacheFake", "CacheManager"]
