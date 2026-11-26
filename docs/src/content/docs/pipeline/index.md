---
title: "Pipeline"
---

# Pipeline

Pipeline passes one value through an ordered sequence of Python stages.
Stages run sequentially. Pipeline does not create background tasks or own a
concurrency runtime.

## Process a value

Use `Pipeline` with explicit input and output types when a stage sequence
changes the value's shape:

```python
from dataclasses import dataclass

from titanspan.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class Document:
    """Hold one source document.

    Attributes:
        text: Original document text.
    """

    text: str


def normalize(document: Document) -> str:
    """Remove surrounding whitespace from the document.

    Args:
        document: Source document.

    Returns:
        Normalized text.
    """
    return document.text.strip()


def count_words(text: str) -> int:
    """Count non-empty words in normalized text.

    Args:
        text: Normalized document text.

    Returns:
        Number of whitespace-separated words.
    """
    return len(text.split())


words = (
    Pipeline[Document, int]()
    .send(Document("  clear stages  "))
    .through([normalize, count_words])
    .then_return()
)
```

For transformations whose types should be inferred one stage at a time, use
`pipe()` or `pipe_async()`. The `pipeline(value)` helper starts a typed
value-preserving builder.

## Resolve application stages

Stage classes can expose `handle(value)` or a selected public method. Pass the
application's Container when a stage needs dependencies:

```python
from decimal import Decimal

from titanspan.container import Container
from titanspan.pipeline import Pipeline


class TaxRate:
    """Provide one configured rate.

    Attributes:
        rate: Decimal rate added to a base amount.
    """

    rate: Decimal

    def __init__(self, rate: Decimal) -> None:
        """Store the application-selected rate.

        Args:
            rate: Rate selected by application configuration.
        """
        self.rate = rate


class AddTax:
    """Apply the configured rate to one amount.

    Attributes:
        _rate: Rate resolved by the native Container.
    """

    _rate: TaxRate

    def __init__(self, rate: TaxRate) -> None:
        """Receive the rate through Container construction.

        Args:
            rate: Dependency constructed by the native Container.
        """
        self._rate = rate

    def handle(self, amount: Decimal) -> Decimal:
        """Return the amount including tax.

        Args:
            amount: Amount before tax.

        Returns:
            Amount after applying the configured rate.
        """
        return amount * (Decimal("1") + self._rate.rate)


container = Container()
container.instance(TaxRate, TaxRate(Decimal("0.08")))
total = (
    Pipeline[Decimal, Decimal](container=container)
    .send(Decimal("10.00"))
    .through([AddTax])
    .then_return()
)
```

Pipeline asks the supplied Container to resolve class stages at execution
time. Container owns any registered stage resources and their lifetimes.
Without a Container, class stages need a zero-argument constructor.

## Use asynchronous stages

Choose `then_return_async()` or `then_async()` when any stage performs async
work. Cancellation propagates to the active stage, which remains responsible
for closing resources it acquires:

The example uses a small local client so the Pipeline is runnable. Replace it
with a model client registered by the application or its AI integration.

```python
from typing import Protocol

from titanspan.container import Container
from titanspan.pipeline import Pipeline


class SummaryModel(Protocol):
    """Describe the model operation supplied by the application.

    The application or its future AI integration implements this protocol.
    """

    async def generate(self, prompt: str) -> str:
        """Generate a summary from prepared prompt text.

        Args:
            prompt: Text sent to the configured model.

        Returns:
            Generated summary text.
        """
        ...


class LocalSummaryModel:
    """Provide a local stand-in for an application model client.

    A production application can bind its provider implementation instead.
    """

    async def generate(self, prompt: str) -> str:
        """Return a deterministic summary label for this example.

        Args:
            prompt: Text sent to the configured model.

        Returns:
            Summary text describing the prompt length.
        """
        return f"Summary for {len(prompt)} characters."


class GenerateSummary:
    """Adapt an application-owned model client as a Pipeline stage.

    Attributes:
        _model: Model dependency supplied by the Container.
    """

    _model: SummaryModel

    def __init__(self, model: SummaryModel) -> None:
        """Retain the model client injected by the Container.

        Args:
            model: Application-owned model integration.
        """
        self._model = model

    async def handle(self, prompt: str) -> str:
        """Generate a summary for one prompt.

        Args:
            prompt: Prepared source text.

        Returns:
            Generated summary text.
        """
        return await self._model.generate(prompt)


async def prepare_prompt(text: str) -> str:
    """Prepare text before passing it to an application model client.

    Args:
        text: Source document text.

    Returns:
        Prompt text for the model client.
    """
    return f"Summarize this document:\n{text}"


container = Container()
container.instance(SummaryModel, LocalSummaryModel())
document_text = "A source document prepared for summary."


async def summarize_document(
    active_container: Container,
    text: str,
) -> str:
    """Run prompt preparation and model generation in order.

    Args:
        active_container: Container with a registered SummaryModel.
        text: Source document text.

    Returns:
        Generated summary text.
    """
    return await (
        Pipeline[str, str](container=active_container)
        .send(text)
        .through([prepare_prompt, GenerateSummary])
        .then_return_async()
    )


async def example() -> str:
    """Run the local model example from an async application operation.

    Returns:
        Generated summary text.
    """
    return await summarize_document(container, document_text)
```

The client and remote-call policy belong to the application or its AI
integration. Pipeline only orders the stages. It does not retry, parallelize,
persist, or orchestrate workflow state. Call `summarize_document` from an
async application operation and pass its configured Container.

## Continuations and conditional stages

`Pipeline.middleware()` wraps a synchronous continuation. The asynchronous
form is `Pipeline.middleware_async()`. A stage may transform the value passed
downstream, inspect the returned value, or short-circuit without calling the
continuation. Use `when(condition, stages)` to add stages when the condition
is true. Builder operations return independent stage snapshots.

## HTTP middleware boundary

Pipeline is for sequential application values. HTTP middleware wraps an ASGI
request and response lifecycle, including request scopes, streaming
transmission, disconnects, and cleanup. It remains owned by HTTP and Routing;
Pipeline does not replace or compose those middleware stacks.

Read the [Pipeline behavioral specification](/titanspan/specifications/pipeline/)
for error, typing, and lifecycle details.
