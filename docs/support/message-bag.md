# Message bags

`MessageBag` stores ordered messages under string or integer keys. It supports
Laravel-style `:message` and `:key` formatting, wildcard reads, duplicate
prevention through `add`, and explicit merge behavior.

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

`add` adds a message only once for its key. `merge` follows Laravel's
recursive merge behavior and appends incoming messages, including duplicates.
The `add_if`/`addIf`, `has_any`/`hasAny`, `is_empty`/`isEmpty`, and
`is_not_empty`/`isNotEmpty` pairs share one implementation.

```python
errors = MessageBag()
errors.add("email", "invalid").addIf(True, "name", "required")

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

`get_messages`, `messages`, and `to_array` return defensive copies. Use
`add`, `merge`, and `forget` to update the bag. Python `str(bag)` and `to_json`
serialize the raw messages as compact JSON; `to_pretty_json` provides
indented output. The supported JSON option bits are pretty printing and
unescaped Unicode.

## Python adaptations

- Integer keys are preserved to represent numeric PHP array keys. Boolean
  keys are rejected because Python treats booleans as integers.
- Message data accepts a mapping or iterable. Iterable entries receive
  integer keys in iteration order.
- Message lists returned by public accessors are copies, consistent with
  PHP array copy-on-write behavior.
- Python JSON serialization supports the documented pretty-print and
  Unicode options; Laravel's full `json_encode` option set is not mirrored.

This API is under development. See the
[method-level compatibility inventory](/compatibility/laravel-support) for
the pinned Laravel baseline and verified status.
