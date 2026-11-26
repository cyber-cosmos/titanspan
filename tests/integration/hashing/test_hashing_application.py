"""Verify Hashing uses the application Config and Container services.

The test sends an actual request through FastAPI and exercises the canonical
Hasher contract and Hash facade with the configured Bcrypt implementation.
"""

from http import HTTPStatus

import anyio
import pytest
from fastapi.testclient import TestClient

from titanspan.contracts.hashing import Hasher
from titanspan.facades import Hash
from titanspan.foundation import Application
from titanspan.hashing import HashingServiceProvider

pytestmark = [pytest.mark.integration, pytest.mark.architecture]


def test_hashing_uses_application_config_injection_and_facade() -> None:
    """Resolve the same configured hasher through injection and Hash.

    A real ASGI request observes the application-owned service graph.
    """
    application = Application(
        config={"hashing": {"driver": "bcrypt"}},
        service_providers=(HashingServiceProvider(),),
    )

    async def hash_password(hasher: Hasher) -> dict[str, object]:
        """Exercise asynchronous hashing and the context-bound facade.

        Args:
            hasher: Contract service injected from this application.

        Returns:
            Safe verification status without returning password material.
        """
        encoded = await Hash.make_async("framework integration password")
        verified = await Hash.check_async(
            "framework integration password",
            encoded,
        )
        upgraded = await Hash.verify_and_rehash_async(
            "framework integration password",
            encoded,
        )
        metadata = Hash.inspect(encoded)
        return {
            "same_service": Hash.resolve_service() is hasher,
            "algorithm": metadata.algorithm if metadata is not None else None,
            "driver": hasher.algorithm,
            "verified": verified and upgraded.verified,
            "replacement": upgraded.replacement_hash,
            "needs_rehash": Hash.needs_rehash(encoded),
        }

    def hash_password_synchronously(
        hasher: Hasher,
    ) -> dict[str, object]:
        """Exercise synchronous facade operations in a sync endpoint.

        Args:
            hasher: Contract service injected from this application.

        Returns:
            Safe verification status without returning password material.
        """
        encoded = Hash.make("synchronous integration credential")
        verified = Hash.check(
            "synchronous integration credential",
            encoded,
        )
        upgraded = Hash.verify_and_rehash(
            "synchronous integration credential",
            encoded,
        )
        return {
            "same_service": Hash.resolve_service() is hasher,
            "verified": verified and upgraded.verified,
            "replacement": upgraded.replacement_hash,
        }

    application.router.get("/hashing", hash_password)
    application.router.get("/hashing/sync", hash_password_synchronously)

    with TestClient(application.asgi) as client:
        response = client.get("/hashing")
        synchronous_response = client.get("/hashing/sync")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "same_service": True,
        "algorithm": "bcrypt",
        "driver": "bcrypt",
        "verified": True,
        "replacement": None,
        "needs_rehash": False,
    }
    assert synchronous_response.status_code == HTTPStatus.OK
    assert synchronous_response.json() == {
        "same_service": True,
        "verified": True,
        "replacement": None,
    }


@pytest.mark.concurrency
@pytest.mark.anyio
async def test_concurrent_application_contexts_keep_hashers_isolated() -> None:
    """Keep each concurrent facade lookup bound to its own app config.

    Interleaved tasks must resolve different application-owned hashers.
    """
    argon_application = Application(
        config={"hashing": {"driver": "argon2id"}},
        service_providers=(HashingServiceProvider(),),
    )
    bcrypt_application = Application(
        config={"hashing": {"driver": "bcrypt"}},
        service_providers=(HashingServiceProvider(),),
    )
    argon_hasher = argon_application.container.make(Hasher)
    bcrypt_hasher = bcrypt_application.container.make(Hasher)

    async def resolve_in_context(
        application: Application,
        expected: Hasher,
    ) -> None:
        """Resolve the facade after yielding inside one app context.

        Args:
            application: Application whose context the task binds.
            expected: Hasher owned by that application's container.
        """
        with application.context():
            await anyio.lowlevel.checkpoint()
            assert Hash.resolve_service() is expected

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(resolve_in_context, argon_application, argon_hasher)
        tasks.start_soon(resolve_in_context, bcrypt_application, bcrypt_hasher)
