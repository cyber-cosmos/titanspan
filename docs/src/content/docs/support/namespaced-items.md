---
title: "Namespaced item keys"
---

<span id="namespaced-item-keys"></span>

`NamespacedItemResolver` splits a dotted key into a namespace, group, and
optional item. Use it when an adapter needs a compact key format such as
`mail::messages.welcome`.

```python
from titanspan.support import NamespacedItemResolver

resolver = NamespacedItemResolver()

assert resolver.parse_key("mail::messages.welcome") == [
    "mail",
    "messages",
    "welcome",
]
assert resolver.parse_key("messages.errors.required") == [
    None,
    "messages",
    "errors.required",
]
```

Use `parse_key` to split a key into its namespace, group, and optional item.

## Cache control

Parsed values are cached per resolver instance. `set_parsed_key` seeds or
replaces a value, and `flush_parsed_keys` clears that instance's cache.

```python
resolver.set_parsed_key("messages.custom", ["app", "messages", "custom"])
assert resolver.parse_key("messages.custom") == [
    "app",
    "messages",
    "custom",
]

resolver.flush_parsed_keys()
assert resolver.parse_key("messages.custom") == [None, "messages", "custom"]
```

The cache stores immutable tuples and returns fresh lists, preserving the
value-copy behavior while preventing caller mutation from changing later
results. The resolver does not load configuration or
translation files; those concerns belong to their owning modules.

See the [Support specification](/framework/specifications/support) for module ownership
and test evidence.
