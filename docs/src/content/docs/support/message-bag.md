---
title: "Message bags"
---

<span id="message-bags"></span>

`MessageBag` stores ordered messages under string or integer keys. It supports
`:message` and `:key` formatting, wildcard reads, duplicate prevention through
`add`, and explicit merge behavior.

```python
from titanspan.support import MessageBag

errors = MessageBag({"email": ["invalid", "required"]})
assert errors.first("email") == "invalid"
assert errors.get("email", "[ :key ] :message") == [
    "[ email ] invalid",
    "[ email ] required",
]
```

## Add and query messages

`add` adds a message only once for its key. `merge` recursively adds incoming
messages, including duplicates. `add_if`, `has_any`, `is_empty`, and
`is_not_empty` each provide one native operation.

```python
errors = MessageBag()
errors.add("email", "invalid").add_if(True, "name", "required")

assert errors.has(["email", "name"])
assert errors.get("email.*") == {}
assert errors.all(":key: :message") == [
    "email: invalid",
    "name: required",
]
```

`has` requires every requested key. `has_any` requires at least one. Both
accept one key, an iterable of keys, or additional positional keys. Passing
`None` to `has` or `has_any` checks whether the bag has any messages.

## Mutation and serialization

`get_messages` and `all` return defensive copies. Use
`add`, `merge`, and `forget` to update the bag. Python `str(bag)` and `to_json`
serialize the raw messages as compact JSON; `to_pretty_json` provides
indented output. The supported JSON option bits are pretty printing and
unescaped Unicode.

## Python behavior

- Integer keys are preserved. Boolean keys are rejected because Python treats
  booleans as integers.
- Message data accepts a mapping or iterable. Iterable entries receive
  integer keys in iteration order.
- Message lists returned by public accessors are copies.
- Python JSON serialization supports the documented pretty-print and
  Unicode options.

See the [Support specification](/titanspan/specifications/support) for ownership and
test evidence.
