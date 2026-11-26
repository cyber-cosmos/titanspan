"""Expose eager and lazy collection APIs.

The component delegates iteration mechanics to native Python facilities.
"""

from titanspan.collections.collection import Collection, collect
from titanspan.collections.lazy_collection import LazyCollection, lazy

__all__ = ["Collection", "LazyCollection", "collect", "lazy"]
