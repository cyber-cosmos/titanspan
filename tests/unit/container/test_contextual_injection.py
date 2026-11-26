"""Verify contextual and declarative dependency resolution.

The tests exercise the native registration API through real Dishka graphs.
"""

from __future__ import annotations

import asyncio
from collections.abc import (
    AsyncIterator,  # The backend resolves factory hints.
    Awaitable,  # Callback validation resolves return hints.
    Iterator,  # The backend evaluates resource factory hints.
    Mapping,
)
from typing import TYPE_CHECKING, Annotated, Protocol, cast

import anyio
import pytest

from titanspan.config import ConfigValueError
from titanspan.config import Repository as ConfigStore
from titanspan.container import (
    Container,
    FromConfig,
    Inject,
    Named,
    Tagged,
    singleton,
)
from titanspan.container._internal.injection import read_config_value
from titanspan.container.exceptions import (
    AsyncResolutionRequiredError,
    BindingError,
    BindingResolutionError,
    ScopeError,
)
from titanspan.contracts.config import ConfigReader

if TYPE_CHECKING:
    from collections.abc import Sequence

    from titanspan.contracts import ServiceOverride

pytestmark = pytest.mark.unit

_CONFIG_BATCH_SIZE = 64
_CONFIG_RATIO = 1.5
_TAGGED_BATCH_SIZE = 32
_EXPLICIT_BATCH_SIZE = 7
_CONTEXTUAL_BATCH_SIZE = 30


class DataRepository(Protocol):
    """Define the repository capability consumed by application services.

    Contextual registration selects different implementations by consumer.
    """

    @property
    def name(self) -> str:
        """Return a stable implementation marker for assertions.

        Returns:
            The repository implementation name.
        """
        ...


class SqlRepository:
    """Represent the default document persistence implementation.

    The class has no constructor dependencies and is auto-resolved.
    """

    name = "sql"


class AnalyticsRepository:
    """Represent the analytics-specific repository implementation.

    This implementation verifies consumer-specific contextual selection.
    """

    name = "analytics"


class DocumentService:
    """Consume one contextually selected document repository.

    Attributes:
        repository: Repository injected for document processing.
    """

    def __init__(self, repository: DataRepository) -> None:
        """Retain the service dependency selected by the container.

        Args:
            repository: Consumer-specific document repository.
        """
        self.repository = repository

    repository: DataRepository


class AsyncContextualService:
    """Consume a dependency selected through contextual registration.

    The selected implementation may require asynchronous initialization even
    when the consumer's own constructor is synchronous.
    """

    def __init__(self, repository: DataRepository) -> None:
        """Retain the asynchronously initialized repository.

        Args:
            repository: Contextually selected dependency.
        """
        self.repository = repository

    repository: DataRepository


class AsyncAnnotatedService:
    """Consume a service implementation selected by injection metadata.

    The concrete class may have its own asynchronous resource binding.
    """

    def __init__(
        self,
        repository: Annotated[DataRepository, Inject(SqlRepository)],
    ) -> None:
        """Retain the annotated dependency.

        Args:
            repository: Service selected by the ``Inject`` marker.
        """
        self.repository = repository

    repository: DataRepository


class AnalyticsService:
    """Consume one contextually selected analytics repository.

    Attributes:
        repository: Repository injected for analytics operations.
    """

    def __init__(self, repository: DataRepository) -> None:
        """Retain the service dependency selected by the container.

        Args:
            repository: Consumer-specific analytics repository.
        """
        self.repository = repository

    repository: DataRepository


class ApplicationServices:
    """Aggregate separate consumers inside one dependency graph.

    Attributes:
        documents: Consumer with document-specific dependencies.
        analytics: Consumer with analytics-specific dependencies.
    """

    def __init__(
        self,
        documents: DocumentService,
        analytics: AnalyticsService,
    ) -> None:
        """Retain both application consumers for isolation assertions.

        Args:
            documents: Service using the document repository binding.
            analytics: Service using the analytics repository binding.
        """
        self.documents = documents
        self.analytics = analytics

    documents: DocumentService
    analytics: AnalyticsService


class ConfiguredService:
    """Consume explicitly selected and configuration-backed dependencies.

    Attributes:
        repository: Repository selected by ``Inject`` metadata.
        batch_size: Primitive value read from the configuration contract.
    """

    def __init__(
        self,
        repository: Annotated[DataRepository, Inject(SqlRepository)],
        batch_size: Annotated[int, FromConfig("processing.batch_size")],
    ) -> None:
        """Retain implementation and configuration injections.

        Args:
            repository: Explicit implementation selected by metadata.
            batch_size: Typed application configuration value.
        """
        self.repository = repository
        self.batch_size = batch_size

    repository: DataRepository
    batch_size: int


class TaggedHandler(Protocol):
    """Describe one handler contributed to an ordered service tag.

    Each implementation provides a stable value for the receiving service.
    """

    @property
    def value(self) -> str:
        """Return the handler marker.

        Returns:
            A short identifier for the concrete handler.
        """
        ...


class FirstHandler:
    """Represent the first registered handler in an ordered tag.

    The tag integration preserves this declaration's position.
    """

    value = "first"


class SecondHandler:
    """Represent the second registered handler in an ordered tag.

    The tag integration preserves this declaration's position.
    """

    value = "second"


class TaggedService:
    """Receive all handlers registered under one declared tag.

    Attributes:
        handlers: Handler instances resolved in registration order.
    """

    def __init__(
        self,
        handlers: Annotated[list[TaggedHandler], Tagged("document.handlers")],
    ) -> None:
        """Retain the handler collection provided by the container.

        Args:
            handlers: Lazy resolved values from the selected service tag.
        """
        self.handlers = handlers

    handlers: list[TaggedHandler]


class NamedService:
    """Receive one dependency through its registered type alias.

    Attributes:
        repository: Repository resolved from the named service key.
    """

    def __init__(
        self,
        repository: Annotated[DataRepository, Named("document-repository")],
    ) -> None:
        """Retain the aliased dependency selected by the container.

        Args:
            repository: Repository registered under the declared alias.
        """
        self.repository = repository

    repository: DataRepository


class ConfigValueService:
    """Consume a primitive value from a contextual configuration rule.

    Attributes:
        batch_size: Processing batch size selected by the container.
    """

    def __init__(self, batch_size: int) -> None:
        """Retain the contextual primitive constructor argument.

        Args:
            batch_size: Value supplied by configuration or explicit input.
        """
        self.batch_size = batch_size

    batch_size: int


class CallableInjectionTarget:
    """Expose sync and async callables for contextual parameter injection.

    Both methods use one consumer identity so the rule is applied consistently
    by explicit synchronous and asynchronous invocation.
    """

    def process(
        self,
        batch_size: Annotated[int, FromConfig("processing.batch_size")],
    ) -> int:
        """Return one dependency-selected value.

        Args:
            batch_size: Contextual value or explicit caller override.

        Returns:
            The selected batch size.
        """
        return batch_size

    async def process_async(
        self,
        batch_size: Annotated[int, FromConfig("processing.batch_size")],
    ) -> int:
        """Return one value through the explicit asynchronous call path.

        Args:
            batch_size: Contextual value or explicit caller override.

        Returns:
            The selected batch size.
        """
        await anyio.lowlevel.checkpoint()
        return batch_size


class CallbackService:
    """Represent a cached service observed by resolution callbacks.

    Callback tests distinguish construction identity from repeated retrieval.
    """


class SharedService:
    """Represent an application singleton preserved by a temporary override.

    The test observes its identity across the parent and overlay graph.
    """


class BasicConfigReader:
    """Provide only the base configuration contract for failure checks.

    Typed accessor capability is intentionally absent.

    Attributes:
        _values: Empty mapping backing the read operations.
    """

    def __init__(self) -> None:
        """Create a reader with no stored values.

        The fixture exists only to exercise the base protocol boundary.
        """
        self._values: dict[str, object] = {}

    def has(self, key: str) -> bool:
        """Report that no configuration keys are present.

        Args:
            key: Dotted key being inspected.

        Returns:
            Always false for this empty test reader.
        """
        return key in self._values

    def get(
        self,
        key: str | Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> object:
        """Return a fallback or empty mapping for a requested key.

        Args:
            key: Path or collection of paths being read.
            default: Value returned for a missing scalar path.

        Returns:
            The fallback or an empty mapping.
        """
        if isinstance(key, str):
            return self._values.get(key, default)
        return self.get_many(key, default)

    def get_many(
        self,
        keys: Sequence[str] | Mapping[str, object],
        default: object = None,
    ) -> Mapping[str, object]:
        """Return no values for the requested paths.

        Args:
            keys: Paths requested by the caller.
            default: Unused fallback for missing values.

        Returns:
            An empty mapping.
        """
        names = keys if not isinstance(keys, Mapping) else keys.keys()
        result: dict[str, object] = {}
        for name in names:
            fallback = keys[name] if isinstance(keys, Mapping) else default
            result[name] = self._values.get(name, fallback)
        return result

    def all(self) -> Mapping[str, object]:
        """Return an empty configuration snapshot.

        Returns:
            An empty read-only-compatible mapping.
        """
        return dict(self._values)


class MultiTypedConfigService:
    """Consume values through each existing typed configuration accessor.

    Attributes:
        label: Configured string.
        ratio: Configured float.
        enabled: Configured boolean.
        options: Configured mapping.
        steps: Configured list.
    """

    def __init__(
        self,
        label: Annotated[str, FromConfig("values.label")],
        ratio: Annotated[float, FromConfig("values.ratio")],
        enabled: Annotated[bool, FromConfig("values.enabled")],
        options: Annotated[dict[str, object], FromConfig("values.options")],
        metadata: Annotated[Mapping[str, object], FromConfig("values.meta")],
        steps: Annotated[list[object], FromConfig("values.steps")],
    ) -> None:
        """Retain the configuration values after typed retrieval.

        Args:
            label: Text value.
            ratio: Floating-point value.
            enabled: Boolean value.
            options: Dictionary value.
            metadata: Mapping value.
            steps: List value.
        """
        self.label = label
        self.ratio = ratio
        self.enabled = enabled
        self.options = options
        self.metadata = metadata
        self.steps = steps

    label: str
    ratio: float
    enabled: bool
    options: dict[str, object]
    metadata: Mapping[str, object]
    steps: list[object]


class ReplacementSingletonDocumentService:
    """Represent a singleton replacement owned by an outer overlay.

    Attributes:
        repository: Dependency captured by the owning overlay.
    """

    def __init__(self, repository: DataRepository) -> None:
        """Retain the repository selected by the overlay that owns the value.

        Args:
            repository: Repository resolved in the singleton's owner graph.
        """
        self.repository = repository

    repository: DataRepository


class UnsupportedConfigService:
    """Represent an unsupported config annotation for validation checks.

    Attributes:
        value: Complex value unsupported by `TypedConfigReader` accessors.
    """

    def __init__(
        self,
        value: Annotated[complex, FromConfig("values.value")],
    ) -> None:
        """Retain a value only if config injection supports its annotation.

        Args:
            value: Complex number from a configuration source.
        """
        self.value = value

    value: complex


class SingletonDocumentService:
    """Represent an app singleton whose repository can be substituted.

    Attributes:
        repository: Repository captured at singleton construction.
    """

    def __init__(self, repository: DataRepository) -> None:
        """Retain the repository selected for this singleton.

        Args:
            repository: The dependency captured for the application lifetime.
        """
        self.repository = repository

    repository: DataRepository


class SingletonDocumentConsumer:
    """Represent a transient consumer of the application singleton.

    Attributes:
        service: Application-owned service reached transitively.
    """

    def __init__(self, service: SingletonDocumentService) -> None:
        """Retain the application-owned dependency.

        Args:
            service: The singleton whose repository was selected earlier.
        """
        self.service = service

    service: SingletonDocumentService


class ExtendableService:
    """Hold markers added by ordered service extensions.

    Attributes:
        markers: Extension markers appended by registered functions.
    """

    def __init__(self) -> None:
        """Start with no extension markers.

        The container extensions are responsible for ordered enrichment.
        """
        self.markers: list[str] = []


@singleton
class DeclaredExtensionService(ExtendableService):
    """Declare application lifetime through a native class decorator.

    The extension integration must preserve this declared cache policy.
    """


class OverrideResource:
    """Represent a resource with observable finalization state.

    The owning container controls the lifetime recorded by ``closed``.
    """

    def __init__(self) -> None:
        """Create an open resource for lifecycle assertions.

        The owner marks it closed when finalization completes.
        """
        self.closed = False

    closed: bool


class ResourceConsumer:
    """Hold an application resource through a transient dependency graph.

    Attributes:
        resource: The app-owned value injected from the shared graph.
    """

    def __init__(self, resource: OverrideResource) -> None:
        """Retain the resolved app-owned resource.

        Args:
            resource: Resource whose owner must outlive an override graph.
        """
        self.resource = resource

    resource: OverrideResource


class PositionalInjectionService:
    """Use positional-only metadata and preserve an optional default.

    Attributes:
        repository: The implementation selected through annotation metadata.
        label: Optional constructor value retained from its Python default.
    """

    def __init__(
        self,
        repository: Annotated[DataRepository, Inject(SqlRepository)],
        /,
        label: str = "default",
    ) -> None:
        """Store injected and defaulted constructor values.

        Args:
            repository: The concrete implementation selected by metadata.
            label: Optional value used to exercise default preservation.
        """
        self.repository = repository
        self.label = label

    repository: DataRepository
    label: str


class ConflictingMetadataService:
    """Declare invalid multiple injection sources for one parameter.

    The graph must reject this declaration without constructing the class.
    """

    def __init__(
        self,
        value: Annotated[
            int,
            FromConfig("processing.batch_size"),
            Named("primary-repository"),
        ],
    ) -> None:
        """Retain a value only if conflicting metadata were accepted.

        Args:
            value: Invalid declaration rejected before construction.
        """
        self.value = value

    value: int


class InvalidAnnotationService:
    """Provide a constructor with a simulated unresolved optional type.

    The annotation is replaced after class creation to model an unavailable
    integration type without making the test module itself invalid.
    """

    def __init__(self, dependency: object) -> None:
        """Retain an injected object if annotation inspection succeeds.

        Args:
            dependency: Placeholder for the unresolved annotation target.
        """
        self.dependency = dependency

    dependency: object


InvalidAnnotationService.__init__.__annotations__["dependency"] = (
    "UnavailableOptionalDependency"
)


class MissingAliasService:
    """Request a deliberately unregistered service alias.

    Graph construction should reject this declared dependency source.
    """

    def __init__(
        self,
        repository: Annotated[DataRepository, Named("absent-repository")],
    ) -> None:
        """Retain a value only if invalid metadata resolves unexpectedly.

        Args:
            repository: Dependency selected by the missing alias.
        """
        self.repository = repository

    repository: DataRepository


class MissingTagService:
    """Request a deliberately unregistered service tag.

    Graph construction should reject this declared dependency source.
    """

    def __init__(
        self,
        handlers: Annotated[list[TaggedHandler], Tagged("absent-handlers")],
    ) -> None:
        """Retain values only if the missing tag resolves unexpectedly.

        Args:
            handlers: Dependencies selected by the missing tag.
        """
        self.handlers = handlers

    handlers: list[TaggedHandler]


class InvalidImplementationMetadataService:
    """Declare a value that is not a valid injection implementation.

    The container must reject this malformed marker before construction.
    """

    def __init__(
        self,
        value: Annotated[
            int,
            Inject(
                cast("type[object]", object()),  # noqa: UP037
            ),
        ],
    ) -> None:
        """Retain a value only if the invalid source is accepted.

        Args:
            value: Parameter whose metadata must fail graph composition.
        """
        self.value = value

    value: int


class AsyncCallbackService:
    """Represent a value observed by an asynchronous lifecycle callback.

    Tests verify async preflight and post-resolution hook ordering.
    """


class AsyncCallableObserver:
    """Observe resolution through an asynchronous callable object.

    Attributes:
        observed: Instances passed through the callback's async method.
    """

    def __init__(self) -> None:
        """Start an empty observation list for one test registry.

        Callback invocations append resolved values to this list.
        """
        self.observed: list[object] = []

    async def __call__(self, service: object) -> None:
        """Record one resolved value asynchronously.

        Args:
            service: Instance passed by the resolution callback registry.
        """
        await anyio.lowlevel.checkpoint()
        self.observed.append(service)

    observed: list[object]


def read_annotated_repository(
    repository: Annotated[DataRepository, Inject(SqlRepository)],
) -> str:
    """Read one service selected by synchronous callable metadata.

    Args:
        repository: Concrete dependency selected by ``Inject``.

    Returns:
        The implementation marker used by the regression assertion.
    """
    return repository.name


def read_configured_batch_size(
    batch_size: Annotated[int, FromConfig("processing.batch_size")],
) -> int:
    """Read one configuration value through callable injection.

    Args:
        batch_size: Value read through the registered configuration contract.

    Returns:
        The configured integer value.
    """
    return batch_size


def read_named_repository(
    repository: Annotated[DataRepository, Named("document-repository")],
) -> str:
    """Read one alias-selected service through callable injection.

    Args:
        repository: Service registered under the declared alias.

    Returns:
        The implementation marker for the selected service.
    """
    return repository.name


async def read_tagged_handlers(
    handlers: Annotated[list[TaggedHandler], Tagged("document.handlers")],
) -> tuple[str, ...]:
    """Read tagged service values through asynchronous callable injection.

    Args:
        handlers: Ordered services selected by the declared tag.

    Returns:
        Values in tag registration order.
    """
    return tuple(handler.value for handler in handlers)


def add_first_extension(
    service: ExtendableService,
) -> ExtendableService:
    """Add the first marker and return the same owned instance.

    Args:
        service: Service instance produced by the dependency graph.

    Returns:
        The enriched service with its identity preserved.
    """
    service.markers.append("first")
    return service


def add_second_extension(
    service: ExtendableService,
) -> ExtendableService:
    """Add the second marker after the first extension.

    Args:
        service: Service instance produced by the first extension.

    Returns:
        The same service after ordered enrichment.
    """
    service.markers.append("second")
    return service


def provide_batch_size() -> int:
    """Return one factory-produced primitive for contextual resolution.

    Returns:
        The explicit batch size used by the factory-source regression.
    """
    return _CONTEXTUAL_BATCH_SIZE


def add_declared_extension(
    service: DeclaredExtensionService,
) -> DeclaredExtensionService:
    """Decorate a class-declared singleton through the container backend.

    Args:
        service: App-owned instance created by the dependency graph.

    Returns:
        The same instance after one extension marker is appended.
    """
    service.markers.append("declared")
    return service


async def add_async_extension(
    service: ExtendableService,
) -> ExtendableService:
    """Add a marker from an explicit asynchronous extension.

    Args:
        service: Service instance produced by the dependency graph.

    Returns:
        The same service instance after asynchronous extension work.
    """
    await anyio.lowlevel.checkpoint()
    service.markers.append("async")
    return service


class HandlerService:
    """Consume a tagged dependency through a contextual binding rule.

    Attributes:
        handlers: Values resolved from the configured handler tag.
    """

    def __init__(self, handlers: list[TaggedHandler]) -> None:
        """Retain the tagged handler values for the consumer.

        Args:
            handlers: Ordered handlers contributed to the consumer.
        """
        self.handlers = handlers

    handlers: list[TaggedHandler]


@pytest.mark.anyio
async def test_contextual_bindings_are_consumer_specific_in_one_graph() -> None:
    """Resolve two implementations of one protocol without cross-talk.

    The dependency graph contains both consumers, so selecting one global
    implementation for the protocol would make this regression fail.
    """
    async with Container() as container:
        container.when(DocumentService).needs(DataRepository).give(
            SqlRepository,
        )
        container.when(AnalyticsService).needs(DataRepository).give(
            AnalyticsRepository,
        )

        services = container.make(ApplicationServices)

    assert services.documents.repository.name == "sql"
    assert services.analytics.repository.name == "analytics"


@pytest.mark.anyio
async def test_sync_resolution_rejects_contextual_async_factory() -> None:
    """Identify async contextual sources before composing a sync graph.

    The failed sync lookup must not initialize the selected resource, while
    explicit async resolution must use and finalize it normally.
    """
    lifecycle: list[str] = []

    async def repository_resource() -> AsyncIterator[SqlRepository]:
        """Yield the contextual repository under async ownership.

        Yields:
            The repository owned by the async dependency graph.
        """
        lifecycle.append("started")
        try:
            yield SqlRepository()
        finally:
            lifecycle.append("closed")

    async with Container() as container:
        container.when(AsyncContextualService).needs(
            DataRepository,
        ).give(repository_resource)

        with pytest.raises(
            AsyncResolutionRequiredError,
            match="make_async",
        ):
            container.make(AsyncContextualService)
        assert lifecycle == []

        service = await container.make_async(AsyncContextualService)
        assert isinstance(service.repository, SqlRepository)
        assert lifecycle == ["started"]

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_sync_resolution_rejects_async_annotated_implementation() -> None:
    """Inspect async resources behind an ``Inject`` implementation marker.

    Sync resolution must reject the annotated binding before the backend
    constructs a graph that cannot run synchronously.
    """
    lifecycle: list[str] = []

    async def repository_resource() -> AsyncIterator[SqlRepository]:
        """Yield an asynchronously owned implementation.

        Yields:
            The service instance selected by injection metadata.
        """
        lifecycle.append("started")
        try:
            yield SqlRepository()
        finally:
            lifecycle.append("closed")

    async with Container() as container:
        container.singleton(SqlRepository, repository_resource)

        with pytest.raises(
            AsyncResolutionRequiredError,
            match="make_async",
        ):
            container.make(AsyncAnnotatedService)
        assert lifecycle == []

        service = await container.make_async(AsyncAnnotatedService)
        assert isinstance(service.repository, SqlRepository)
        assert lifecycle == ["started"]

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_annotated_injection_and_config_values_use_native_contracts() -> (
    None
):
    """Resolve implementation and primitive metadata through one graph.

    Configuration access is performed through the registered reader
    contract; no second settings registry is introduced.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": 64}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)

        service = container.make(ConfiguredService)

    assert isinstance(service.repository, SqlRepository)
    assert service.batch_size == _CONFIG_BATCH_SIZE


@pytest.mark.anyio
async def test_from_config_uses_existing_typed_accessors() -> None:
    """Resolve supported scalar and container types through config contracts.

    The adapter delegates validation to the real configuration repository.
    """
    configuration = ConfigStore(
        {
            "values": {
                "label": "worker",
                "ratio": _CONFIG_RATIO,
                "enabled": True,
                "options": {"retries": 2},
                "meta": {"source": "config"},
                "steps": ["read", "write"],
            },
        },
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)

        service = await container.make_async(MultiTypedConfigService)

    assert service.label == "worker"
    assert service.ratio == _CONFIG_RATIO
    assert service.enabled is True
    assert service.options == {"retries": 2}
    assert service.metadata == {"source": "config"}
    assert service.steps == ["read", "write"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("options", ["read"]),
        ("meta", ["read"]),
        ("steps", {"read": True}),
    ],
)
async def test_from_config_rejects_incompatible_collection_shapes(
    key: str,
    replacement: object,
) -> None:
    """Reject collection values that disagree with parameter annotations.

    The typed config capability accepts lists and mappings broadly, while
    injection also enforces the outer shape requested by the annotation.
    """
    collections: dict[str, object] = {
        "options": {"retries": 2},
        "meta": {"source": "config"},
        "steps": ["read", "write"],
    }
    collections[key] = replacement
    configuration = ConfigStore(
        {
            "values": {
                "label": "worker",
                "ratio": _CONFIG_RATIO,
                "enabled": True,
                **collections,
            },
        },
    )

    async with Container() as container:
        container.instance(ConfigReader, configuration)

        with pytest.raises(BindingResolutionError) as error:
            await container.make_async(MultiTypedConfigService)

    cause = error.value.__cause__
    while cause is not None and not isinstance(cause, TypeError):
        cause = cause.__cause__
    assert isinstance(cause, TypeError)


@pytest.mark.parametrize(
    ("annotation", "value", "expected"),
    [
        (list, ["read"], ["read"]),
        (dict, {"source": "config"}, {"source": "config"}),
        (Mapping, {"source": "config"}, {"source": "config"}),
    ],
)
def test_config_injection_accepts_unsubscripted_collection_annotations(
    annotation: object,
    value: object,
    expected: object,
) -> None:
    """Resolve bare collection classes through the existing array accessor.

    Built-in list and dict annotations have no generic origin at runtime, so
    the adapter must recognize their class objects directly.
    """
    configuration = ConfigStore({"values": {"collection": value}})

    assert (
        read_config_value(
            configuration,
            "values.collection",
            annotation,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        (list, {"source": "config"}),
        (dict, ["read"]),
        (Mapping, ["read"]),
    ],
)
def test_config_injection_rejects_bare_collection_shape_mismatches(
    annotation: object,
    value: object,
) -> None:
    """Reject broad array values that do not satisfy a bare collection type.

    This checks the same adapter path used after ``FromConfig`` selects its
    typed configuration accessor.
    """
    configuration = ConfigStore({"values": {"collection": value}})

    with pytest.raises(TypeError):
        read_config_value(
            configuration,
            "values.collection",
            annotation,
        )


@pytest.mark.anyio
async def test_from_config_rejects_unsupported_parameter_annotations() -> None:
    """Reject config types for which no typed accessor exists.

    No new model validation behavior is inferred by the dependency adapter.
    """
    configuration = ConfigStore({"values": {"value": 1 + 2j}})
    async with Container() as container:
        container.instance(ConfigReader, configuration)

        with pytest.raises(BindingResolutionError) as error:
            await container.make_async(UnsupportedConfigService)

    cause = error.value.__cause__
    while cause is not None and not isinstance(cause, BindingError):
        cause = cause.__cause__
    assert isinstance(cause, BindingError)


@pytest.mark.anyio
async def test_from_config_requires_typed_reader_capability() -> None:
    """Fail clearly when the selected reader lacks typed accessors.

    The base `ConfigReader` contract remains usable without falsely claiming
    typed value validation.
    """
    async with Container() as container:
        container.instance(ConfigReader, BasicConfigReader())

        with pytest.raises(BindingResolutionError) as error:
            await container.make_async(ConfiguredService)

    cause = error.value.__cause__
    while cause is not None and not isinstance(cause, BindingError):
        cause = cause.__cause__
    assert isinstance(cause, BindingError)


@pytest.mark.anyio
async def test_explicit_binding_applies_metadata_and_defaults() -> None:
    """Adapt an explicitly registered constructor through its metadata.

    The constructor keeps a positional-only injected value and an unrelated
    default without requiring the backend to infer an alternate graph.
    """
    async with Container() as container:
        container.bind(PositionalInjectionService)

        service = container.make(PositionalInjectionService)

    assert isinstance(service.repository, SqlRepository)
    assert service.label == "default"


@pytest.mark.anyio
async def test_from_config_rejects_missing_and_incompatible_values() -> None:
    """Use typed configuration access for missing and mismatched values.

    Invalid settings must fail through the configuration capability before
    the consumer receives a value of the wrong type.
    """
    for values in ({}, {"processing": {"batch_size": "64"}}):
        configuration = ConfigStore(values)
        async with Container() as container:
            container.instance(ConfigReader, configuration)

            with pytest.raises(BindingResolutionError) as error:
                await container.make_async(ConfiguredService)

            cause = error.value.__cause__
            while cause is not None and not isinstance(
                cause,
                ConfigValueError,
            ):
                cause = cause.__cause__
            assert isinstance(cause, ConfigValueError)


@pytest.mark.anyio
async def test_conflicting_and_unresolvable_annotations_fail_natively() -> None:
    """Reject ambiguous metadata and unavailable forward references.

    Both errors arise during inspection or graph composition before user
    service constructors are invoked.
    """
    async with Container() as container:
        with pytest.raises(BindingError, match="only one injection marker"):
            container.make(ConflictingMetadataService)

        with pytest.raises(
            BindingError,
            match="inspect dependencies",
        ):
            container.make(InvalidAnnotationService)

        with pytest.raises(BindingError):
            container.make(InvalidImplementationMetadataService)

        with pytest.raises(BindingError):
            container.make(MissingAliasService)

        with pytest.raises(BindingError):
            container.make(MissingTagService)


@pytest.mark.anyio
async def test_invalid_contextual_declarations_fail_at_registration() -> None:
    """Reject empty or malformed consumer and source declarations early.

    Invalid source metadata must not survive until runtime graph construction.
    """
    async with Container() as container:
        with pytest.raises(BindingError, match="consumer classes"):
            container.when(())

        with pytest.raises(BindingError, match="consumer classes"):
            container.when((DocumentService, cast("type[object]", object())))

        with pytest.raises(BindingError, match="parameter names"):
            container.when(DocumentService).needs("").give_value(1)

        with pytest.raises(BindingError, match="keys and tags"):
            container.when(DocumentService).needs("value").give_config("")


def test_injection_metadata_rejects_empty_selectors() -> None:
    """Reject empty config paths, aliases, and tag names at declaration.

    Invalid marker objects cannot be attached to constructor annotations.
    """
    with pytest.raises(BindingError, match="cannot be empty"):
        FromConfig("")

    with pytest.raises(BindingError, match="cannot be empty"):
        Named("")

    with pytest.raises(BindingError, match="cannot be empty"):
        Tagged("")


@pytest.mark.anyio
async def test_give_config_rejects_missing_and_incompatible_values() -> None:
    """Use the same typed accessors for contextual config injection.

    Contextual declarations and Annotated markers share the native config
    capability and reject missing or mismatched values.
    """
    for values in ({}, {"processing": {"batch_size": "64"}}):
        configuration = ConfigStore(values)
        async with Container() as container:
            container.instance(ConfigReader, configuration)
            container.when(ConfigValueService).needs(
                "batch_size",
            ).give_config("processing.batch_size")

            with pytest.raises(BindingResolutionError) as error:
                await container.make_async(ConfigValueService)

            cause = error.value.__cause__
            while cause is not None and not isinstance(
                cause,
                ConfigValueError,
            ):
                cause = cause.__cause__
            assert isinstance(cause, ConfigValueError)


@pytest.mark.anyio
async def test_callable_metadata_resolves_all_native_sources() -> None:
    """Resolve implementation, config, alias, and tag callable sources.

    The sync and async entry points share the same native source metadata and
    the registered typed configuration contract.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": _CONFIG_BATCH_SIZE}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)
        container.singleton(DataRepository, SqlRepository)
        container.alias(DataRepository, "document-repository")
        container.tag([FirstHandler, SecondHandler], "document.handlers")

        implementation = container.call(read_annotated_repository)
        sync_size = container.call(read_configured_batch_size)
        alias = container.call(read_named_repository)
        async_size = await container.call_async(read_configured_batch_size)
        tags = await container.call_async(read_tagged_handlers)

        async with container.override(
            {DataRepository: AnalyticsRepository},
        ):
            overridden_sync = container.call(read_named_repository)
            overridden_async = await container.call_async(
                read_named_repository,
            )

    assert implementation == "sql"
    assert sync_size == _CONFIG_BATCH_SIZE
    assert async_size == _CONFIG_BATCH_SIZE
    assert alias == "sql"
    assert tags == ("first", "second")
    assert overridden_sync == "analytics"
    assert overridden_async == "analytics"


@pytest.mark.anyio
async def test_callable_metadata_reports_missing_aliases_and_tags() -> None:
    """Report undeclared callable aliases and tags as native binding errors.

    Missing sources are rejected before the target callable is invoked.
    """

    def read_missing_alias(
        repository: Annotated[DataRepository, Named("missing-repository")],
    ) -> str:
        """Return an alias marker if unexpected registration succeeds.

        Args:
            repository: Service that should not resolve without an alias.

        Returns:
            The selected repository marker.
        """
        return repository.name

    async def read_missing_tag(
        handlers: Annotated[list[TaggedHandler], Tagged("missing-handlers")],
    ) -> tuple[str, ...]:
        """Return tag values if unexpected registration succeeds.

        Args:
            handlers: Services that should not resolve without a tag.

        Returns:
            Values contributed by the selected tag.
        """
        return tuple(handler.value for handler in handlers)

    async with Container() as container:
        with pytest.raises(BindingError, match="No service alias"):
            container.call(read_missing_alias)

        with pytest.raises(BindingError, match="No services are registered"):
            await container.call_async(read_missing_tag)


@pytest.mark.anyio
async def test_tagged_and_named_metadata_resolve_registered_services() -> None:
    """Resolve named and tagged dependencies through canonical bindings.

    Tags preserve their registration order and aliases identify an existing
    service key without duplicating its binding.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.alias(DataRepository, "document-repository")
        container.when(NamedService).needs(DataRepository).give_named(
            "document-repository",
        )
        container.tag([FirstHandler, SecondHandler], "document.handlers")

        named = container.make(NamedService)
        tagged = container.make(TaggedService)

    assert isinstance(named.repository, SqlRepository)
    assert [handler.value for handler in tagged.handlers] == [
        "first",
        "second",
    ]


@pytest.mark.anyio
async def test_callable_config_injection_rejects_incompatible_values() -> None:
    """Validate config values for both sync and async callable injection.

    Public call resolution shares the typed-reader path with graph factories.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": "64"}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)
        target = CallableInjectionTarget()

        with pytest.raises(ConfigValueError):
            container.call(target.process)
        with pytest.raises(ConfigValueError):
            await container.call_async(target.process_async)


@pytest.mark.anyio
async def test_contextual_config_and_tags_resolve_constructor_values() -> None:
    """Resolve primitive and collection dependencies contextually.

    The fluent API supplies a configuration lookup and an ordered collection
    without registering either value as a global service binding.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": 32}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)
        container.when(ConfigValueService).needs("batch_size").give_config(
            "processing.batch_size",
        )
        container.tag([FirstHandler, SecondHandler], "document.handlers")
        container.when(HandlerService).needs(list[TaggedHandler]).give_tagged(
            "document.handlers",
        )
        container.when(ConfiguredService).needs("batch_size").give(
            provide_batch_size,
        )

        configured = container.make(ConfigValueService)
        handlers = container.make(HandlerService)
        factory_configured = container.make(ConfiguredService)

    assert configured.batch_size == _TAGGED_BATCH_SIZE
    assert [handler.value for handler in handlers.handlers] == [
        "first",
        "second",
    ]
    assert factory_configured.batch_size == _CONTEXTUAL_BATCH_SIZE


@pytest.mark.anyio
async def test_explicit_constructor_values_override_contextual_values() -> None:
    """Give call-site values precedence over contextual primitive rules.

    Explicit construction arguments are scoped to one construction and do
    not mutate the stored contextual rule.
    """
    async with Container() as container:
        container.when(ConfigValueService).needs("batch_size").give_value(30)

        explicit = container.make_with(
            ConfigValueService,
            {"batch_size": 7},
        )
        contextual = container.make(ConfigValueService)

    assert explicit.batch_size == _EXPLICIT_BATCH_SIZE
    assert contextual.batch_size == _CONTEXTUAL_BATCH_SIZE


@pytest.mark.anyio
async def test_make_with_resolves_omitted_annotated_dependencies() -> None:
    """Apply injection metadata while constructing an uncached root.

    Explicit constructor values take precedence, while omitted dependencies
    still use the same metadata and typed configuration contract as graphs.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": _CONFIG_BATCH_SIZE}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)

        service = container.make_with(ConfiguredService, {})

    assert isinstance(service.repository, SqlRepository)
    assert service.batch_size == _CONFIG_BATCH_SIZE


@pytest.mark.anyio
async def test_contextual_precedence_respects_explicit_values() -> None:
    """Apply explicit values, then contextual rules, then metadata defaults.

    A contextual constructor rule replaces an ``Annotated`` configuration
    source, while a per-call parameter remains the highest-priority source.
    """
    configuration = ConfigStore(
        {"processing": {"batch_size": _CONFIG_BATCH_SIZE}},
    )
    async with Container() as container:
        container.instance(ConfigReader, configuration)
        container.when(ConfiguredService).needs("batch_size").give_value(
            _CONTEXTUAL_BATCH_SIZE,
        )

        contextual = container.make(ConfiguredService)
        explicit = container.make_with(
            ConfiguredService,
            {"batch_size": _EXPLICIT_BATCH_SIZE},
        )

    assert contextual.batch_size == _CONTEXTUAL_BATCH_SIZE
    assert explicit.batch_size == _EXPLICIT_BATCH_SIZE


@pytest.mark.anyio
async def test_callable_injection_uses_shared_source_precedence() -> None:
    """Use the shared source selector for sync and async callables.

    A bound method supplies its declaring class as the contextual consumer,
    while explicit named values remain local to one invocation.
    """
    async with Container() as container:
        container.when(CallableInjectionTarget).needs(
            "batch_size",
        ).give_value(_CONTEXTUAL_BATCH_SIZE)
        target = CallableInjectionTarget()

        contextual_sync = container.call(target.process)
        explicit_sync = container.call(
            target.process,
            {"batch_size": _EXPLICIT_BATCH_SIZE},
        )
        contextual_async = await container.call_async(target.process_async)

    assert contextual_sync == _CONTEXTUAL_BATCH_SIZE
    assert explicit_sync == _EXPLICIT_BATCH_SIZE
    assert contextual_async == _CONTEXTUAL_BATCH_SIZE


@pytest.mark.anyio
async def test_extensions_wrap_cached_services_once_in_registration_order() -> (
    None
):
    """Apply native extensions once while preserving singleton identity.

    The dependency engine owns caching for the fully decorated service.
    """
    async with Container() as container:
        container.singleton(ExtendableService)
        container.extend(ExtendableService, add_first_extension)
        container.extend(ExtendableService, add_second_extension)

        first = container.make(ExtendableService)
        second = container.make(ExtendableService)

    assert first is second
    assert first.markers == ["first", "second"]


@pytest.mark.anyio
async def test_extensions_honor_declared_scope_and_skip_unreachable() -> None:
    """Apply declared lifetime decorators only to reachable graph services.

    An extension registered for an unrelated type does not affect resolution,
    while a class-declared singleton receives its registered decorator.
    """
    async with Container() as container:
        container.extend(ExtendableService, add_first_extension)
        container.extend(DeclaredExtensionService, add_declared_extension)

        first = container.make(DeclaredExtensionService)
        second = container.make(DeclaredExtensionService)
        unrelated = container.make(CallbackService)

    assert first is second
    assert first.markers == ["declared"]
    assert isinstance(unrelated, CallbackService)


@pytest.mark.anyio
async def test_async_extensions_require_explicit_async_resolution() -> None:
    """Reject sync resolution before caching an async decorated service.

    The later async lookup executes the extension once and owns the cached
    decorated result.
    """
    async with Container() as container:
        container.singleton(ExtendableService)
        container.extend(ExtendableService, add_async_extension)

        with pytest.raises(AsyncResolutionRequiredError):
            container.make(ExtendableService)
        assert not container.resolved(ExtendableService)

        result = await container.make_async(ExtendableService)

    assert result.markers == ["async"]


@pytest.mark.anyio
async def test_async_callback_requires_async_resolution_early() -> None:
    """Reject asynchronous hooks before constructing their requested value.

    An unsuccessful synchronous call must not leave a partially initialized
    singleton in the shared container cache.
    """
    observed: list[object] = []

    async def after_resolution(service: object) -> None:
        """Record a service after its async resolution boundary.

        Args:
            service: Value resolved by the container.
        """
        await anyio.lowlevel.checkpoint()
        observed.append(service)

    async with Container() as container:
        container.singleton(AsyncCallbackService)
        container.after_resolving(AsyncCallbackService, after_resolution)

        with pytest.raises(AsyncResolutionRequiredError):
            container.make(AsyncCallbackService)
        assert not container.resolved(AsyncCallbackService)

        service = await container.make_async(AsyncCallbackService)

    assert observed == [service]


@pytest.mark.anyio
async def test_async_callable_object_requires_async_resolution() -> None:
    """Recognize async ``__call__`` objects before resolving the service.

    The callable object is invoked and awaited only by the explicit async
    resolution path.
    """
    observer = AsyncCallableObserver()
    async with Container() as container:
        container.singleton(CallbackService)
        container.after_resolving(CallbackService, observer)

        with pytest.raises(AsyncResolutionRequiredError):
            container.make(CallbackService)
        assert not container.resolved(CallbackService)

        service = await container.make_async(CallbackService)

    assert observer.observed == [service]


@pytest.mark.anyio
async def test_awaitable_callback_annotation_selects_async_resolution() -> None:
    """Detect awaitable return annotations without invoking the callback.

    An ordinary function returning an awaitable is a supported async hook
    when it declares the awaitable return type.
    """
    observed: list[object] = []

    async def finish(service: object) -> None:
        """Record the value after the returned awaitable is awaited.

        Args:
            service: Resolved service instance passed by the hook.
        """
        await anyio.lowlevel.checkpoint()
        observed.append(service)

    def after_resolution(service: object) -> Awaitable[None]:
        """Return async work for one resolved service.

        Args:
            service: Resolved value passed to the callback.

        Returns:
            Awaitable work that records callback completion.
        """
        return finish(service)

    async with Container() as container:
        container.singleton(CallbackService)
        container.after_resolving(CallbackService, after_resolution)

        with pytest.raises(AsyncResolutionRequiredError):
            container.make(CallbackService)
        assert not container.resolved(CallbackService)

        service = await container.make_async(CallbackService)

    assert observed == [service]


@pytest.mark.anyio
async def test_unannotated_awaitable_callback_is_closed_on_sync_error() -> None:
    """Close an unexpected coroutine instead of leaking it from sync hooks.

    The callback has an intentionally broad return annotation, so only its
    runtime result reveals the async requirement after service resolution.
    """

    async def finish() -> None:
        """Provide awaitable work that must not run synchronously.

        The callback guard closes this coroutine when sync resolution is used.
        """

    def after_resolution(service: object) -> object:
        """Return hidden async work for the sync guard to close.

        Args:
            service: Resolved instance, unused by this regression.

        Returns:
            A coroutine that must not escape the synchronous API.
        """
        _ = service
        return finish()

    async with Container() as container:
        container.singleton(CallbackService)
        container.after_resolving(CallbackService, after_resolution)

        with pytest.raises(AsyncResolutionRequiredError):
            container.make(CallbackService)

    assert container.resolved(CallbackService)


@pytest.mark.anyio
async def test_unavailable_callback_return_hint_falls_back_to_runtime() -> None:
    """Run a sync hook when an optional return annotation cannot be imported.

    A missing optional type name must not prevent unrelated synchronous
    service access.
    """
    observed: list[object] = []

    def after_resolution(service: object) -> object:
        """Record one synchronous result with a stale type annotation.

        Args:
            service: Resolved service instance.

        Returns:
            ``None`` after recording the value.
        """
        observed.append(service)
        return None

    after_resolution.__annotations__["return"] = "UnavailablePluginType"

    async with Container() as container:
        container.singleton(CallbackService)
        container.after_resolving(CallbackService, after_resolution)

        service = container.make(CallbackService)

    assert observed == [service]


@pytest.mark.anyio
async def test_resolution_callback_rejects_recursive_same_service_request() -> (
    None
):
    """Stop a callback from recursively resolving the same root service.

    The native recursion guard raises before the backend graph is entered a
    second time.
    """
    async with Container() as container:
        container.before_resolving(
            CallbackService,
            lambda service: container.make(service),
        )

        with pytest.raises(BindingResolutionError, match="recursively"):
            container.make(CallbackService)


@pytest.mark.anyio
@pytest.mark.concurrency
async def test_override_resources_finalize_when_context_is_cancelled() -> None:
    """Shield overlay cleanup while cancellation unwinds its owner task.

    The replacement async generator is owned by the temporary graph and its
    finalizer must complete before the override context restores the parent.
    """
    lifecycle: list[str] = []

    async def managed_resource() -> AsyncIterator[OverrideResource]:
        """Yield and finalize one temporary resource.

        Yields:
            The resource created only in the overlay graph.
        """
        lifecycle.append("started")
        resource = OverrideResource()
        try:
            yield resource
        finally:
            await anyio.lowlevel.checkpoint()
            resource.closed = True
            lifecycle.append("closed")

    async with Container() as container:
        with anyio.CancelScope() as cancellation:
            async with container.override(
                {OverrideResource: managed_resource},
            ):
                await container.make_async(OverrideResource)
                cancellation.cancel()
                await anyio.sleep_forever()

    assert lifecycle == ["started", "closed"]


@pytest.mark.anyio
async def test_override_borrows_application_resources_until_shutdown() -> None:
    """Keep unaffected singleton resources owned by the application graph.

    Resolving the service directly or as a transient dependency in a temporary
    overlay must not transfer finalization ownership to that overlay.
    """
    lifecycle: list[str] = []

    async def application_resource() -> AsyncIterator[OverrideResource]:
        """Yield one application resource and record its finalization.

        Yields:
            The resource shared by both overlay and application graphs.
        """
        resource = OverrideResource()
        try:
            yield resource
        finally:
            resource.closed = True
            lifecycle.append("closed")

    container = Container()
    container.singleton(OverrideResource, application_resource)

    async with container.override({DataRepository: AnalyticsRepository}):
        direct = await container.make_async(OverrideResource)
        consumer = await container.make_async(ResourceConsumer)
        assert consumer.resource is direct
        assert not direct.closed

    assert not direct.closed
    assert lifecycle == []
    assert await container.make_async(OverrideResource) is direct
    await container.aclose()

    assert direct.closed
    assert lifecycle == ["closed"]


def test_sync_override_owns_sync_resources_and_restores_after_failure() -> None:
    """Finalize synchronous replacement resources at context exit.

    The original application binding remains intact after an exception, and
    an unaffected singleton stays shared with the temporary graph.
    """
    lifecycle: list[str] = []

    def replacement_resource() -> Iterator[OverrideResource]:
        """Yield one sync-owned replacement and record its cleanup.

        Yields:
            The replacement resource owned by the temporary graph.
        """
        resource = OverrideResource()
        try:
            yield resource
        finally:
            resource.closed = True
            lifecycle.append("closed")

    container = Container()
    application_resource = OverrideResource()
    container.instance(OverrideResource, application_resource)
    application_singleton = SharedService()
    container.instance(SharedService, application_singleton)
    resolved: list[OverrideResource] = []
    failure_message = "exit override"
    override_context: ServiceOverride = container.override(
        {OverrideResource: replacement_resource},
    )

    def leave_override_with_error() -> None:
        """Raise from inside an override after checking shared identity.

        The outer test asserts that cleanup and context restoration still run.
        """
        with override_context:
            replacement = container.make(OverrideResource)
            resolved.append(replacement)
            assert not replacement.closed
            assert container.make(SharedService) is application_singleton
            raise RuntimeError(failure_message)

    with pytest.raises(RuntimeError, match=failure_message):
        leave_override_with_error()

    replacement = resolved[0]
    assert replacement.closed
    assert lifecycle == ["closed"]
    assert container.make(SharedService) is application_singleton
    assert container.make(OverrideResource) is application_resource


@pytest.mark.anyio
async def test_sync_override_singleton_identity_across_modes() -> None:
    """Reuse a sync-owned local singleton through async resolution too.

    Async access inside a synchronous override may use sync-safe graphs, but it
    does not compose a second cache for the replacement service.
    """
    async with Container() as container:
        container.singleton(DataRepository, SqlRepository)
        with container.override({DataRepository: AnalyticsRepository}):
            synchronous = container.make(DataRepository)
            asynchronous = await container.make_async(DataRepository)

    assert synchronous is asynchronous
    assert synchronous.name == "analytics"


@pytest.mark.anyio
async def test_sync_override_rejects_async_factory_before_initialization() -> (
    None
):
    """Require async context entry for async-only replacement resources.

    A failed synchronous lookup must not initialize or retain the resource,
    and the application binding must remain unchanged.
    """
    lifecycle: list[str] = []
    original = OverrideResource()

    async def replacement_resource() -> AsyncIterator[OverrideResource]:
        """Yield an async-only resource and record actual initialization.

        Yields:
            A resource whose acquisition requires async context ownership.
        """
        lifecycle.append("started")
        yield OverrideResource()

    async with Container() as container:
        container.instance(OverrideResource, original)
        with container.override({OverrideResource: replacement_resource}):
            with pytest.raises(
                AsyncResolutionRequiredError,
                match="async with",
            ):
                container.make(OverrideResource)
            assert lifecycle == []

        assert container.make(OverrideResource) is original

    assert lifecycle == []


@pytest.mark.anyio
async def test_nested_override_borrows_outer_override_resources() -> None:
    """Keep an inherited replacement owned by the outer overlay.

    A nested override must borrow an initialized outer singleton and leave its
    resource open until the outer overlay exits.
    """
    lifecycle: list[str] = []

    async def replacement_resource() -> AsyncIterator[OverrideResource]:
        """Yield the resource owned by the outer overlay.

        Yields:
            The replacement that nested contexts must borrow.
        """
        resource = OverrideResource()
        try:
            yield resource
        finally:
            resource.closed = True
            lifecycle.append("closed")

    async with Container() as container:
        container.singleton(OverrideResource)
        async with container.override(
            {OverrideResource: replacement_resource},
        ):
            outer = await container.make_async(OverrideResource)
            async with container.override(
                {DataRepository: AnalyticsRepository},
            ):
                nested = await container.make_async(OverrideResource)
                assert nested is outer
                assert not outer.closed
            assert not outer.closed

        assert outer.closed

    assert lifecycle == ["closed"]


@pytest.mark.anyio
async def test_resolution_callbacks_run_in_order_for_cached_access() -> None:
    """Run callbacks around each public request, including cached requests.

    Registration order is stable and a callback sees the canonical service
    type or resolved instance described by its phase.
    """
    events: list[str] = []

    def before(service: type[object]) -> None:
        """Record the service type before each retrieval.

        Args:
            service: Requested service key.
        """
        events.append(f"before:{service.__name__}")

    def resolving(service: object) -> None:
        """Record the resolved service before after-callbacks run.

        Args:
            service: Cached instance returned by the container.
        """
        events.append(f"resolving:{type(service).__name__}")

    def after(service: object) -> None:
        """Record completion of one public resolution request.

        Args:
            service: Instance returned by the container.
        """
        events.append(f"after:{type(service).__name__}")

    async with Container() as container:
        container.singleton(CallbackService)
        container.before_resolving(CallbackService, before)
        container.resolving(CallbackService, resolving)
        container.after_resolving(CallbackService, after)

        first = container.make(CallbackService)
        second = container.make(CallbackService)

    assert first is second
    assert events == [
        "before:CallbackService",
        "resolving:CallbackService",
        "after:CallbackService",
        "before:CallbackService",
        "resolving:CallbackService",
        "after:CallbackService",
    ]


@pytest.mark.anyio
async def test_overrides_are_isolated_and_preserve_cached_singletons() -> None:
    """Resolve one temporary replacement without mutating base bindings.

    Previously initialized application singletons are seeded into the overlay
    as externally owned instances.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.singleton(SharedService)
        original_shared = container.make(SharedService)

        async with container.override(
            {DataRepository: AnalyticsRepository},
        ):
            temporary = container.make(DocumentService)
            assert isinstance(temporary.repository, AnalyticsRepository)
            assert container.make(SharedService) is original_shared

        restored = container.make(DocumentService)
        assert container.make(SharedService) is original_shared

    assert isinstance(restored.repository, SqlRepository)


@pytest.mark.anyio
async def test_override_rejects_transitive_singleton_substitution() -> None:
    """Reject overrides that cannot affect an app singleton's dependency.

    A singleton cannot be reconstructed in an isolated overlay without
    changing its application ownership or leaking a temporary value.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.singleton(SingletonDocumentService)

        with pytest.raises(ScopeError, match="application singleton"):
            async with container.override(
                {DataRepository: AnalyticsRepository},
            ):
                await container.make_async(SingletonDocumentConsumer)

        service = await container.make_async(SingletonDocumentService)

    assert isinstance(service.repository, SqlRepository)


@pytest.mark.anyio
async def test_sync_override_rejects_transitive_singleton_substitution() -> (
    None
):
    """Apply singleton substitution checks to synchronous graph owners.

    The synchronous backend must reject the same unsafe cache semantics as
    asynchronous graph resolution.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.singleton(SingletonDocumentService)

        with (
            pytest.raises(ScopeError, match="application singleton"),
            container.override({DataRepository: AnalyticsRepository}),
        ):
            container.make(SingletonDocumentConsumer)

        service = container.make(SingletonDocumentService)

    assert isinstance(service.repository, SqlRepository)


@pytest.mark.anyio
async def test_override_rejects_cached_singleton_dependency_substitution() -> (
    None
):
    """Reject an override when the affected singleton already exists.

    Returning the cached original would make a requested substitution appear
    successful while keeping its pre-override dependency.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.singleton(SingletonDocumentService)
        original = await container.make_async(SingletonDocumentService)

        with pytest.raises(ScopeError, match="application singleton"):
            async with container.override(
                {DataRepository: AnalyticsRepository},
            ):
                await container.make_async(SingletonDocumentService)

        assert await container.make_async(SingletonDocumentService) is original


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("initialized", [False, True])
async def test_nested_override_checks_inherited_singleton_dependencies(
    asynchronous: bool,
    initialized: bool,
) -> None:
    """Reject inner replacements hidden by an outer-owned singleton.

    Both sync and async nested overlays must compare changes against the
    singleton's owner graph without closing borrowed singleton resources.
    """
    lifecycle: list[str] = []

    def create_shared_service() -> Iterator[SharedService]:
        """Yield a shared application resource with visible finalization.

        Yields:
            The application-owned service.
        """
        try:
            yield SharedService()
        finally:
            lifecycle.append("closed")

    replacement: type[object] = ReplacementSingletonDocumentService
    override_bindings: dict[type[object], object] = {
        SingletonDocumentService: replacement,
    }

    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        container.singleton(SingletonDocumentService)
        container.singleton(SharedService, create_shared_service)
        shared = container.make(SharedService)

        if asynchronous:
            async with container.override(override_bindings):
                initialized_value = (
                    await container.make_async(SingletonDocumentService)
                    if initialized
                    else None
                )
                async with container.override(
                    {DataRepository: AnalyticsRepository},
                ):
                    assert container.make(SharedService) is shared
                    with pytest.raises(
                        ScopeError,
                        match="application singleton",
                    ):
                        await container.make_async(SingletonDocumentService)
                resolved = await container.make_async(
                    SingletonDocumentService,
                )
                assert lifecycle == []
        else:
            with container.override(override_bindings):
                initialized_value = (
                    container.make(SingletonDocumentService)
                    if initialized
                    else None
                )
                with container.override(
                    {DataRepository: AnalyticsRepository},
                ):
                    assert container.make(SharedService) is shared
                    with pytest.raises(
                        ScopeError,
                        match="application singleton",
                    ):
                        container.make(SingletonDocumentService)
                resolved = container.make(SingletonDocumentService)
                assert lifecycle == []

        assert isinstance(resolved, ReplacementSingletonDocumentService)
        assert isinstance(resolved.repository, SqlRepository)
        if initialized:
            assert resolved is initialized_value
        assert container.make(SharedService) is shared
        assert lifecycle == []

    assert lifecycle == ["closed"]


@pytest.mark.anyio
async def test_instance_override_is_local_to_its_active_context() -> None:
    """Use a supplied instance only in the active override graph.

    The application binding remains unchanged after the instance overlay
    closes, and the container does not own that instance's lifecycle.
    """
    replacement = AnalyticsRepository()
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)

        async with container.override({DataRepository: replacement}):
            temporary = container.make(DocumentService)
            assert temporary.repository is replacement

        restored = container.make(DocumentService)

    assert isinstance(restored.repository, SqlRepository)


@pytest.mark.anyio
async def test_nested_overrides_restore_bindings_and_parent_state() -> None:
    """Restore each overlay in LIFO order without changing the base graph.

    The inner overlay replaces another service but inherits the outer
    repository replacement until its own context exits.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)

        async with container.override(
            {DataRepository: AnalyticsRepository},
        ):
            outer_service = container.make(DocumentService)
            async with container.override({SharedService: SharedService}):
                inner_service = container.make(DocumentService)
                assert isinstance(
                    inner_service.repository,
                    AnalyticsRepository,
                )

            restored_outer = container.make(DocumentService)

        restored_parent = container.make(DocumentService)

    assert isinstance(outer_service.repository, AnalyticsRepository)
    assert isinstance(restored_outer.repository, AnalyticsRepository)
    assert isinstance(restored_parent.repository, SqlRepository)


@pytest.mark.anyio
async def test_overrides_share_uninitialized_unaffected_singletons() -> None:
    """Retain singleton identity when first construction occurs in an overlay.

    A temporary replacement for another service must not create a second
    application singleton graph for unaffected bindings.
    """
    started = asyncio.Event()
    release = asyncio.Event()
    factory_calls = 0

    async def create_shared_service() -> SharedService:
        """Create one delayed singleton for overlapping graph requests.

        Returns:
            The shared value owned by the application container.
        """
        nonlocal factory_calls
        factory_calls += 1
        started.set()
        await release.wait()
        return SharedService()

    async with Container() as container:
        container.singleton(SharedService, create_shared_service)

        async def resolve_in_override() -> SharedService:
            """Resolve the unaffected singleton through a child registry.

            Returns:
                The application-owned singleton instance.
            """
            async with container.override(
                {DataRepository: AnalyticsRepository},
            ):
                return await container.make_async(SharedService)

        overlay_task = asyncio.create_task(resolve_in_override())
        await started.wait()
        parent_task = asyncio.create_task(
            container.make_async(SharedService),
        )
        release.set()
        overlay_value, parent_value = await asyncio.gather(
            overlay_task,
            parent_task,
        )

    assert overlay_value is parent_value
    assert factory_calls == 1


@pytest.mark.anyio
async def test_concurrent_overrides_remain_task_local() -> None:
    """Keep independent replacement graphs isolated across concurrent tasks.

    Both tasks overlap inside temporary contexts while resolving the same
    consumer with different implementation bindings.
    """
    async with Container() as container:
        container.bind(DataRepository, SqlRepository)
        barrier = asyncio.Barrier(2)

        async def resolve_with(
            implementation: type[DataRepository],
        ) -> str:
            """Resolve one consumer under an independent task-local binding.

            Args:
                implementation: Replacement repository used in this task.

            Returns:
                The resolved repository marker.
            """
            async with container.override(
                {DataRepository: implementation},
            ):
                await barrier.wait()
                service = container.make(DocumentService)
                return service.repository.name

        names = await asyncio.gather(
            resolve_with(SqlRepository),
            resolve_with(AnalyticsRepository),
        )

    assert sorted(names) == ["analytics", "sql"]
