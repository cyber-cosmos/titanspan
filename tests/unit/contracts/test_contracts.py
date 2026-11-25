"""Verify the public contracts package exposes native typed protocols.

The tests exercise structural conformance and public symbol identity without
instantiating infrastructure implementations.
"""

from collections.abc import Iterator, Mapping
from typing import overload

import pytest

from titanspan.contracts import (
    Arrayable,
    AsyncServiceContainer,
    ConfigRepository,
    Jsonable,
    LaravelArrayable,
    LaravelJsonable,
    LaravelResponsable,
    Renderable,
    Responsable,
    ValidatedData,
)
from titanspan.contracts.config_repository import (
    ConfigRepository as ConfigModule,
)
from titanspan.contracts.container import (
    AsyncServiceContainer as ContainerModule,
)
from titanspan.contracts.support import (
    Arrayable as SupportArrayable,
)
from titanspan.contracts.support import (
    Htmlable,
)

pytestmark = pytest.mark.unit
EXPECTED_ARRAY_COUNT = 3
EXPECTED_RESPONSE_LENGTH = 5
EXPECTED_VALIDATED_AGE = 30


class PythonArrayValue:
    """Provide a Python-style typed array representation.

    The fixture keeps the example protocol implementation minimal.
    """

    def to_array(self) -> dict[str, int]:
        """Return the value as a string-keyed mapping.

        Returns:
            A new mapping containing the value's public fields.
        """
        return {"count": 3}


class LaravelArrayValue:
    """Provide the upstream camelCase array conversion method.

    The object intentionally omits the Python spelling.
    """

    def toArray(self) -> dict[str, int]:
        """Return the value as an upstream-compatible array.

        Returns:
            A new mapping containing the value's public fields.
        """
        return {"count": 4}


class PythonJsonValue:
    """Provide a native JSON string representation.

    The example returns a fixed valid document.
    """

    def to_json(self) -> str:
        """Serialize the value to JSON text.

        Returns:
            A JSON document encoded as Unicode text.
        """
        return '{"ready": true}'


class LaravelJsonValue:
    """Provide the upstream camelCase JSON conversion method.

    The example does not translate PHP option bits into Python settings.
    """

    def toJson(self, options: int = 0) -> str:
        """Serialize the value using upstream option flags.

        Args:
            options: Laravel-compatible JSON encoding flags.

        Returns:
            A JSON document encoded as Unicode text.
        """
        del options
        return '{"ready": true}'


class RenderedValue:
    """Provide rendered text without depending on a template engine.

    The fixture demonstrates the backend-neutral string result.
    """

    def render(self) -> str:
        """Return the rendered text representation.

        Returns:
            The completed text output.
        """
        return "ready"


class PythonResponseValue:
    """Provide a Python-named response conversion operation.

    The example keeps request and response types application-defined.
    """

    def to_response(self, request: str) -> int:
        """Build a response value from a request value.

        Args:
            request: The request input used by this example.

        Returns:
            The adapted response value.
        """
        return len(request)


class LaravelResponseValue:
    """Provide the upstream camelCase response conversion operation.

    The fixture omits a snake_case alias to test structural separation.
    """

    def toResponse(self, request: str) -> int:
        """Build an upstream-compatible response value.

        Args:
            request: The request input used by this example.

        Returns:
            The adapted response value.
        """
        return len(request)


class PythonValidatedValue:
    """Expose validated data through array and mapping protocols.

    This fixture demonstrates shape compatibility without validation logic.
    """

    def to_array(self) -> dict[str, int]:
        """Return a shallow mapping copy of validated values.

        Returns:
            The validated values as a new dictionary.
        """
        return {"age": 30}

    def __getitem__(self, key: str) -> int:
        """Retrieve one validated integer value.

        Args:
            key: The validated field name.

        Returns:
            The value associated with the field.
        """
        return self.to_array()[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate the available validated field names.

        Yields:
            Validated keys in insertion order.
        """
        return iter(self.to_array())

    def __len__(self) -> int:
        """Return the number of validated fields.

        Returns:
            The number of available fields.
        """
        return len(self.to_array())


class RepositoryFixture:
    """Implement the mutable configuration repository protocol.

    This lightweight test fixture models only the declared semantics.
    """

    def __init__(self) -> None:
        """Create the test repository with one nested value.

        Keep the fixture independent of production configuration code.
        """
        self.values: dict[str, object] = {"app.name": "Titanspan"}

    def has(self, key: str) -> bool:
        """Check whether a configuration key exists, including null values.

        Args:
            key: The dotted configuration key.

        Returns:
            Whether the exact key is stored.
        """
        return key in self.values

    @overload
    def get(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Retrieve one configuration path.

        Args:
            key: The dotted configuration key.
            default: Value returned when the path is missing.

        Returns:
            The stored value or fallback.
        """

    @overload
    def get(
        self,
        key: list[str] | tuple[str, ...],
        default: object = None,
    ) -> Mapping[str, object]:
        """Retrieve several configuration paths.

        Args:
            key: The requested paths in caller-specified order.
            default: Value substituted for absent paths.

        Returns:
            A mapping keyed by requested paths.
        """

    def get(
        self,
        key: str | list[str] | tuple[str, ...],
        default: object = None,
    ) -> object:
        """Retrieve one value or a selected set of values.

        Args:
            key: A dotted key or ordered sequence of keys.
            default: Value returned when a selected key is missing.

        Returns:
            The selected value, default, or mapping of selected values.
        """
        if isinstance(key, str):
            return self.values.get(key, default)
        return {item: self.values.get(item, default) for item in key}

    def all(self) -> Mapping[str, object]:
        """Return a shallow snapshot of every configuration value.

        Returns:
            A mapping containing the repository's current entries.
        """
        return dict(self.values)

    def set(
        self,
        key: str | Mapping[str, object],
        value: object = None,
    ) -> None:
        """Set one key or merge several values into the repository.

        Args:
            key: A dotted key or mapping of key-value pairs.
            value: The value assigned when ``key`` is a string.
        """
        if isinstance(key, str):
            self.values[key] = value
        else:
            self.values.update(key)

    def prepend(self, key: str, value: object) -> None:
        """Prepend a value to a list-valued configuration item.

        Args:
            key: The target configuration key.
            value: The value inserted at the beginning.
        """
        current = self.values.get(key, [])
        assert isinstance(current, list)
        self.values[key] = [value, *current]

    def push(self, key: str, value: object) -> None:
        """Append a value to a list-valued configuration item.

        Args:
            key: The target configuration key.
            value: The value appended at the end.
        """
        current = self.values.get(key, [])
        assert isinstance(current, list)
        self.values[key] = [*current, value]


class ResolvedService:
    """Represent a no-argument dependency for the resolver fixture.

    The test does not model a production container or scope hierarchy.
    """


class ResolverFixture:
    """Implement the async container contract for a local type fixture.

    The fixture demonstrates generic resolution and asynchronous cleanup
    without introducing a second production dependency engine.
    """

    async def get[ServiceT](self, service: type[ServiceT]) -> ServiceT:
        """Construct a no-argument service by its class key.

        Args:
            service: The service class to instantiate.

        Returns:
            An instance whose type matches the requested class.
        """
        return service()

    async def close(self) -> None:
        """Complete the fixture's no-op resource lifecycle.

        The fixture owns no resources to finalize.
        """


def test_contract_exports_preserve_canonical_identity() -> None:
    """Re-export contract types without creating duplicate identities.

    This keeps imports stable for Support and future component consumers.
    """
    assert ConfigRepository is ConfigModule
    assert AsyncServiceContainer is ContainerModule
    assert Arrayable is SupportArrayable
    assert Htmlable.__module__ == "titanspan.contracts.htmlable"


@pytest.mark.anyio
async def test_async_service_container_preserves_requested_service_type() -> (
    None
):
    """Resolve a generic service and close the structural container fixture.

    This test checks the contract's typing surface, not dependency graph
    semantics supplied by concrete container implementations.
    """
    container: AsyncServiceContainer = ResolverFixture()

    assert isinstance(container, AsyncServiceContainer)
    assert isinstance(await container.get(ResolvedService), ResolvedService)
    await container.close()


def test_support_protocols_accept_native_and_laravel_spellings() -> None:
    """Recognize either supported spelling without requiring both methods.

    Runtime protocol checks verify attribute presence only; static typing and
    behavioral tests remain responsible for the complete method contract.
    """
    assert isinstance(PythonArrayValue(), Arrayable)
    assert isinstance(LaravelArrayValue(), LaravelArrayable)
    assert isinstance(PythonJsonValue(), Jsonable)
    assert isinstance(LaravelJsonValue(), LaravelJsonable)
    assert isinstance(RenderedValue(), Renderable)
    assert isinstance(PythonResponseValue(), Responsable)
    assert isinstance(LaravelResponseValue(), LaravelResponsable)
    assert isinstance(PythonValidatedValue(), ValidatedData)


def test_config_repository_protocol_is_structural_and_mutable() -> None:
    """Describe get, has, set, collection mutation, and snapshots.

    The protocol remains a contract; this fixture demonstrates how a
    replaceable repository can satisfy the declared interface.
    """
    repository = _configuration_repository(RepositoryFixture())

    assert isinstance(repository, ConfigRepository)
    assert repository.has("app.name")
    assert repository.get("app.name") == "Titanspan"
    assert repository.get(("app.name", "missing"), "fallback") == {
        "app.name": "Titanspan",
        "missing": "fallback",
    }

    repository.set({"features": ["ai"]})
    repository.prepend("features", "web")
    repository.push("features", "data")

    assert repository.get("features") == ["web", "ai", "data"]
    assert repository.all()["app.name"] == "Titanspan"


def _arrayable_value(value: Arrayable[str, int]) -> int:
    """Read a typed value from an Arrayable contract.

    Args:
        value: An arrayable implementation with string keys and integers.

    Returns:
        The count stored by the implementation.
    """
    return value.to_array()["count"]


def _configuration_repository(
    repository: ConfigRepository,
) -> ConfigRepository:
    """Check a candidate against the public repository protocol.

    Args:
        repository: A possible configuration repository implementation.

    Returns:
        The same object with its public contract type.
    """
    return repository


def _render_value(value: Renderable) -> str:
    """Render a contract-compatible value as text.

    Args:
        value: The object that owns its rendering behavior.

    Returns:
        The rendered text.
    """
    return value.render()


def _response_value(value: Responsable[str, int], request: str) -> int:
    """Build a generic response without importing a web implementation.

    Args:
        value: The response adapter.
        request: A request-domain value.

    Returns:
        The corresponding response-domain value.
    """
    return value.to_response(request)


def _validated_value(value: ValidatedData[str, int]) -> int:
    """Read one typed value from a validated-data mapping.

    Args:
        value: An implementation of the validated-data contract.

    Returns:
        The integer stored under the ``age`` key.
    """
    return value["age"]


def test_generic_contracts_preserve_python_value_types() -> None:
    """Keep generic result relationships available to static type checking.

    The calls also exercise the expected structural methods at runtime.
    """
    assert _arrayable_value(PythonArrayValue()) == EXPECTED_ARRAY_COUNT
    assert _render_value(RenderedValue()) == "ready"
    assert (
        _response_value(PythonResponseValue(), "hello")
        == EXPECTED_RESPONSE_LENGTH
    )
    assert _validated_value(PythonValidatedValue()) == EXPECTED_VALIDATED_AGE
