"""Provide small native helpers for creating ordered Pipelines.

Helpers retain the stage builder's explicit input and output types.
"""

from titanspan.contracts.container import ServiceContainer
from titanspan.pipeline.pipeline import Pipeline


def pipeline[InputT](
    value: InputT,
    *,
    container: ServiceContainer | None = None,
) -> Pipeline[InputT, InputT]:
    """Create a value-preserving pipeline with an optional stage container.

    Args:
        value: Initial value supplied to the first stage.
        container: Optional application container for class stages.

    Returns:
        A builder ready to append ordered stages.
    """
    return Pipeline[InputT, InputT](container=container).send(value)


__all__ = ["pipeline"]
