"""Expose native password hashing over Argon2-CFFI and PyCA Bcrypt.

The component owns configuration, service integration, safe errors, and
explicit async offloading while the dependencies own hashing mechanics.
"""

from titanspan.contracts.hashing import (
    Hasher,
    HashMetadata,
    HashVerification,
)
from titanspan.hashing.configuration import (
    Argon2Configuration,
    BcryptConfiguration,
    HashingConfiguration,
)
from titanspan.hashing.exceptions import (
    HashGenerationError,
    HashingConfigurationError,
    HashingError,
    HashInspectionError,
)
from titanspan.hashing.manager import HasherFactory, HashingManager
from titanspan.hashing.service_provider import HashingServiceProvider

__all__ = [
    "Argon2Configuration",
    "BcryptConfiguration",
    "HashGenerationError",
    "HashInspectionError",
    "HashMetadata",
    "HashVerification",
    "Hasher",
    "HasherFactory",
    "HashingConfiguration",
    "HashingConfigurationError",
    "HashingError",
    "HashingManager",
    "HashingServiceProvider",
]
