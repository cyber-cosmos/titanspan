"""Verify context-aware Config facade and Support helper access.

The facade and helper must resolve the same explicitly bound repository and
must restore scoped overrides after failures.
"""

from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, overload

import anyio
import pytest

from titanspan import Application
from titanspan.config import ConfigArray, ConfigContextError, Repository
from titanspan.facades import Config
from titanspan.support import config

pytestmark = pytest.mark.unit
_EXPECTED_FAILURE = "failure"
_EXPECTED_CONCURRENT_TASKS = 2
_WORKER_COUNT = 4
_TEMPERATURE = 0.25

if TYPE_CHECKING:
    from titanspan.contracts.config import (
        ConfigDiagnostics,
        ConfigRepository,
        ScopedConfigOverrides,
        TypedConfigReader,
    )


class _AlternateConfigRepository:
    """Adapt the repository behavior behind a distinct public implementation.

    This object exposes supported configuration capabilities without
    inheriting from the concrete Titanspan repository.
    """

    def __init__(self) -> None:
        """Create isolated values for facade substitution tests.

        The alternate owns an independent production repository internally
        but exposes only the structural contract under test.
        """
        self._store = Repository(
            {
                "app": {"name": "Alternate", "debug": False},
                "items": ["initial"],
            }
        )
        self.batch_reads = 0

    def has(self, key: str) -> bool:
        """Check whether one path exists in the adapted store.

        Args:
            key: Dotted configuration path.

        Returns:
            Whether the path is present.
        """
        return self._store.has(key)

    @overload
    def get(self, key: str, default: object = None) -> object:
        """Retrieve one path from the adapted store.

        Args:
            key: Dotted configuration path.
            default: Fallback value.

        Returns:
            The value or fallback.
        """

    @overload
    def get(
        self,
        key: list[str] | tuple[str, ...] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve multiple paths from the adapted store.

        Args:
            key: Requested paths or per-path defaults.
            default: Shared fallback for path sequences.

        Returns:
            Values keyed by requested paths.
        """

    def get(
        self,
        key: str | list[str] | tuple[str, ...] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Retrieve one or multiple values through the adapted store.

        Args:
            key: Path, sequence of paths, or per-path defaults.
            default: Shared fallback for path sequences.

        Returns:
            The selected value or mapping of values.
        """
        if isinstance(key, str):
            return self._store.get(key, default)
        return self.get_many(key, default)

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve multiple paths and count canonical batch delegation.

        Args:
            keys: Ordered paths or individual defaults.
            default: Shared fallback for ordered paths.

        Returns:
            Values keyed by their requested paths.
        """
        self.batch_reads += 1
        return self._store.get_many(keys, default)

    def all(self) -> Mapping[str, object]:
        """Return all adapted configuration values.

        Returns:
            A read-only snapshot from the wrapped repository.
        """
        return self._store.all()

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Update one path or a batch of paths.

        Args:
            key: Dotted path or mapping of assignments.
            value: Value assigned for a single path.
        """
        self._store.set(key, value)

    def prepend(self, key: str, value: object) -> None:
        """Insert one item at the start of a configured list.

        Args:
            key: Dotted list path.
            value: Item inserted at the beginning.
        """
        self._store.prepend(key, value)

    def push(self, key: str, value: object) -> None:
        """Append one item to a configured list.

        Args:
            key: Dotted list path.
            value: Item appended to the end.
        """
        self._store.push(key, value)

    def string(
        self,
        key: str,
        default: str | Callable[[], str] | None = None,
    ) -> str:
        """Return a strictly validated string value.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            The validated string.
        """
        return self._store.string(key, default)

    def integer(
        self,
        key: str,
        default: int | Callable[[], int] | None = None,
    ) -> int:
        """Return a strictly validated integer value.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            The validated integer.
        """
        return self._store.integer(key, default)

    def float(
        self,
        key: str,
        default: float | Callable[[], float] | None = None,
    ) -> float:
        """Return a strictly validated floating-point value.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            The validated float.
        """
        return self._store.float(key, default)

    def boolean(
        self,
        key: str,
        default: bool | Callable[[], bool] | None = None,
    ) -> bool:
        """Return a strictly validated boolean value.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            The validated boolean.
        """
        return self._store.boolean(key, default)

    def array(
        self,
        key: str,
        default: ConfigArray | Callable[[], ConfigArray] | None = None,
    ) -> ConfigArray:
        """Return a validated mapping or list value.

        Args:
            key: Dotted configuration path.
            default: Optional value or lazy fallback.

        Returns:
            The configured mapping or list.
        """
        return self._store.array(key, default)

    @contextmanager
    def override(
        self,
        values: Mapping[str, object],
    ) -> Generator[None, None, None]:
        """Expose the wrapped repository's task-local override behavior.

        Args:
            values: Temporary path values.

        Yields:
            Control while the override is active.
        """
        with self._store.override(values):
            yield

    def redacted(self) -> Mapping[str, object]:
        """Return a secret-safe diagnostic snapshot.

        Returns:
            The wrapped repository's redacted mapping.
        """
        return self._store.redacted()


def test_config_facade_requires_an_explicit_repository_context() -> None:
    """Avoid silently creating a process-global configuration store.

    Returns:
        None.
    """
    with pytest.raises(ConfigContextError):
        Config.get("app.name")


def test_config_facade_and_helper_share_one_repository() -> None:
    """Resolve, read, mutate, and return the active repository consistently.

    Returns:
        None.
    """
    application = Application()
    repository = Repository(
        {
            "app": {"name": "Titanspan", "debug": False},
            "ai": {"temperature": _TEMPERATURE},
            "queue": {"workers": _WORKER_COUNT},
            "providers": ["local"],
            "middleware": ["auth"],
        }
    )

    with application.context(), Config.use(repository):
        assert Config.repository() is repository
        assert Config.has("app.name")
        assert Config.get("app.name") == "Titanspan"
        assert Config.string("app.name") == "Titanspan"
        assert Config.integer("queue.workers") == _WORKER_COUNT
        assert Config.float("ai.temperature") == _TEMPERATURE
        assert Config.array("providers") == ["local"]
        assert Config.all()["app"] == {
            "name": "Titanspan",
            "debug": False,
        }
        assert Config.get_many(["app.name", "app.debug"]) == {
            "app.name": "Titanspan",
            "app.debug": False,
        }
        assert Config.get_many(["app.name"]) == {"app.name": "Titanspan"}
        assert Config.get({"app.missing": "fallback"}) == {
            "app.missing": "fallback",
        }
        assert Config.get(("app.name", "app.missing"), "fallback") == {
            "app.name": "Titanspan",
            "app.missing": "fallback",
        }
        assert Config.get_many({"app.missing": lambda: "lazy-fallback"}) == {
            "app.missing": "lazy-fallback"
        }
        Config.set("app.debug", True)
        Config.prepend("middleware", "authorization")
        Config.push("middleware", "logging")
        assert repository.get("middleware") == [
            "authorization",
            "auth",
            "logging",
        ]
        assert config() is repository
        assert config("app.name") == "Titanspan"
        config({"app.debug": True})
        assert Config.boolean("app.debug") is True


def test_config_override_is_restored_after_exceptions() -> None:
    """Restore the repository view even if a caller exits exceptionally.

    Returns:
        None.
    """
    application = Application()
    repository = Repository({"app": {"debug": False}})

    def fail_inside_override() -> None:
        """Raise after observing the temporary configuration value.

        The helper lets ``pytest.raises`` observe failure outside the
        ContextVar override, verifying its ``finally`` restoration path.
        """
        with Config.override({"app.debug": True}):
            assert Config.boolean("app.debug") is True
            raise RuntimeError(_EXPECTED_FAILURE)

    with (
        application.context(),
        Config.use(repository),
        pytest.raises(
            RuntimeError,
            match=_EXPECTED_FAILURE,
        ),
    ):
        fail_inside_override()

    with application.context(), Config.use(repository):
        assert Config.boolean("app.debug") is False


def test_facade_uses_alternate_capabilities_without_concrete_checks() -> None:
    """Delegate batch, typed, mutation, and override behavior by contract.

    The adapted repository has a distinct concrete identity but implements
    the same supported configuration capabilities.
    """
    application = Application()
    repository = _AlternateConfigRepository()
    base_contract: ConfigRepository = repository
    typed_contract: TypedConfigReader = repository
    scoped_contract: ScopedConfigOverrides = repository
    diagnostic_contract: ConfigDiagnostics = repository

    assert base_contract is repository
    assert typed_contract is repository
    assert scoped_contract is repository
    assert diagnostic_contract is repository

    with application.context(), Config.use(repository):
        assert Config.repository() is repository
        assert Config.string("app.name") == "Alternate"
        assert Config.get_many(["app.name"]) == {
            "app.name": "Alternate",
        }
        assert repository.batch_reads == 1

        with Config.override({"app.name": "scoped"}):
            Config.set("app.name", "mutated")
            assert Config.get("app.name") == "mutated"

        assert Config.get("app.name") == "Alternate"


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_config_overrides_are_isolated_between_concurrent_tasks() -> None:
    """Keep task-specific values separate during overlapping scopes.

    A synchronization event holds both tasks inside their override scopes at
    once, so this tests context-local state rather than sequential behavior.
    """
    application = Application()
    repository = Repository({"app": {"name": "base"}})
    both_started = anyio.Event()
    arrivals = 0
    observed: dict[str, object] = {}

    async def read_override(name: str) -> None:
        """Read one task-specific configuration value.

        Args:
            name: Expected value for the current task.
        """
        nonlocal arrivals
        with Config.override({"app.name": name}):
            arrivals += 1
            if arrivals == _EXPECTED_CONCURRENT_TASKS:
                both_started.set()
            await both_started.wait()
            observed[name] = Config.get("app.name")

    with application.context(), Config.use(repository):
        async with anyio.create_task_group() as group:
            group.start_soon(read_override, "task-a")
            group.start_soon(read_override, "task-b")

    assert observed == {"task-a": "task-a", "task-b": "task-b"}
    assert repository.get("app.name") == "base"


def test_config_facade_delegates_macro_lifecycle_to_repository() -> None:
    """Use the repository's shared macro registry through the facade.

    The facade keeps the repository as the single canonical macro owner and
    uses explicit invocation to preserve static discoverability.
    """
    application = Application()
    repository = Repository({"app": {"name": "Titanspan"}})

    class ApplicationMixin:
        """Provide one application-specific macro factory.

        The mixin exercises shared registration through the Config facade.
        """

        def application_name(self) -> Callable[[], object]:
            """Create a macro that returns the configured application name.

            Returns:
                A callback registered by the native facade.
            """

            def resolve_name() -> object:
                """Return the static name captured by this mixin.

                Returns:
                    A diagnostic application name.
                """
                return "Mixin"

            return resolve_name

    def configured_name(target: Repository) -> object:
        """Return the name stored in a repository instance.

        Args:
            target: Repository that receives the macro call.

        Returns:
            The configured application name.
        """
        return target.get("app.name")

    with application.context(), Config.use(repository):
        Config.flush_macros()
        try:
            Config.macro("configuredName", configured_name)
            assert Config.has_macro("configuredName")
            assert Config.call_macro("configuredName") == "Titanspan"
            Config.mixin(ApplicationMixin())
            assert Config.call_macro("application_name") == "Mixin"
        finally:
            Config.flush_macros()
