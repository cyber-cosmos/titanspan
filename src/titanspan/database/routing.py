"""Bind typed route parameters through native ORM queries.

Routing owns matching and dispatch; this adapter resolves one trusted model
type through its active application Database service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from titanspan.database.model import Model

if TYPE_CHECKING:
    from titanspan.routing import Router

_INVALID_ROUTE_KEY_ERROR = "Route key must name a mapped model column."


def bind_model[ModelT: Model](
    router: Router,
    model: type[ModelT],
    *,
    parameter: str,
    route_key: str | None = None,
) -> None:
    """Resolve a route parameter to one model through the active Database.

    Bindings use the application's asynchronous ORM path, preserve model
    scopes, and return ``None`` for Routing's native not-found response.

    Args:
        router: Application Router that owns path binding callbacks.
        model: Trusted mapped model class resolved for this parameter.
        parameter: Path parameter name registered on the Router.
        route_key: Mapped column name, defaulting to the model convention.

    Raises:
        ValueError: If the selected route key is not a mapped column.
    """
    key = model.route_key_name if route_key is None else route_key
    if not key.isidentifier() or model.__table__.columns.get(key) is None:
        raise ValueError(_INVALID_ROUTE_KEY_ERROR)

    async def resolve(value: str) -> ModelT | None:
        """Load one visible model by its configured route value.

        Args:
            value: Untrusted path value bound as a query parameter.

        Returns:
            The matching model or ``None`` for Routing's 404 handling.
        """
        return await model.query().where(key, value).first_async()

    router.bind(parameter, resolve)


__all__ = ["bind_model"]
