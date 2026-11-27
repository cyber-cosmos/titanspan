"""Define native job declarations and per-execution metadata.

Jobs contain serializable application data. The Container supplies handler
dependencies when the registered job runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from titanspan.contracts.queue.context import JobContext

if TYPE_CHECKING:
    from titanspan.contracts.queue.middleware import JobMiddlewareType

_POSITIVE_ATTEMPTS_ERROR = "A job must allow at least one attempt."
_INVALID_TIMEOUT_ERROR = "A job timeout must be a positive number."
_INVALID_BACKOFF_ERROR = "Job backoff values must be non-negative numbers."


class Job:
    """Mark a class as a trusted, serializable queue job.

    Subclasses must be dataclasses or Pydantic models and define a public
    ``handle`` method. Constructor values are message data, not services.
    """

    job_name: ClassVar[str | None] = None
    schema_version: ClassVar[int] = 1
    connection: ClassVar[str | None] = None
    queue: ClassVar[str | None] = None
    tries: ClassVar[int | None] = None
    timeout: ClassVar[float | None] = None
    backoff: ClassVar[int | float | tuple[int | float, ...]] = 0
    middleware: ClassVar[tuple[JobMiddlewareType, ...]] = ()


def validate_job_policy(job_type: type[Job]) -> None:
    """Reject invalid retry and timeout declarations before publication.

    Args:
        job_type: Registered job class whose policy is validated.

    Raises:
        TypeError: If middleware declarations have an invalid type.
        ValueError: If attempts, version, or timeout values are invalid.
    """
    tries = job_type.tries
    if tries is not None and (type(tries) is not int or tries < 1):
        raise ValueError(_POSITIVE_ATTEMPTS_ERROR)
    version = job_type.schema_version
    if type(version) is not int or version < 1:
        msg = "A job schema version must be a positive integer."
        raise ValueError(msg)
    middleware_types: object = getattr(job_type, "middleware", None)
    validate_middleware_declarations(middleware_types)
    timeout = job_type.timeout
    if timeout is not None and (
        type(timeout) not in (int, float) or timeout <= 0
    ):
        raise ValueError(_INVALID_TIMEOUT_ERROR)
    backoff = job_type.backoff
    if isinstance(backoff, tuple):
        valid_values = all(
            type(value) in (int, float) and value >= 0 for value in backoff
        )
    else:
        valid_values = type(backoff) in (int, float) and backoff >= 0
    if not valid_values:
        raise ValueError(_INVALID_BACKOFF_ERROR)


def validate_middleware_declarations(
    value: object,
) -> tuple[JobMiddlewareType, ...]:
    """Require a tuple of class-based middleware declarations.

    Args:
        value: Untrusted job or provider middleware declaration.

    Returns:
        The validated immutable class tuple.

    Raises:
        TypeError: If declarations are not a tuple of middleware classes.
    """
    if not isinstance(value, tuple):
        msg = "Job middleware must be declared as a class tuple."
        raise TypeError(msg)
    declarations = cast("tuple[object, ...]", value)
    for middleware_type in declarations:
        if not isinstance(middleware_type, type) or not callable(
            getattr(middleware_type, "handle", None)
        ):
            msg = "Each job middleware must declare a public handle method."
            raise TypeError(msg)
    return cast("tuple[JobMiddlewareType, ...]", value)


__all__ = ["Job", "JobContext", "validate_job_policy"]
