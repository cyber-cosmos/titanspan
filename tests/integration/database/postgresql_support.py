"""Provide shared configuration checks for real PostgreSQL tests.
"""  # fmt: skip

from __future__ import annotations

import os

import pytest
from sqlalchemy.engine import URL

_POSTGRES_URL_ENV = "TITANSPAN_TEST_POSTGRES_URL"
_REQUIRE_POSTGRES_ENV = "TITANSPAN_REQUIRE_POSTGRES"
_POSTGRES_USER_ENV = "TITANSPAN_TEST_POSTGRES_USER"
# The value names a variable and contains no actual password.
_POSTGRES_AUTH_ENV = (
    "TITANSPAN_TEST_POSTGRES_PASSWORD"  # pragma: allowlist secret
)
_POSTGRES_HOST_ENV = "TITANSPAN_TEST_POSTGRES_HOST"
_POSTGRES_PORT_ENV = "TITANSPAN_TEST_POSTGRES_PORT"
_POSTGRES_DATABASE_ENV = "TITANSPAN_TEST_POSTGRES_DATABASE"


def configured_postgres_url() -> str:
    """Require a disposable integration URL when PostgreSQL is mandatory.

    Returns:
        The configured URL for an isolated PostgreSQL test database.

    Raises:
        pytest.fail.Exception: If mandatory CI lacks its configured service.
    """
    url = os.environ.get(_POSTGRES_URL_ENV)
    if url is not None:
        return url
    if os.environ.get(_REQUIRE_POSTGRES_ENV) != "1":
        pytest.skip(f"Set {_POSTGRES_URL_ENV} to run Postgres integration.")

    username = os.environ.get(_POSTGRES_USER_ENV)
    password = os.environ.get(_POSTGRES_AUTH_ENV)
    host = os.environ.get(_POSTGRES_HOST_ENV)
    port_value = os.environ.get(_POSTGRES_PORT_ENV)
    database = os.environ.get(_POSTGRES_DATABASE_ENV)
    if (
        username is None
        or password is None
        or host is None
        or port_value is None
        or database is None
    ):
        pytest.fail(
            f"{_REQUIRE_POSTGRES_ENV}=1 requires {_POSTGRES_URL_ENV} "
            "or all structured PostgreSQL connection settings.",
        )
    try:
        port = int(port_value)
    except ValueError:
        pytest.fail(f"{_POSTGRES_PORT_ENV} must be an integer.")
    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)
