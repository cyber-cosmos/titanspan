---
title: "Forwarded calls"
---

<span id="forwarded-calls"></span>

`ForwardsCalls` is a small mixin for wrappers that delegate selected methods
to a composed object while preserving Python's attribute lookup and error
conventions.

```python
from titanspan.support import ForwardsCalls


class Renderer:
    """Provide a method that a wrapper can delegate to."""

    def render(self, value: str) -> str:
        """Render a value as uppercase text."""
        return value.upper()


class RendererProxy(ForwardsCalls):
    """Expose the renderer through a delegating wrapper."""

    def __init__(self, renderer: Renderer) -> None:
        """Store the composed renderer."""
        self.renderer = renderer

    def render(self, value: str) -> object:
        """Forward rendering to the composed implementation."""
        return self.forward_call_to(
            self.renderer,
            "render",
            (value,),
        )
```

## Methods

| Method | Behavior |
|---|---|---|
| `forward_call_to` | Invoke a target method with positional arguments. |
| `forward_decorated_call_to` | Return the wrapper if the target method returns the target itself. |
| `throw_bad_method_call_exception` | Raise `AttributeError` naming the wrapper and missing method. |

A missing target method raises `AttributeError`. An `AttributeError` raised
by an existing descriptor or method is preserved, and a present non-callable
attribute raises `TypeError`.

The mixin accepts positional arguments as a sequence. It does not intercept
attribute access or provide magic forwarding for arbitrary wrapper methods;
the wrapper decides which calls it delegates.
