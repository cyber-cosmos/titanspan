"""Verify contracts have one domain-oriented definition and public identity.

The contract package is the source of shared interfaces while components may
re-export them from their public API.
"""

import pytest

from titanspan import contracts
from titanspan.config import ConfigServiceProvider, Repository
from titanspan.container import Container
from titanspan.contracts import (
    AsyncLogDriver,
    AsyncServiceContainer,
    BootableServiceProvider,
    ConfigRepository,
    DeferredDisplayValue,
    DeliveryStatus,
    HtmlRenderable,
    InstanceRegistration,
    LogBridge,
    LogCustomizer,
    LogDriver,
    LogFormatter,
    LoggingManager,
    LogProcessor,
    LogWriter,
    MessageBagProtocol,
    MessageKey,
    MessageProvider,
    ServiceContainer,
    ServiceProvider,
    ServiceRegistry,
    support,
)
from titanspan.contracts.config import (
    ConfigDiagnostics,
    ConfigMacroRegistry,
    ConfigReader,
    ConfigWriter,
    ScopedConfigOverrides,
    TypedConfigReader,
)
from titanspan.contracts.config import (
    ConfigRepository as DomainConfigRepository,
)
from titanspan.contracts.container import (
    AsyncServiceContainer as DomainAsyncServiceContainer,
)
from titanspan.contracts.container import (
    InstanceRegistration as DomainInstanceRegistration,
)
from titanspan.contracts.container import (
    ServiceContainer as DomainServiceContainer,
)
from titanspan.contracts.foundation import (
    BootableServiceProvider as DomainBootableServiceProvider,
)
from titanspan.contracts.foundation import (
    ServiceProvider as DomainServiceProvider,
)
from titanspan.contracts.logging import (
    AsyncLogDriver as DomainAsyncLogDriver,
)
from titanspan.contracts.logging import (
    DeliveryStatus as DomainDeliveryStatus,
)
from titanspan.contracts.logging import (
    LogBridge as DomainLogBridge,
)
from titanspan.contracts.logging import (
    LogCustomizer as DomainLogCustomizer,
)
from titanspan.contracts.logging import (
    LogDriver as DomainLogDriver,
)
from titanspan.contracts.logging import (
    LogFormatter as DomainLogFormatter,
)
from titanspan.contracts.logging import (
    LoggingManager as DomainLoggingManager,
)
from titanspan.contracts.logging import (
    LogProcessor as DomainLogProcessor,
)
from titanspan.contracts.logging import (
    LogWriter as DomainLogWriter,
)
from titanspan.contracts.support import (
    DeferredDisplayValue as DomainDeferredDisplayValue,
)
from titanspan.contracts.support import (
    HtmlRenderable as DomainHtmlRenderable,
)
from titanspan.contracts.support import (
    MessageBagProtocol as DomainMessageBagProtocol,
)
from titanspan.contracts.support import (
    MessageKey as DomainMessageKey,
)
from titanspan.contracts.support import (
    MessageProvider as DomainMessageProvider,
)
from titanspan.logging import (
    AsyncLogDriver as PublicAsyncLogDriver,
)
from titanspan.logging import (
    DeliveryStatus as PublicDeliveryStatus,
)
from titanspan.logging import (
    LogCustomizer as PublicLogCustomizer,
)
from titanspan.logging import (
    LogDriver as PublicLogDriver,
)
from titanspan.logging import (
    LogFormatter as PublicLogFormatter,
)
from titanspan.logging import LogManager
from titanspan.logging import (
    LogProcessor as PublicLogProcessor,
)
from titanspan.logging.service_provider import LoggingServiceProvider
from titanspan.support.message_bag import MessageBag

pytestmark = [pytest.mark.unit, pytest.mark.architecture]


def test_top_level_contract_exports_keep_canonical_type_identity() -> None:
    """Re-export each contract without creating duplicate protocol objects.

    Component imports and convenient top-level imports must resolve to the
    same object so structural typing and runtime checks remain consistent.
    """
    contract_pairs: tuple[tuple[object, object], ...] = (
        (ConfigRepository, DomainConfigRepository),
        (BootableServiceProvider, DomainBootableServiceProvider),
        (AsyncServiceContainer, DomainAsyncServiceContainer),
        (InstanceRegistration, DomainInstanceRegistration),
        (LogBridge, DomainLogBridge),
        (LogWriter, DomainLogWriter),
        (LoggingManager, DomainLoggingManager),
        (ServiceContainer, DomainServiceContainer),
        (ServiceProvider, DomainServiceProvider),
        (AsyncLogDriver, DomainAsyncLogDriver),
        (DeliveryStatus, DomainDeliveryStatus),
        (LogCustomizer, DomainLogCustomizer),
        (LogDriver, DomainLogDriver),
        (LogFormatter, DomainLogFormatter),
        (LogProcessor, DomainLogProcessor),
        (DeferredDisplayValue, DomainDeferredDisplayValue),
        (HtmlRenderable, DomainHtmlRenderable),
        (MessageBagProtocol, DomainMessageBagProtocol),
        (MessageKey, DomainMessageKey),
        (MessageProvider, DomainMessageProvider),
    )

    for public_contract, domain_contract in contract_pairs:
        assert public_contract is domain_contract

    assert LogDriver is PublicLogDriver
    assert LogFormatter is PublicLogFormatter
    assert LogProcessor is PublicLogProcessor
    assert LogCustomizer is PublicLogCustomizer
    assert AsyncLogDriver is PublicAsyncLogDriver
    assert DeliveryStatus is PublicDeliveryStatus


def test_contract_classes_are_declared_in_their_domain_packages() -> None:
    """Keep domain packages as the contract declaration owners.

    Public re-exports must not become a second source of contract identity.
    """
    assert ConfigRepository.__module__ == (
        "titanspan.contracts.config.repository"
    )
    assert ServiceContainer.__module__ == "titanspan.contracts.container"
    assert LogDriver.__module__ == "titanspan.contracts.logging.driver"
    assert MessageProvider.__module__ == (
        "titanspan.contracts.support.message_bag"
    )
    assert HtmlRenderable.__module__ == (
        "titanspan.contracts.support.html_renderable"
    )


def test_production_services_satisfy_canonical_runtime_contracts() -> None:
    """Verify concrete application services satisfy their declared APIs.

    Local annotations provide strict static conformance evidence. Runtime
    protocol checks confirm the production objects expose their contract
    operations without treating member presence as behavioral proof.
    """
    repository = Repository()
    container = Container()
    manager = LogManager(
        {
            "default": "capture",
            "channels": {"capture": {"driver": "memory"}},
        }
    )
    logger = manager.channel()
    config_provider = ConfigServiceProvider(repository)
    logging_provider = LoggingServiceProvider()
    message_bag = MessageBag()

    config_contract: ConfigRepository = repository
    config_reader: ConfigReader = repository
    config_writer: ConfigWriter = repository
    typed_config: TypedConfigReader = repository
    scoped_config: ScopedConfigOverrides = repository
    config_diagnostics: ConfigDiagnostics = repository
    config_macros: ConfigMacroRegistry = repository
    container_contract: ServiceContainer = container
    async_container_contract: AsyncServiceContainer = container
    registry_contract: ServiceRegistry = container
    logging_contract: LoggingManager = manager
    logger_contract: LogWriter = logger
    registration_contract: InstanceRegistration = config_provider
    config_provider_contract: ServiceProvider = config_provider
    logging_provider_contract: ServiceProvider = logging_provider
    message_bag_contract: MessageBagProtocol = message_bag

    assert config_contract is repository
    assert config_reader is repository
    assert config_writer is repository
    assert typed_config is repository
    assert scoped_config is repository
    assert config_diagnostics is repository
    assert config_macros is repository
    assert container_contract is container
    assert async_container_contract is container
    assert registry_contract is container
    assert logging_contract is manager
    assert logger_contract is logger
    assert registration_contract.value is repository
    assert config_provider_contract is config_provider
    assert logging_provider_contract is logging_provider
    assert message_bag_contract is message_bag
    assert isinstance(repository, ConfigRepository)
    assert isinstance(container, ServiceContainer)
    assert isinstance(config_provider, ServiceProvider)
    assert isinstance(logging_provider, ServiceProvider)
    assert isinstance(manager, LoggingManager)
    assert isinstance(logger, LogWriter)
    manager.close()


def test_unimplemented_domain_contracts_are_not_public() -> None:
    """Keep future domain contracts unpublished until owners need them.

    HTTP, validation, and serialization boundaries need implemented owning
    components before their protocols become supported public interfaces.
    """
    future_contracts = (
        "JsonTextProvider",
        "MappingConvertible",
        "Renderable",
        "ResponseConvertible",
        "ValidatedData",
    )
    for name in future_contracts:
        assert not hasattr(contracts, name)
        assert not hasattr(support, name)
