"""Describe Titanspan-owned dependency lifecycle scopes.

The names express lifecycle intent while adapting to supported graph levels.
"""

from enum import Enum


class Scope(Enum):
    """Name application and execution lifetimes for cached dependencies.

    Execution scope names adapt to a finite backend hierarchy. Request,
    connection, job, and workflow lifetimes share one level; node and agent
    lifetimes share the next level; tool and task lifetimes share the final
    level. Nesting is therefore supported only when it advances that order.
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
