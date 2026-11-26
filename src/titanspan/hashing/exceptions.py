"""Define safe native errors for password hashing operations.

Error messages omit password values, encoded hashes, and backend details.
"""


class HashingError(Exception):
    """Represent a safe failure from the native Hashing component.

    Messages omit password values, encoded hashes, and backend details.
    """


class HashingConfigurationError(HashingError):
    """Represent invalid hashing configuration or driver registration.

    The exception does not echo the invalid configuration value.
    """


class HashGenerationError(HashingError):
    """Represent failure to generate a password hash.

    The message omits the password and algorithm-provider details.
    """


class HashInspectionError(HashingError):
    """Represent an unsupported or malformed encoded hash inspection.

    The message does not include the encoded value.
    """


__all__ = [
    "HashGenerationError",
    "HashInspectionError",
    "HashingConfigurationError",
    "HashingError",
]
