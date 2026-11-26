"""Define native errors for server and client HTTP operations.

Backend exceptions are translated at adapter boundaries and retained as
causes without leaking transport-specific types through Titanspan APIs.
"""


class HttpError(RuntimeError):
    """Represent an HTTP component failure with safe diagnostic context.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpContextError(HttpError):
    """Report use of an application-bound HTTP service without its context.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpConfigurationError(HttpError):
    """Report invalid application HTTP configuration without values.

    Errors avoid exposing credentials or private request payloads.
    """


class RequestError(HttpError):
    """Represent malformed, consumed, or oversized incoming request data.

    Errors avoid exposing credentials or private request payloads.
    """


class RequestBodyTooLargeError(RequestError):
    """Report that an incoming request exceeded its configured byte limit.

    Errors avoid exposing credentials or private request payloads.
    """


class RequestBodyConsumedError(RequestError):
    """Report an attempt to read a body after streaming consumed it.

    Errors avoid exposing credentials or private request payloads.
    """


class RequestInputError(RequestError):
    """Report an input value that cannot satisfy the requested type.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpClientError(HttpError):
    """Represent a failure while making or inspecting an outgoing request.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpFakeError(HttpClientError):
    """Report an invalid HTTP fake context or assertion operation.

    Errors avoid exposing credentials or private request payloads.
    """


class UnexpectedHttpRequestError(HttpFakeError):
    """Report an outgoing call with no available fake response.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpTransportError(HttpClientError):
    """Report a connection or protocol failure from the HTTP transport.

    Errors avoid exposing credentials or private request payloads.
    """


class HttpTimeoutError(HttpTransportError):
    """Report a timeout while omitting the request URL from the message.

    The URL may contain credentials or user-provided query parameters.
    """


class HttpStatusError(HttpClientError):
    """Report an HTTP error status after explicit response escalation.

    Errors avoid exposing credentials or private request payloads.
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Store the response status and a sanitized explanation.

        Args:
            status_code: HTTP status code that caused explicit escalation.
            message: Safe message without credentials or response content.
        """
        super().__init__(message)
        self.status_code = status_code

    status_code: int


class SynchronousHttpInAsyncContextError(HttpClientError):
    """Require async client methods when called from a running event loop.

    Errors avoid exposing credentials or private request payloads.
    """


__all__ = [
    "HttpClientError",
    "HttpConfigurationError",
    "HttpContextError",
    "HttpError",
    "HttpFakeError",
    "HttpStatusError",
    "HttpTimeoutError",
    "HttpTransportError",
    "RequestBodyConsumedError",
    "RequestBodyTooLargeError",
    "RequestError",
    "RequestInputError",
    "SynchronousHttpInAsyncContextError",
    "UnexpectedHttpRequestError",
]
