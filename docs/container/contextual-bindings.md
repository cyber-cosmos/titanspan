# Contextual bindings

Use a contextual rule when one consumer needs a different implementation or
value than the rest of the application:

```python
container.when(DocumentService).needs(Repository).give(SqlRepository)
container.when(ReportService).needs(Repository).give(AnalyticsRepository)
```

The rule is selected only while resolving the named consumer. It does not
change the ordinary binding for `Repository` or affect unrelated consumers.
Multiple consumers may be selected by passing an iterable to `when`.

## Values and framework services

Use `give_value` for a literal, `give_config` for a value read through the
registered `ConfigReader`, `give_named` for an alias, and `give_tagged` for an
ordered list of services:

```python
container.when(Worker).needs("timeout").give_value(30)
container.when(Worker).needs("batch_size").give_config(
    "processing.batch_size",
)
container.when(Worker).needs("repository").give_named("primary-repository")
```

`give` accepts a concrete implementation or typed factory. The container
does not guess primitive values. A required scalar must have a contextual
value, supported `Annotated` marker, or explicit call argument.

## `Annotated` metadata

Use Titanspan-owned metadata for dependencies declared with `Annotated`:

```python
from typing import Annotated

from titanspan.container import FromConfig, Inject


class DocumentService:
    """Coordinate document operations using configured dependencies.
    """

    def __init__(
        self,
        repository: Annotated[Repository, Inject(SqlRepository)],
        batch_size: Annotated[int, FromConfig("processing.batch_size")],
    ) -> None:
        """Retain values selected by the container.

        Args:
            repository: The explicitly selected repository.
            batch_size: The value read from the configuration contract.
        """
        self.repository = repository
        self.batch_size = batch_size
```

The supported markers are `Inject`, `FromConfig`, `Named`, and `Tagged`.
Configuration metadata requires `ConfigReader` to be registered in the active
application container. More than one supported marker on a parameter raises
`BindingError` instead of guessing.

## Precedence

Explicit arguments passed to `make_with`, `make_with_async`, `call`, or
`call_async` take precedence. Next, the container applies a matching
consumer-specific rule, then `Annotated` metadata, then ordinary binding or
automatic concrete resolution. A Python default is used when no source is
selected. This order allows one construction to override a configured
contextual value without mutating the registration.

Contextual registration freezes with the rest of the binding registry after
the first graph is composed. For temporary substitution after startup, use an
[execution-local override](overrides.md).
