"""Verify password hashing delegates to safe configured drivers.

These tests exercise real hashing backends through the native service.
"""

import base64
import threading
from typing import cast
from unittest.mock import MagicMock, patch

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
    HashVerificationLimits,
)
from titanspan.hashing._backends import _NativeHasher
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
_ONE_HASH_OPERATION = 1
_TWO_HASH_OPERATIONS = 2
_PRIVATE_FACTORY_ERROR = "private factory details"
_PRIVATE_ENCODING_ERROR = "private encoding detail"


class _ObservedBoundedSemaphore(threading.BoundedSemaphore):
    """Expose a deterministic signal when a second hashing call contends.

    The inherited semaphore still owns and enforces the execution limit.
    """

    def __init__(self, value: int) -> None:
        """Create a bounded gate and initialize waiter observations.

        Args:
            value: Maximum number of concurrent hashing operations.
        """
        super().__init__(value)
        self._attempt_lock = threading.Lock()
        self._attempts = 0
        self.second_waiter = threading.Event()

    def __enter__(
        self,
        blocking: bool = True,
        timeout: float | None = None,
    ) -> bool:
        """Observe semaphore entry before acquiring its bounded slot.

        Returns:
            Whether this call acquired the semaphore.
        """
        with self._attempt_lock:
            self._attempts += 1
            if self._attempts == _TWO_HASH_OPERATIONS:
                self.second_waiter.set()
        return super().acquire(blocking, timeout)

    @property
    def attempts(self) -> int:
        """Return the number of observed acquisitions.

        Tests inspect this after all worker calls complete.
        """
        with self._attempt_lock:
            return self._attempts

    _attempt_lock: threading.Lock
    _attempts: int
    second_waiter: threading.Event


@pytest.fixture
def observed_hashing_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_ObservedBoundedSemaphore]:
    """Record the real semaphores created by the built-in driver.

    The test retains the backend's synchronization behavior while observing
    entry and contention.
    """
    observed: list[_ObservedBoundedSemaphore] = []

    def create_limiter(value: int) -> _ObservedBoundedSemaphore:
        """Create and retain one observed bounded semaphore.

        Args:
            value: Maximum number of concurrent hashing operations.

        Returns:
            A real bounded semaphore with test observation hooks.
        """
        limiter = _ObservedBoundedSemaphore(value)
        observed.append(limiter)
        return limiter

    monkeypatch.setattr(
        "titanspan.hashing._backends.BoundedSemaphore",
        create_limiter,
    )
    return observed


class _HashingWorkProbe:
    """Coordinate two real entry points around a controlled hash call.

    Events expose contention without relying on worker scheduling delays.
    """

    _hasher: _NativeHasher
    first_started: threading.Event
    second_started: threading.Event
    release_first: threading.Event
    _active_lock: threading.Lock
    _active: int
    _peak_active: int
    results: list[str]
    release_results: list[bool]

    def __init__(self, hasher: _NativeHasher) -> None:
        """Create synchronization and result state for one hash test.

        Args:
            hasher: Built-in hasher created through HashingManager.
        """
        self._hasher = hasher
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release_first = threading.Event()
        self._active_lock = threading.Lock()
        self._active = 0
        self._peak_active = 0
        self.results: list[str] = []
        self.release_results: list[bool] = []

    def generate(self, candidate: str, backend: PasswordHasher) -> str:
        """Hold backend entry and record simultaneous operations.

        Args:
            candidate: Value identifying the current call.
            backend: Configured Argon2 backend, unused by the probe.

        Returns:
            A stable hash marker for the operation.
        """
        _ = backend
        with self._active_lock:
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)
        self.first_started.set()
        released = self.release_first.wait(_WORKER_START_TIMEOUT)
        self.release_results.append(released)
        with self._active_lock:
            self._active -= 1
        return f"test-hash:{candidate}"

    async def make_async(self) -> None:
        """Run an async hash call and retain its result.

        The built-in driver delegates it through AnyIO's worker pool.
        """
        self.results.append(await self._hasher.make_async("async"))

    async def make_sync(self) -> None:
        """Run a synchronous hash call through an AnyIO worker.

        Its independent limiter keeps the test observer from blocking it.
        """

        def resolve() -> str:
            """Signal worker entry before synchronous hashing starts.

            Returns:
                The hash result from the synchronous API.
            """
            self.second_started.set()
            return self._hasher.make("sync")

        result = await anyio.to_thread.run_sync(
            resolve,
            limiter=anyio.CapacityLimiter(_ONE_HASH_OPERATION),
            abandon_on_cancel=False,
        )
        self.results.append(result)

    @property
    def peak_active(self) -> int:
        """Return the largest number of simultaneous backend calls.

        The measurement covers entries after semaphore acquisition.
        """
        with self._active_lock:
            return self._peak_active


def _argon_hash_metadata(
    *,
    memory_cost: int = 65_536,
    time_cost: int = 3,
    parallelism: int = 4,
    salt_length: int = 16,
    hash_length: int = 32,
) -> str:
    """Build bounded synthetic PHC metadata without hashing a password.

    Args:
        memory_cost: Encoded Argon2 memory factor.
        time_cost: Encoded Argon2 iteration count.
        parallelism: Encoded Argon2 lane count.
        salt_length: Encoded salt size in bytes.
        hash_length: Encoded digest size in bytes.

    Returns:
        A syntactically valid metadata string for preflight tests.
    """
    salt = base64.b64encode(bytes(salt_length)).decode("ascii").rstrip("=")
    digest = base64.b64encode(bytes(hash_length)).decode("ascii").rstrip("=")
    return (
        f"$argon2id$v=19$m={memory_cost},t={time_cost},p={parallelism}"
        f"${salt}${digest}"
    )


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


@pytest.mark.parametrize(
    "parameters",
    [
        {"memory_cost": 262_145},
        {"time_cost": 7},
        {"parallelism": 9},
        {"hash_length": 129},
        {"salt_length": 129},
    ],
)
def test_argon2_verification_rejects_excessive_metadata_before_backend(
    parameters: dict[str, int],
) -> None:
    """Reject excessive Argon2 costs before the crypto backend runs.

    Inspection and verification share the application's operational policy.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    encoded = _argon_hash_metadata(**parameters)

    with patch.object(PasswordHasher, "verify", autospec=True) as verify:
        assert hasher.inspect(encoded) is None
        assert not hasher.check("candidate", encoded)

    verify.assert_not_called()


def test_bcrypt_verification_rejects_excessive_cost_before_backend() -> None:
    """Reject algorithm-valid Bcrypt costs above the operational maximum.

    Encoded metadata is inspected before the dependency performs key setup.
    """
    hasher = HashingManager(
        HashingConfiguration(driver="bcrypt"),
    ).hasher()
    encoded = f"$2b$17${'A' * 53}"

    with patch("titanspan.hashing._backends.bcrypt.checkpw") as checkpw:
        assert hasher.inspect(encoded) is None
        assert not hasher.check("candidate", encoded)

    checkpw.assert_not_called()


def test_hash_size_and_password_size_limits_fail_before_backend() -> None:
    """Bound encoded metadata and password input before verification.

    Applications can lower the input limit without changing hash defaults.
    """
    configuration = HashingConfiguration(
        verification_limits=HashVerificationLimits(max_password_bytes=8),
    )
    hasher = HashingManager(configuration).hasher()
    oversized_hash = "x" * (
        configuration.verification_limits.max_encoded_hash_length + 1
    )

    with patch("titanspan.hashing._backends.extract_parameters") as extract:
        assert hasher.inspect(oversized_hash) is None
        assert not hasher.check("candidate", oversized_hash)
        assert not hasher.check("password-too-long", "$argon2id$bad")

    extract.assert_not_called()
    with pytest.raises(HashGenerationError):
        hasher.make("password-too-long")


def test_hash_generation_limits_encoded_utf8_bytes() -> None:
    """Apply password limits to encoded bytes as well as characters.

    A short Unicode string can exceed a byte-based operational limit.
    """
    hasher = HashingManager(
        HashingConfiguration(
            verification_limits=HashVerificationLimits(max_password_bytes=2),
        ),
    ).hasher()

    with pytest.raises(HashGenerationError):
        hasher.make("🦕")
    existing_hash = HashingManager().hasher().make("password")
    assert not hasher.check("abc", existing_hash)


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


def test_hash_verification_rejects_invalid_unicode() -> None:
    """Return a failed verification for strings that cannot encode as UTF-8.

    Malformed Python strings must not escape from the hashing boundary.
    """
    hasher = HashingManager(HashingConfiguration()).hasher()
    hashed = hasher.make("ordinary password")

    assert not hasher.check("\ud800", hashed)


def test_argon2_rehash_uses_the_application_work_budget(
    monkeypatch: pytest.MonkeyPatch,
    observed_hashing_limits: list[_ObservedBoundedSemaphore],
) -> None:
    """Count verification and replacement hashing under one limiter.

    Rehashing uses the same application-owned budget as direct generation.
    """
    candidate = "rehash within the application budget"
    stored_hasher = PasswordHasher(
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )
    stored = stored_hasher.hash(candidate)
    hasher = HashingManager(
        HashingConfiguration(
            argon2id=Argon2Configuration(
                memory_cost=_CUSTOM_ARGON2_MEMORY_KIB,
            ),
        ),
    ).hasher()
    assert isinstance(hasher, _NativeHasher)
    assert len(observed_hashing_limits) == 1
    limiter = observed_hashing_limits[0]

    def generate_replacement(
        candidate: str,
        backend: PasswordHasher,
    ) -> str:
        """Return a marker after the replacement path acquires its gate.

        Args:
            candidate: Password selected for the replacement hash.
            backend: Configured backend, unused by this boundary test.

        Returns:
            A marker that identifies the replacement operation.
        """
        return f"replacement:{candidate}:{backend}"

    monkeypatch.setattr(
        "titanspan.hashing._backends._generate_argon2_hash",
        generate_replacement,
    )

    result = hasher.verify_and_rehash(candidate, stored)

    assert result.verified
    assert result.replacement_hash is not None
    assert limiter.attempts == _TWO_HASH_OPERATIONS


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
async def test_sync_and_async_hashing_share_application_work_budget(
    monkeypatch: pytest.MonkeyPatch,
    observed_hashing_limits: list[_ObservedBoundedSemaphore],
) -> None:
    """Limit simultaneous crypto work across sync and async entry points.

    Controlled threads verify that both paths use one application limiter.
    """
    hasher = HashingManager(
        HashingConfiguration(
            max_concurrent_operations=_ONE_HASH_OPERATION,
        ),
    ).hasher()
    assert isinstance(hasher, _NativeHasher)
    assert len(observed_hashing_limits) == 1
    limiter = observed_hashing_limits[0]
    probe = _HashingWorkProbe(hasher)
    monkeypatch.setattr(
        "titanspan.hashing._backends._generate_argon2_hash",
        probe.generate,
    )
    first_entered = False
    second_started = False
    second_waiting = False
    observer_limiter = anyio.CapacityLimiter(_ONE_HASH_OPERATION)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(probe.make_async)
            first_entered = await anyio.to_thread.run_sync(
                probe.first_started.wait,
                _WORKER_START_TIMEOUT,
                limiter=observer_limiter,
                abandon_on_cancel=False,
            )
            if first_entered:
                tasks.start_soon(probe.make_sync)
                second_started = await anyio.to_thread.run_sync(
                    probe.second_started.wait,
                    _WORKER_START_TIMEOUT,
                    limiter=observer_limiter,
                    abandon_on_cancel=False,
                )
                if second_started:
                    second_waiting = await anyio.to_thread.run_sync(
                        limiter.second_waiter.wait,
                        _WORKER_START_TIMEOUT,
                        limiter=observer_limiter,
                        abandon_on_cancel=False,
                    )
            probe.release_first.set()
    finally:
        probe.release_first.set()

    assert first_entered
    assert second_started
    assert second_waiting, limiter.attempts
    assert sorted(probe.results) == ["test-hash:async", "test-hash:sync"]
    assert probe.peak_active == _ONE_HASH_OPERATION
    assert all(probe.release_results)


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
