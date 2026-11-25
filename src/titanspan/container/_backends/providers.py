"""Adapt native framework registrations to the private graph engine.

Translate framework-owned registrations at the backend integration boundary.
"""

from collections.abc import Sequence
from typing import cast

from dishka import Provider, Scope

from titanspan.contracts.container import InstanceRegistration


def adapt_providers(providers: Sequence[object]) -> tuple[Provider, ...]:
    """Translate supported Titanspan providers at the backend boundary.

    Args:
        providers: Native framework registrations or advanced integration
            provider objects.

    Returns:
        Backend provider instances used only by private composition code.
    """
    return tuple(_adapt_provider(provider) for provider in providers)


def _adapt_provider(provider: object) -> Provider:
    """Convert one native registration or preserve an interop provider.

    Args:
        provider: Native configuration registration or advanced provider.

    Returns:
        The backend provider used to compose the dependency graph.
    """
    if not isinstance(provider, InstanceRegistration):
        return cast("Provider", provider)

    native_provider = Provider(scope=Scope.APP)

    def provide_instance() -> object:
        """Return the value contributed by a native registration.

        The backend owns this binding for the application lifetime.
        """
        return provider.value

    native_provider.provide(
        provide_instance,
        provides=provider.service,
        scope=Scope.APP,
        recursive=False,
    )
    return native_provider
