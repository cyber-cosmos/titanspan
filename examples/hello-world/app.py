"""Run a configured Titanspan application through a FastAPI ASGI boundary.

The example composes native providers, contracts, facades, and automatic
constructor injection before exposing one small HTTP route.
"""

from typing import Protocol

from fastapi import FastAPI

from titanspan import Application
from titanspan.contracts.config import ConfigRepository
from titanspan.contracts.container import ServiceRegistry
from titanspan.contracts.foundation import ServiceProvider
from titanspan.contracts.logging import LogWriter
from titanspan.facades import Config, Log

__all__ = ["app", "application"]


class Greeter(Protocol):
    """Describe the service used by the HTTP example.

    The route depends on this contract, while the application provider selects
    the configured implementation.
    """

    def greet(self, name: str) -> str:
        """Create a greeting for one recipient.

        Args:
            name: Recipient name included in the greeting.

        Returns:
            A message containing the configured application name.
        """
        ...


class ConfiguredGreeter:
    """Create configured greetings and report their creation to logging.

    The container injects both dependencies from their canonical contracts.
    """

    def __init__(
        self,
        configuration: ConfigRepository,
        logger: LogWriter,
    ) -> None:
        """Retain application-owned configuration and logging services.

        Args:
            configuration: Repository selected by application bootstrap.
            logger: Default logger resolved from the configured manager.
        """
        self._configuration = configuration
        self._logger = logger

    def greet(self, name: str) -> str:
        """Return a greeting and emit a structured event.

        Args:
            name: Recipient name included in the greeting.

        Returns:
            A message containing the configured application name.

        Raises:
            TypeError: If the application name is not a string.
        """
        application_name = self._configuration.get("app.name", "Titanspan")
        if not isinstance(application_name, str):
            message = "The configured application name must be a string."
            raise TypeError(message)
        self._logger.info(
            "Greeting created",
            application=application_name,
            recipient=name,
        )
        return f"Hello from {application_name}, {name}!"


class GreetingServiceProvider(ServiceProvider):
    """Register the example greeting service with the application container.

    Providers contribute bindings but do not construct a second registry or
    resolve dependencies themselves.
    """

    def register(self, container: ServiceRegistry) -> None:
        """Bind the greeter contract to its injectable implementation.

        Args:
            container: Canonical registry assembled by the application.
        """
        container.singleton(Greeter, ConfiguredGreeter)


application = Application(
    config={
        "app": {
            "name": "Titanspan Example",
            "debug": False,
        },
    },
    service_providers=(GreetingServiceProvider(),),
)

# FastAPI is the current routing interoperability boundary. Its lifespan
# delegates startup and resource cleanup to the Titanspan Application.
app: FastAPI = application.asgi


@app.get("/")
async def hello_world() -> dict[str, str]:
    """Return a configured greeting and this request's context identifier.

    Returns:
        Application name, service-generated greeting, and request identifier.
    """
    greeter = application.make(Greeter)
    application_name = Config.string("app.name")
    request_id = Log.get_context().get("request_id")
    if not isinstance(request_id, str):
        message = "The ASGI request context has no valid request identifier."
        raise TypeError(message)
    Log.info(
        "Greeting request handled",
        application=application_name,
        request_id=request_id,
    )
    return {
        "application": application_name,
        "message": greeter.greet("world"),
        "request_id": request_id,
    }
