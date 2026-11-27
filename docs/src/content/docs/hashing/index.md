---
title: "Hashing"
---

<span id="hashing"></span>

Hashing provides configured password hashing through the application's
`Hasher` service. Titanspan owns configuration, service registration, safe
errors, and async access. Argon2-CFFI and PyCA Bcrypt perform hashing.

## Register the service

Foundation registers `HashingServiceProvider` by default. It reads the
`hashing` namespace from the canonical Config repository. Supply one explicit
provider only when you need custom hash drivers; it replaces the default.

```python
from titanspan import Application
from titanspan.facades import Hash

application = Application(
    config={"hashing": {"driver": "argon2id"}},
)

with application.context():
    hashed_password = Hash.make("a user-supplied password")
    assert Hash.check("a user-supplied password", hashed_password)
```

The `Hash` facade and injected `Hasher` contract resolve the same
application-owned service.

## Select an algorithm

Argon2id is the default for new hashes. Hashing also verifies existing Bcrypt
hashes and upgrades them after successful verification.

```python
from titanspan import Application

application = Application(
    config={
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
    },
)
```

Argon2id generation uses the configured work factors. Verification rejects
encoded hashes that exceed `hashing.verification_limits` before calling the
cryptographic backend. Bcrypt creation accepts the `2a` and `2b` prefixes;
verification also accepts compatible existing Bcrypt prefixes.

The default limits accept Argon2id hashes up to 256 MiB, six iterations, and
eight lanes. They accept Bcrypt costs up to 16. Encoded hashes are limited to
2,048 characters, and passwords are limited to 1 MiB. The policy also bounds
Argon2 digest and salt lengths. Applications can set a lower password-byte
limit. Work-factor limits cannot be lower than the generation defaults.
Hard ceilings reject excessive configuration.

To create new Bcrypt hashes, select `"bcrypt"` as the driver. The manager still
verifies Argon2 hashes so applications can upgrade them after a successful
check.

## Verify and upgrade

`check` returns `False` for malformed hashes and unsupported algorithms.
`verify_and_rehash` also fails closed and returns a replacement only after a
successful check.

```python
from titanspan.facades import Hash

stored_hash = Hash.make("a user-supplied password")
result = Hash.verify_and_rehash(
    "a user-supplied password",
    stored_hash,
)
if result.verified and result.replacement_hash is not None:
    updated_hash = result.replacement_hash
```

Persist `updated_hash` with the owning account record. Hashing does not own
password records, Authentication, or database access.

`Hash.needs_rehash` checks for a different algorithm or work factors below the
configured settings. `Hash.inspect` returns available algorithm and parameter
metadata, or `None` for an unrecognized encoding. `HashVerification` exposes
the replacement hash for persistence but omits it from its ordinary
representation.

## Use async methods

Synchronous methods perform blocking password work. Use their explicit async
counterparts from async handlers. They run through AnyIO's bounded worker
thread mechanism, so password work does not block the event loop.

```python
from titanspan.facades import Hash

async def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    """Verify a password without blocking the event loop.

    Args:
        password: Candidate password value.
        stored_hash: Encoded hash stored by the owning application.

    Returns:
        Whether the candidate matches.
    """
    result = await Hash.verify_and_rehash_async(password, stored_hash)
    return result.verified
```

Worker calls finish before pending cancellation is delivered. The hashing
backend cannot safely stop an in-progress operation. The built-in driver
limits hashing work to two operations per application by default. Set
`hashing.execution.max_concurrent_operations` from one to eight to change this
limit. Synchronous and asynchronous methods share the same application limit.
Async methods also use AnyIO's worker pool, which has a process-wide limit.
Custom hash drivers must define their own work policy.

## Handle errors safely

`make` raises `HashGenerationError` when the selected backend cannot process a
password. For example, Bcrypt rejects values longer than its supported byte
limit. Hashing never truncates password text or includes the input in its
native error message.

Use only `Hash.check` or `Hash.verify_and_rehash` to verify hashes. Do not
compare encoded values directly. The selected backend generates random salts
and encodes algorithm parameters. See the
[Argon2-CFFI API](https://argon2-cffi.readthedocs.io/en/stable/api.html) and
[PyCA Bcrypt documentation](https://github.com/pyca/bcrypt).

See the [Hashing specification](/framework/specifications/hashing/) for exact
configuration, contract, error, and lifecycle behavior.
