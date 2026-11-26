"""Verify shared facade resolution and container-owned substitutions.

These tests cover the common behavior used by every component facade.
"""

import anyio
import pytest

from titanspan import Application
from titanspan.config import Repository
from titanspan.container import Scope, ScopeError
from titanspan.contracts.config import ConfigRepository
from titanspan.facades import Facade

pytestmark = pytest.mark.unit
_FACADE_FAILURE = "facade failure"


class _ProbeFacade(Facade[ConfigRepository]):
    """Resolve the probe through the shared Facade implementation.

    The class declares only the canonical service contract.
    """

    service_contract = ConfigRepository


def test_facade_use_restores_nested_replacements_after_failure() -> None:
    """Restore the canonical service after nested exceptional overrides.

    The shared facade must use the application's existing Container graph.
    """
    application = Application()
    original = application.make(ConfigRepository)
    first = Repository({"app": {"name": "first"}})
    second = Repository({"app": {"name": "second"}})

    def fail_in_nested_override() -> None:
        """Raise after checking nested replacement behavior.

        The outer test checks that both contexts restore the original graph.
        """
        with _ProbeFacade.use(first):
            assert _ProbeFacade.resolve_service() is first
            with _ProbeFacade.use(second):
                assert application.make(ConfigRepository) is second
                raise RuntimeError(_FACADE_FAILURE)

    with (
        application.context(),
        pytest.raises(
            RuntimeError,
            match=_FACADE_FAILURE,
        ),
    ):
        fail_in_nested_override()

    with application.context():
        assert application.make(ConfigRepository) is original
        assert _ProbeFacade.resolve_service() is original


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_facade_use_isolated_between_concurrent_contexts() -> None:
    """Keep service substitutions local to concurrent task contexts.

    Both replacements remain active at once without changing the base graph.
    """
    application = Application()
    original = application.make(ConfigRepository)
    replacements = {
        "first": Repository({"app": {"name": "first"}}),
        "second": Repository({"app": {"name": "second"}}),
    }
    both_entered = anyio.Event()
    arrivals = 0
    observed: dict[str, ConfigRepository] = {}

    async def resolve_replacement(name: str) -> None:
        """Resolve one task's facade service while scopes overlap.

        Args:
            name: Key selecting the task's unique replacement.
        """
        nonlocal arrivals
        replacement = replacements[name]
        with application.context(), _ProbeFacade.use(replacement):
            arrivals += 1
            if arrivals == len(replacements):
                both_entered.set()
            await both_entered.wait()
            observed[name] = _ProbeFacade.resolve_service()

    async with anyio.create_task_group() as group:
        for name in replacements:
            group.start_soon(resolve_replacement, name)

    assert observed == replacements
    with application.context():
        assert _ProbeFacade.resolve_service() is original


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_facade_use_restores_service_after_cancellation() -> None:
    """Restore the application graph when a task is cancelled in an override.

    The Container owns cleanup and context restoration for the substitution.
    """
    application = Application()
    original = application.make(ConfigRepository)
    replacement = Repository({"app": {"name": "replacement"}})
    entered = anyio.Event()

    async def wait_with_replacement() -> None:
        """Hold the replacement until its owning task group cancels it.

        The cancellation exercises the Container's restoration boundary.
        """
        with application.context(), _ProbeFacade.use(replacement):
            assert _ProbeFacade.resolve_service() is replacement
            entered.set()
            await anyio.sleep_forever()

    async with anyio.create_task_group() as group:
        group.start_soon(wait_with_replacement)
        await entered.wait()
        group.cancel_scope.cancel()

    with application.context():
        assert application.make(ConfigRepository) is original
        assert _ProbeFacade.resolve_service() is original


def test_facade_use_respects_active_container_scope_restrictions() -> None:
    """Reject service replacement after an execution scope begins.

    Facades delegate override safety to the application's Container.
    """
    application = Application()
    replacement = Repository({"app": {"name": "replacement"}})

    def enter_override() -> None:
        """Enter a replacement after the request scope has started.

        The active Container must reject this operation.
        """
        with _ProbeFacade.use(replacement):
            pass

    with (
        application.context(),
        application.container.scope(Scope.REQUEST),
        pytest.raises(ScopeError),
    ):
        enter_override()
