"""Expose logging-specific fakes and assertions for application tests.

The fake records Titanspan-owned events and remains isolated to its manager.
"""

from titanspan.logging.testing.fake import FakeLog

__all__ = ["FakeLog"]
