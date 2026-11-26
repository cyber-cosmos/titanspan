"""Expose event recording and assertion tools for application tests.

Applications and test tools use the same event record type.
"""

from titanspan.events.testing.fake import EventFake, EventRecord

__all__ = ["EventFake", "EventRecord"]
