"""Define errors raised by invalid Pipeline configuration or execution.

Pipeline errors distinguish framework execution constraints from stage
exceptions, which propagate unchanged.
"""


class PipelineExecutionError(RuntimeError):
    """Report invalid pipeline configuration or a sync/async mismatch.

    Application exceptions raised by stages remain unwrapped.
    """


__all__ = ["PipelineExecutionError"]
