"""Name application and execution lifetimes for shared dependencies.

Scope values express native lifecycle intent independently of a resolver.
Concrete engines may map multiple values onto the same supported level.
"""

from enum import Enum


class Scope(Enum):
    """Name application and execution lifetimes for cached dependencies.

    Execution scope names adapt to a finite graph hierarchy. Request,
    connection, job, and workflow lifetimes share one level; node and agent
    lifetimes share the next; tool and task lifetimes share the final level.
    Nesting is therefore valid only when it advances that order.
    """

    APPLICATION = "application"
    REQUEST = "request"
    CONNECTION = "connection"
    JOB = "job"
    WORKFLOW = "workflow"
    NODE = "node"
    AGENT = "agent"
    TOOL = "tool"
    TASK = "task"


__all__ = ["Scope"]
