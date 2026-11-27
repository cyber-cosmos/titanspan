---
title: "Hashing component specification"
---

<span id="hashing-component-specification"></span>

Hashing provides an application-owned password hashing service over
`argon2-cffi` and `bcrypt`. The dependencies perform algorithm work. Titanspan
owns the contract, configuration, driver selection, facade, safe failures,
and async boundary.

## Application integration

`HashingServiceProvider` registers one `HashingManager` singleton through the
application's canonical Container. It resolves settings from `ConfigRepository`
and binds the selected service under the `Hasher` contract. The `Hash` facade
uses that same contract.

Foundation registers the provider by default. An explicit
`HashingServiceProvider` replaces it when an application supplies custom
drivers. Hashing owns no global manager and no password storage.

## Configuration

Settings live under `hashing`:

```python
{
    "hashing": {
        "driver": "argon2id",
        "argon2id": {
            "time_cost": 3,
            "memory_cost": 65_536,
            "parallelism": 4,
            "hash_length": 32,
            "salt_length": 16,
        },
        "bcrypt": {"rounds": 12, "prefix": "2b"},
        "execution": {"max_concurrent_operations": 2},
    },
}
```

The defaults use Argon2id with 65,536 KiB of memory, three iterations, and
four lanes. Bcrypt defaults to cost 12. Generated work factors cannot exceed
the configured verification limits. A driver must be `argon2id`, `bcrypt`, or
a name registered with `HashingServiceProvider(drivers=...)`.

`verification_limits` bounds encoded hash inspection before the cryptographic
backend runs. Defaults allow Argon2id hashes up to 256 MiB, six iterations,
eight lanes, and 128-byte digest and salt fields. Bcrypt verification is
limited to cost 16. Encoded hashes are limited to 2,048 characters and
password inputs to 1 MiB. Hard ceilings prevent settings from exceeding
these operational bounds. Verification limits for generated work factors
cannot be lower than the generation defaults. Applications may lower the
password-byte limit.

```python
{
    "hashing": {
        "verification_limits": {
            "max_argon2_memory_cost_kib": 262_144,
            "max_argon2_time_cost": 6,
            "max_argon2_parallelism": 8,
            "max_argon2_hash_length": 128,
            "max_argon2_salt_length": 128,
            "max_bcrypt_rounds": 16,
            "max_encoded_hash_length": 2048,
            "max_password_bytes": 1_048_576,
        },
    },
}
```

Custom driver factories receive `HashingConfiguration` and return a native
`Hasher`. They are trusted application code. Register them before the provider
builds its manager.

## Hash operations

`Hasher.make` returns an encoded hash using a dependency-generated salt.
`Hasher.check` supports Argon2 and Bcrypt hashes through their direct backend
APIs and returns `False` for malformed or unsupported encodings. It does not
expose backend exceptions or hash contents.

`Hasher.inspect` returns immutable `HashMetadata`, including algorithm and
supported work-factor fields. It returns `None` when the encoding is unknown or
malformed. `Hasher.needs_rehash` raises `HashInspectionError` for those inputs;
otherwise, it reports a different algorithm or work factors below policy.

`Hasher.verify_and_rehash` verifies through the direct backend APIs and creates
a replacement when the algorithm changed or work factors fall below policy.
An upgrade preserves any stronger existing Argon2 work factors. The caller
must persist the replacement. Failed verification never includes one. The
replacement hash is excluded from ordinary `HashVerification` representations
but remains explicitly available to callers.

## Async operations and cancellation

`make_async`, `check_async`, and `verify_and_rehash_async` use an
application-owned AnyIO capacity limiter before entering workers. The built-in
driver also uses one shared limit for synchronous and asynchronous operations.
It defaults to two active operations and accepts values from one through eight
at `hashing.execution.max_concurrent_operations`. Async callers wait for this
component limit without occupying general-purpose worker threads. Custom
drivers own their work limits. Neither selected backend provides native async
password hashing.

The worker is not abandoned if its caller is cancelled. Hashing completes in
the worker, then a cancellation checkpoint propagates pending cancellation to
the async caller. Synchronous methods remain available for non-async callers.

## Error and security behavior

- `HashGenerationError` omits password text and backend error details.
- Malformed or unknown hashes make `check` return `False`.
- Malformed or unknown hashes make `inspect` return `None`.
- `needs_rehash` raises `HashInspectionError` for malformed or unknown hashes.
- Bcrypt inputs beyond the backend's supported byte length fail safely.
- Password values are neither trimmed nor truncated.
- Excessive encoded work factors are rejected before verification.
- `HashVerification.replacement_hash` is omitted from `repr` output.
- Hashing creates no salts or cryptographic algorithms itself.
- No passwords or hashes are logged or retained by the manager.

`argon2-cffi` supplies the supported Argon2 parser, verifier, and rehash
inspection APIs. `bcrypt` supplies salt generation, hashing, and verification.
The adapter validates encoded metadata and normalizes backend errors.

## Ownership limits

Hashing is usable without Authentication. Authentication may use `Hasher` for
credential checks and rehashes in a later component milestone. Password
records, database persistence, encryption, sessions, and key management belong
to their owning components.

Foundation registers Hashing by default. An explicit provider replaces the
default when an application selects custom drivers.
