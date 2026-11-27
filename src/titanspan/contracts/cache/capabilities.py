"""Describe cache capabilities without exposing backend implementation.

Applications inspect these values before requesting optional operations.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CacheCapabilities:
    """Report the guarantees provided by one configured cache store.

    Attributes:
        atomic_add: Whether add-if-absent is one backend operation.
        atomic_increment: Whether counter mutation is atomic.
        atomic_pull: Whether retrieval and removal are atomic.
        tags: Whether grouped invalidation is supported.
        tag_invalidation_atomic: Whether one operation invalidates a tag group.
        scoped_clear: Whether a caller-supplied safe prefix can be deleted.
        locks: Whether owner-checked lease locks are supported.
        distributed_locks: Whether the backend coordinates across processes.
        lock_scoped_clear: Whether locks clear within this store namespace.
    """

    atomic_add: bool
    atomic_increment: bool
    atomic_pull: bool
    tags: bool
    tag_invalidation_atomic: bool
    scoped_clear: bool
    locks: bool
    distributed_locks: bool
    lock_scoped_clear: bool


__all__ = ["CacheCapabilities"]
