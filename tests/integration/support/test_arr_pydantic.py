"""Verify array conversion against the installed Pydantic model API.

The integration test exercises a real runtime dependency instead of a fake
``model_dump`` method.
"""

import pytest
from pydantic import BaseModel

from titanspan.support import Arr


class UserRecord(BaseModel):
    """Represent a Pydantic model accepted by ``Arr.from_``.

    Attributes:
        identifier: The stable user identifier.
        active: Whether the user is active.
    """

    identifier: int
    active: bool


@pytest.mark.integration
def test_from_converts_a_real_pydantic_model() -> None:
    """Use Pydantic's real model dump to create keyed array data.

    Returns:
        None.
    """
    result = Arr.from_(UserRecord(identifier=7, active=True))

    assert result == {"identifier": 7, "active": True}
