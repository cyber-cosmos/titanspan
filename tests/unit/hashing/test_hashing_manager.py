"""Verify password hashing delegates to safe configured drivers.

These tests exercise real hashing backends through the native service.
"""

import threading
from typing import cast
from unittest.mock import MagicMock

import anyio
import bcrypt
import pytest
from argon2 import PasswordHasher, Type
from argon2.exceptions import HashingError as Argon2HashingError

from titanspan.contracts.hashing import Hasher
from titanspan.hashing import (
    Argon2Configuration,
    BcryptConfiguration,
    HashingConfiguration,
    HashingManager,
)
from titanspan.hashing.exceptions import (
    HashGenerationError,
    HashingConfigurationError,
    HashInspectionError,
)

pytestmark = pytest.mark.unit
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65_536
_CUSTOM_ARGON2_MEMORY_KIB = 65_537
_BCRYPT_ROUNDS = 12
_WORKER_START_TIMEOUT = 5.0
_PRIVATE_FACTORY_ERROR = "private factory details"
_PRIVATE_ENCODING_ERROR = "private encoding detail"


def test_argon2id_hashes_verify_and_report_parameters() -> None:
    """Create a salted Argon2id hash and inspect its configured costs.

    The dependency owns the encoded format and generated salt.
    """
    configuration = HashingConfiguration()
    hasher = HashingManager(configuration).hasher()

    hashed = hasher.make("correct horse battery staple")
    metadata = hasher.inspect(hashed)

    assert hashed.startswith("$argon2id$")
    assert hasher.check("correct horse battery staple", hashed)
    assert PasswordHasher().verify(
        hashed,
        "correct horse battery staple",
    )
    assert not hasher.check("incorrect", hashed)
    assert metadata is not None
    assert metadata.algorithm == "argon2id"
    assert metadata.parameters["time_cost"] == _ARGON2_TIME_COST
    assert metadata.parameters["memory_cost_kib"] == _ARGON2_MEMORY_COST
    assert not hasher.needs_rehash(hashed)


def test_bcrypt_driver_generates_hashes_with_configured_cost() -> None:
    """Select Bcrypt by configuration and expose its work factor.

    The encoded result must verify through the selected backend.
    """
    hasher = HashingManager(
        HashingConfiguration(driver="bcrypt"),
    ).hasher()

    hashed = hasher.make("correct horse battery staple")
    metadata = hasher.inspect(hashed)

    assert hasher.algorithm == "bcrypt"
    assert hasher.check("correct horse battery staple", hashed)
    assert bcrypt.checkpw(
        b"correct horse battery staple",
        hashed.encode("ascii"),
    )
    assert metadata is not None
    assert metadata.algorithm == "bcrypt"
    assert metadata.parameters["rounds"] == _BCRYPT_ROUNDS
    assert metadata.parameters["prefix"] == "2b"


def test_bcrypt_hashes_upgrade_to_the_configured_argon2id_driver() -> None:
    """Verify existing Bcrypt hashes and return a replacement when needed.

    The replacement uses the configured default algorithm.
    """
    legacy = (
        bcrypt.hashpw(
            b"legacy password",
            bcrypt.gensalt(),
        )
        .decode("ascii")
        .replace("$2b$", "$2y$", 1)
    )
    hasher = HashingManager(HashingConfiguration()).hasher()

    result = hasher.verify_and_rehash("legacy password", legacy)

    assert result.verified
    assert result.replacement_hash is not None
    assert result.replacement_hash.startswith("$argon2id$")
    assert hasher.check("legacy password", result.replacement_hash)
    assert hasher.needs_rehash(legacy)


@pytest.mark.parametrize(
    "encoded",
    [
        "$argon2id$broken",
        "$argon2id$v=x$m=65536,t=3,p=4$salt$hash",
        "$argon2id$v=21$m=65536,t=3,p=4$salt$hash",
        "$argon2id$v=19$m=65536,t=3,p=4,m=8$salt$hash",
        "$argon2id$v=19$m=1,t=3,p=4$salt$hash",
        "$argon2id$v=19$m=65536,t=3$salt$hash",
        "$argon2id$v=19$m=65536,t=3,p=4,orphan$salt$hash",
    ],
)
def test_inspect_rejects_malformed_argon2_metadata(
    encoded: str,
) -> None:
    """Reject malformed Argon2 fields with the backend's public parser.

    Invalid parameter strings do not become inspection metadata.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()

    assert hasher.inspect(encoded) is None


@pytest.mark.parametrize("encoded", ["$2b$12", "$2b$rounds$hash"])
def test_inspect_rejects_malformed_bcrypt_metadata(
    encoded: str,
) -> None:
    """Reject malformed Bcrypt encodings before backend verification.

    Only complete encodings with supported costs are inspected.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()

    assert hasher.inspect(encoded) is None


def test_custom_argon2_parameters_are_used_for_new_hashes() -> None:
    """Apply configured Argon2 work factors through the backend API.

    The resulting metadata reflects the application's raised memory cost.
    """
    configuration = HashingConfiguration(
        argon2id=Argon2Configuration(
            memory_cost=_CUSTOM_ARGON2_MEMORY_KIB,
        ),
    )
    hasher = HashingManager(configuration).hasher()

    hashed = hasher.make("configured Argon2 password")
    metadata = hasher.inspect(hashed)

    assert metadata is not None
    assert metadata.parameters["memory_cost_kib"] == _CUSTOM_ARGON2_MEMORY_KIB


def test_argon2_upgrade_preserves_stronger_existing_costs() -> None:
    """Avoid lowering one cost while upgrading another configured factor.

    Replacement work factors must be at least as strong as stored values.
    """
    candidate = "mixed Argon2 work factors"
    existing_hasher = PasswordHasher(
        time_cost=_ARGON2_TIME_COST + 1,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )
    stored = existing_hasher.hash(candidate)
    hasher = HashingManager(
        HashingConfiguration(
            argon2id=Argon2Configuration(
                memory_cost=_ARGON2_MEMORY_COST + 1,
            ),
        ),
    ).hasher()

    result = hasher.verify_and_rehash(candidate, stored)

    assert result.verified
    assert result.replacement_hash is not None
    metadata = hasher.inspect(result.replacement_hash)
    assert metadata is not None
    assert metadata.parameters["time_cost"] == _ARGON2_TIME_COST + 1
    assert metadata.parameters["memory_cost_kib"] == _ARGON2_MEMORY_COST + 1


def test_stronger_bcrypt_hash_does_not_require_a_downgrade() -> None:
    """Keep hashes with higher Bcrypt work factors unchanged.

    Rehashing must not replace a stronger stored hash with a lower cost.
    """
    candidate = "stronger Bcrypt hash"
    stored = bcrypt.hashpw(
        candidate.encode("utf-8"),
        bcrypt.gensalt(rounds=_BCRYPT_ROUNDS + 1),
    ).decode("ascii")
    hasher = HashingManager(
        HashingConfiguration(driver="bcrypt"),
    ).hasher()

    result = hasher.verify_and_rehash(candidate, stored)

    assert result.verified
    assert result.replacement_hash is None


def test_custom_bcrypt_prefix_is_used_for_new_hashes() -> None:
    """Use the configured compatible prefix for new Bcrypt hashes.

    Existing compatible prefixes remain available to its verifier.
    """
    hasher = HashingManager(
        HashingConfiguration(
            driver="bcrypt",
            bcrypt=BcryptConfiguration(prefix="2a"),
        ),
    ).hasher()

    hashed = hasher.make("configured Bcrypt password")
    metadata = hasher.inspect(hashed)

    assert metadata is not None
    assert metadata.parameters["prefix"] == "2a"


def test_manager_accepts_a_custom_hasher_factory() -> None:
    """Select an application-provided hasher under its configured name.

    Custom code extends the driver selection without adding a registry.
    """
    custom_hasher = MagicMock(spec=Hasher)
    custom_hasher.algorithm = "custom"

    def create_custom_hasher(
        configuration: HashingConfiguration,
    ) -> Hasher:
        """Return the test service registered for one custom driver.

        The factory receives the validated native configuration.
        """
        _ = configuration
        return cast("Hasher", custom_hasher)

    manager = HashingManager(
        HashingConfiguration(driver="custom"),
        drivers={"custom": create_custom_hasher},
    )

    assert manager.driver_names == ("argon2id", "bcrypt", "custom")
    assert manager.default_driver == "custom"
    assert manager.hasher() is custom_hasher


def test_manager_rejects_unknown_or_conflicting_drivers() -> None:
    """Reject unavailable drivers and duplicate built-in names clearly.

    Invalid registrations fail before an application service is used.
    """
    with pytest.raises(HashingConfigurationError):
        HashingManager(HashingConfiguration(driver="missing"))
    with pytest.raises(HashingConfigurationError):
        HashingManager(
            drivers={
                "bcrypt": lambda configuration: HashingManager(
                    configuration,
                ).hasher()
            },
        )


def test_manager_normalizes_custom_factory_failures() -> None:
    """Avoid exposing custom driver factory diagnostics to callers.

    Registration errors use one safe configuration exception.
    """

    def create_hasher(configuration: HashingConfiguration) -> Hasher:
        """Raise a private factory failure for error-boundary coverage.

        Args:
            configuration: Validated settings supplied to the factory.
        """
        _ = configuration
        raise RuntimeError(_PRIVATE_FACTORY_ERROR)

    with pytest.raises(HashingConfigurationError) as captured:
        HashingManager(
            HashingConfiguration(driver="custom"),
            drivers={"custom": create_hasher},
        )

    assert _PRIVATE_FACTORY_ERROR not in str(captured.value)


def test_manager_rejects_custom_factory_algorithm_mismatch() -> None:
    """Require a custom driver to identify itself with its registered name.

    The manager must not advertise another algorithm under a custom key.
    """
    custom_hasher = MagicMock(spec=Hasher)
    custom_hasher.algorithm = "another"

    def create_hasher(configuration: HashingConfiguration) -> Hasher:
        """Return a mismatched test service.

        Args:
            configuration: Validated settings supplied to the factory.
        """
        _ = configuration
        return cast("Hasher", custom_hasher)

    with pytest.raises(HashingConfigurationError):
        HashingManager(
            HashingConfiguration(driver="custom"),
            drivers={"custom": create_hasher},
        )


def test_wrong_password_never_returns_a_replacement_hash() -> None:
    """Keep replacement output absent when verification does not succeed.

    Failed credential checks cannot trigger an upgrade.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    hashed = hasher.make("expected password")

    result = hasher.verify_and_rehash("wrong password", hashed)

    assert not result.verified
    assert result.replacement_hash is None


def test_bcrypt_rejects_overlong_passwords_without_truncation() -> None:
    """Fail safely when Bcrypt cannot represent the complete password.

    Neither hashing nor verification truncates the candidate.
    """
    hasher = HashingManager(
        HashingConfiguration(driver="bcrypt"),
    ).hasher()
    overlong_value = "x" * 73
    stored = hasher.make("x" * 72)
    unicode_prefix = "🦕" * 18
    unicode_overlong = f"{unicode_prefix}🦕"
    unicode_stored = hasher.make(unicode_prefix)

    with pytest.raises(HashGenerationError) as captured:
        hasher.make(overlong_value)

    assert overlong_value not in str(captured.value)
    assert not hasher.check(overlong_value, stored)
    assert not hasher.check(unicode_overlong, unicode_stored)


@pytest.mark.anyio
async def test_async_hashing_runs_in_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep expensive synchronous work off the active event-loop thread.

    The async contract delegates work through AnyIO's worker pool.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    event_thread = threading.get_ident()
    worker_thread: int | None = None

    def generate(password: str) -> str:
        """Record the execution thread without doing password work.

        This stub isolates the scheduling boundary from hashing cost.
        """
        nonlocal worker_thread
        _ = password
        worker_thread = threading.get_ident()
        return "encoded-test-hash"

    monkeypatch.setattr(hasher, "make", generate)

    assert await hasher.make_async("not logged") == "encoded-test-hash"
    assert worker_thread is not None
    assert worker_thread != event_thread


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_async_hashing_finishes_worker_before_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Let uninterruptible work finish before propagating cancellation.

    The worker must not outlive the awaited operation.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    started = threading.Event()
    release = threading.Event()
    cancellation_observed = anyio.Event()

    def generate(password: str) -> str:
        """Hold worker completion until the test releases its event.

        The event gives cancellation cleanup a deterministic ordering.
        """
        _ = password
        started.set()
        release.wait(timeout=_WORKER_START_TIMEOUT)
        return "encoded-test-hash"

    async def request_hash() -> None:
        """Observe cancellation only after the worker returns.

        The event records delivery to the awaiting task.
        """
        try:
            await hasher.make_async("not logged")
        except anyio.get_cancelled_exc_class():
            cancellation_observed.set()

    monkeypatch.setattr(hasher, "make", generate)
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(request_hash)
        try:
            worker_started = await anyio.to_thread.run_sync(
                started.wait,
                abandon_on_cancel=False,
            )
            assert worker_started
            tasks.cancel_scope.cancel()
        finally:
            release.set()

    assert cancellation_observed.is_set()


def test_malformed_hashes_fail_closed_without_backend_details() -> None:
    """Treat malformed encodings as invalid and omit their text from errors.

    Unsupported inputs do not escape dependency-specific diagnostics.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    malformed = "$argon2id$malformed-private-value"

    assert not hasher.check("password", malformed)
    assert hasher.inspect(malformed) is None
    result = hasher.verify_and_rehash("password", malformed)
    assert not result.verified
    assert result.replacement_hash is None
    with pytest.raises(HashInspectionError) as captured:
        hasher.needs_rehash(malformed)
    assert malformed not in str(captured.value)


def test_runtime_non_string_inputs_fail_safely() -> None:
    """Reject incompatible runtime values without exposing their contents.

    Typed callers use strings, while adapters still fail closed defensively.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    invalid_value = cast("str", object())

    with pytest.raises(HashGenerationError):
        hasher.make(invalid_value)
    assert not hasher.check(invalid_value, "not-a-hash")
    assert not hasher.check("password", invalid_value)
    assert hasher.inspect(invalid_value) is None
    result = hasher.verify_and_rehash(invalid_value, "not-a-hash")
    assert not result.verified


def test_backend_inspection_failure_uses_safe_native_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalize a backend parsing failure during rehash inspection.

    The public error must not reveal encoded data or backend internals.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    hashed = hasher.make("inspection failure password")

    def reject_hash(self: PasswordHasher, encoded: str) -> bool:
        """Simulate an unsupported recognized encoding.

        Args:
            self: Backend hasher whose inspection is replaced.
            encoded: Encoded hash passed by the adapter.
        """
        _ = self, encoded
        raise ValueError(_PRIVATE_ENCODING_ERROR)

    monkeypatch.setattr(PasswordHasher, "check_needs_rehash", reject_hash)

    with pytest.raises(HashInspectionError) as captured:
        hasher.needs_rehash(hashed)

    assert _PRIVATE_ENCODING_ERROR not in str(captured.value)


def test_rehash_generation_failure_uses_safe_native_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalize backend failure while upgrading a verified legacy hash.

    The candidate verifies before the backend requests a replacement hash.
    """
    legacy = bcrypt.hashpw(
        b"legacy password",
        bcrypt.gensalt(),
    ).decode("ascii")
    hasher = HashingManager(HashingConfiguration()).hasher()

    def reject_generation(
        self: PasswordHasher,
        password: str,
        *,
        salt: bytes | None = None,
    ) -> str:
        """Simulate a replacement hash generation failure.

        Args:
            self: Backend hasher used for replacement hashes.
            password: Verified candidate text.
            salt: Optional salt accepted by the backend's public API.
        """
        _ = self, password, salt
        raise Argon2HashingError(_PRIVATE_ENCODING_ERROR)

    monkeypatch.setattr(PasswordHasher, "hash", reject_generation)

    with pytest.raises(HashGenerationError) as captured:
        hasher.verify_and_rehash("legacy password", legacy)

    assert "legacy password" not in str(captured.value)
