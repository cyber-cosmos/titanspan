"""Verify canonical contract identity and immutable result values.

The native Hashing package re-exports these exact shared contract objects.
"""

from types import MappingProxyType

import pytest

from titanspan.contracts import Hasher, HashMetadata, HashVerification
from titanspan.contracts.hashing import (
    Hasher as DomainHasher,
)
from titanspan.contracts.hashing import (
    HashMetadata as DomainHashMetadata,
)
from titanspan.contracts.hashing import (
    HashVerification as DomainHashVerification,
)
from titanspan.hashing import Hasher as ComponentHasher
from titanspan.hashing import HashMetadata as ComponentHashMetadata
from titanspan.hashing import HashVerification as ComponentHashVerification

pytestmark = pytest.mark.unit
_INITIAL_ROUNDS = 12
_CHANGED_ROUNDS = 13


def test_hashing_contract_exports_keep_one_canonical_identity() -> None:
    """Expose the domain contract from all native convenience packages.

    Re-exports must refer to the exact objects defined in the domain package.
    """
    assert HashMetadata is DomainHashMetadata is ComponentHashMetadata
    assert (
        HashVerification
        is DomainHashVerification
        is (ComponentHashVerification)
    )
    assert Hasher is DomainHasher is ComponentHasher


def test_hash_metadata_copies_and_freezes_parameter_values() -> None:
    """Keep later caller mutation from changing an inspection result.

    Consumers receive immutable values even when input mappings are mutable.
    """
    parameters: dict[str, int] = {"rounds": _INITIAL_ROUNDS}
    metadata = HashMetadata("bcrypt", parameters)

    parameters["rounds"] = _CHANGED_ROUNDS

    assert metadata.parameters["rounds"] == _INITIAL_ROUNDS
    assert isinstance(metadata.parameters, MappingProxyType)


def test_failed_verification_cannot_include_a_replacement_hash() -> None:
    """Enforce the rule that only verified passwords may trigger upgrades.

    The contract rejects contradictory result values during construction.
    """
    with pytest.raises(ValueError, match="failed verification"):
        HashVerification(
            verified=False,
            replacement_hash="opaque-test-hash",
        )


def test_replacement_hash_is_not_exposed_by_result_representation() -> None:
    """Keep a replacement credential out of ordinary debug output.

    Callers can still read the field explicitly when persistence is needed.
    """
    replacement = "replacement-hash-secret-marker"
    result = HashVerification(True, replacement)

    assert result.replacement_hash == replacement
    assert replacement not in repr(result)


def test_hash_metadata_requires_an_algorithm_identifier() -> None:
    """Reject metadata that cannot identify its encoded format.

    Consumers must be able to interpret an inspection result unambiguously.
    """
    with pytest.raises(ValueError, match="algorithm identifier"):
        HashMetadata(" ", {})
