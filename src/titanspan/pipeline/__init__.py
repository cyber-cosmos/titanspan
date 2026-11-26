"""Expose ordered synchronous and asynchronous processing pipelines.

The package coordinates stages without owning a scheduler or task runtime.
"""

from titanspan.pipeline.exceptions import PipelineExecutionError
from titanspan.pipeline.helpers import pipeline
from titanspan.pipeline.pipeline import (
    ContinuationStage,
    Pipeline,
    StageMethod,
)

__all__ = [
    "ContinuationStage",
    "Pipeline",
    "PipelineExecutionError",
    "StageMethod",
    "pipeline",
]
