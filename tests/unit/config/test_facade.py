"""Verify context-aware Config facade and Support helper access.

The facade and helper must resolve the same explicitly bound repository and
must restore scoped overrides after failures.
"""

from collections.abc import Callable

import anyio
import pytest

from titanspan.config import ConfigContextError, Repository
from titanspan.facades import Config
from titanspan.support import config

pytestmark = pytest.mark.unit
_EXPECTED_FAILURE = "failure"
_EXPECTED_CONCURRENT_TASKS = 2
_WORKER_COUNT = 4
_TEMPERATURE = 0.25


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
    repository = Repository(
        {
            "app": {"name": "Titanspan", "debug": False},
            "ai": {"temperature": _TEMPERATURE},
            "queue": {"workers": _WORKER_COUNT},
            "providers": ["local"],
            "middleware": ["auth"],
        }
    )

    with Config.use(repository):
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
        assert Config.getMany(["app.name", "app.debug"]) == {
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
        Config.use(repository),
        pytest.raises(
            RuntimeError,
            match=_EXPECTED_FAILURE,
        ),
    ):
        fail_inside_override()

    with Config.use(repository):
        assert Config.boolean("app.debug") is False


def test_typed_facade_operations_reject_other_contract_implementations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep native typed helpers and overrides tied to Repository semantics.

    Args:
        monkeypatch: Fixture replacing repository access with another
            structural implementation.

    Returns:
        None.
    """

    def external_repository(_cls: type[Config]) -> object:
        """Return a structural contract implementation without extensions.

        Args:
            _cls: Config facade class receiving the class method call.

        Returns:
            An opaque object representing an alternate repository.
        """
        return object()

    monkeypatch.setattr(
        Config,
        "repository",
        classmethod(external_repository),
    )

    with pytest.raises(ConfigContextError, match="Typed access"):
        Config.string("app.name")

    def enter_unsupported_override() -> None:
        """Attempt the scoped extension on a structural repository.

        Returns:
            None if the context could be entered.
        """
        with Config.override({"app.debug": True}):
            pass

    with pytest.raises(ConfigContextError, match="Scoped overrides"):
        enter_unsupported_override()


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_config_overrides_are_isolated_between_concurrent_tasks() -> None:
    """Keep task-specific values separate during overlapping scopes.

    A synchronization event holds both tasks inside their override scopes at
    once, so this tests context-local state rather than sequential behavior.
    """
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

    with Config.use(repository):
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

    with Config.use(repository):
        Config.flush_macros()
        try:
            Config.macro("configuredName", configured_name)
            assert Config.hasMacro("configuredName")
            assert Config.call_macro("configuredName") == "Titanspan"
            Config.mixin(ApplicationMixin())
            assert Config.call_macro("application_name") == "Mixin"
        finally:
            Config.flushMacros()
