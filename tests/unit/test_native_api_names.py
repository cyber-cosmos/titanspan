"""Verify the public API uses one canonical Python naming style.

The checks cover retired duplicate names across the implemented core
components without constraining private Python integration hooks.
"""

import tomllib
from inspect import Signature, signature
from pathlib import Path
from typing import cast

import pytest

from titanspan.config import Repository
from titanspan.container import Container
from titanspan.facades import Config, Log
from titanspan.logging import Logger, LogManager
from titanspan.support import (
    Arr,
    Env,
    Fluent,
    Lottery,
    Macroable,
    MessageBag,
    Str,
    Stringable,
    Timebox,
    Uri,
)

pytestmark = pytest.mark.unit

PROTECTED_NAMING_RULES = frozenset(
    {
        "N802",
        "N803",
        "N806",
        "N818",
        "N815",
        "N816",
        "A001",
        "A002",
        "A003",
    }
)
_EXPECTED_NAMING_EXCEPTIONS = {
    "src/titanspan/logging/drivers/standard.py": frozenset({"N802", "N803"}),
    "tests/integration/logging/test_webhook.py": frozenset({"A002"}),
    "src/titanspan/validation/exceptions.py": frozenset({"N818"}),
}


def _toml_table(value: object) -> dict[str, object]:
    """Validate and type a table from the repository TOML configuration.

    Args:
        value: A parsed TOML value whose runtime type should be a table.

    Returns:
        The table with values treated as dynamically parsed objects.

    Raises:
        AssertionError: If the value is not a TOML table.
    """
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _toml_list(value: object) -> list[object] | None:
    """Validate and type a list from the repository TOML configuration.

    Args:
        value: A parsed TOML value whose runtime type may be a list.

    Returns:
        The list with values treated as dynamically parsed objects, or
        ``None`` when the value is not a list.
    """
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def test_ruff_enforces_native_names_with_reviewed_exceptions() -> None:
    """Keep Ruff naming rules active with only required override names.

    The local lint target also checks these families with inline suppressions
    ignored, so a ``noqa`` comment cannot restore non-native spellings.
    """
    project_root = Path(__file__).resolve().parents[2]
    pyproject_path = project_root / "pyproject.toml"
    configuration = _toml_table(
        tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    )
    tool = _toml_table(configuration.get("tool"))
    ruff = _toml_table(tool.get("ruff"))
    lint = _toml_table(ruff.get("lint"))

    selected_rules = _toml_list(lint.get("select"))
    assert selected_rules is not None
    assert "N" in selected_rules
    assert "A" in selected_rules

    def suppresses_protected_rule(value: object) -> bool:
        """Identify a rule selector that suppresses naming enforcement.

        Args:
            value: One Ruff rule selector from a global or scoped ignore.

        Returns:
            Whether the selector disables a protected rule or family.
        """
        if not isinstance(value, str):
            return False
        return value in {"N", "A"} or any(
            protected.startswith(value) or value.startswith(protected)
            for protected in PROTECTED_NAMING_RULES
        )

    ignored_rules: list[object] = []
    for option in ("ignore", "extend-ignore"):
        values = _toml_list(lint.get(option, []))
        if values is not None:
            ignored_rules.extend(values)

    naming_exceptions: dict[str, set[str]] = {}
    for option in ("per-file-ignores", "extend-per-file-ignores"):
        values_by_path = lint.get(option, {})
        if isinstance(values_by_path, dict):
            typed_values_by_path = cast(
                "dict[str, object]",
                values_by_path,
            )
            for path, raw_values in typed_values_by_path.items():
                values = _toml_list(raw_values)
                if values is None:
                    continue
                protected_values = {
                    value
                    for value in values
                    if isinstance(value, str)
                    and suppresses_protected_rule(value)
                }
                if protected_values:
                    naming_exceptions.setdefault(path, set()).update(
                        protected_values
                    )

    assert not any(map(suppresses_protected_rule, ignored_rules))
    assert {
        path: frozenset(rules) for path, rules in naming_exceptions.items()
    } == _EXPECTED_NAMING_EXCEPTIONS

    makefile_path = project_root / "Makefile"
    makefile = makefile_path.read_text(encoding="utf-8")
    assert "ruff check --select N,A --ignore-noqa ." in makefile


def test_public_apis_expose_only_canonical_spellings() -> None:
    """Keep removed duplicate names out of the public API.

    The canonical snake_case methods remain covered by their component tests.
    This regression check ensures callers see one public spelling only.
    """
    obsolete_names: tuple[tuple[type[object], str, str], ...] = (
        (Arr, "crossJoin", "cross_join"),
        (Str, "startsWith", "starts_with"),
        (Stringable, "toString", "to_string"),
        (Container, "makeAsync", "make_async"),
        (Container, "bindIf", "bind_if"),
        (Container, "resolve", "make"),
        (Container, "resolve_async", "make_async"),
        (Container, "build", "make"),
        (Container, "build_async", "make_async"),
        (Repository, "getMany", "get_many"),
        (LogManager, "withContext", "with_context"),
        (Config, "getMany", "get_many"),
        (Log, "withContext", "with_context"),
        (MessageBag, "toJson", "to_json"),
        (Macroable, "hasMacro", "has_macro"),
        (Timebox, "earlyReturn", "early_return"),
        (Lottery, "determine_results_normally", "determine_result_normally"),
        (LogManager, "driver", "channel"),
        (LogManager, "get", "channel"),
        (LogManager, "resolve", "channel"),
        (LogManager, "forget_driver", "forget_channel"),
        (LogManager, "get_default_driver", "get_default_channel"),
        (LogManager, "set_default_driver", "set_default_channel"),
        (Log, "get_default_driver", "get_default_channel"),
        (Log, "set_default_driver", "set_default_channel"),
        (Log, "driver", "channel"),
        (Logger, "write", "log"),
        (Env, "enable_putenv", "enable_process_environment"),
        (Env, "disable_putenv", "disable_process_environment"),
        (Uri, "to_response", "redirect"),
    )

    for api, alias, canonical in obsolete_names:
        assert not hasattr(api, alias), f"{api.__name__}.{alias} remains public"
        assert hasattr(api, canonical), (
            f"{api.__name__}.{canonical} is not the canonical API"
        )


def test_string_apis_omit_ignored_encoding_and_language_parameters() -> None:
    """Keep ignored external encoding and locale options out of APIs.

    Returns:
        None.
    """
    string_signatures: tuple[tuple[str, Signature], ...] = (
        ("Str.ascii", signature(Str.ascii)),
        ("Str.convert_case", signature(Str.convert_case)),
        ("Str.length", signature(Str.length)),
        ("Str.position", signature(Str.position)),
        ("Str.slug", signature(Str.slug)),
        ("Str.substr", signature(Str.substr)),
        ("Str.mask", signature(Str.mask)),
        ("Stringable.ascii", signature(Stringable.ascii)),
        ("Stringable.convert_case", signature(Stringable.convert_case)),
        ("Stringable.length", signature(Stringable.length)),
        ("Stringable.position", signature(Stringable.position)),
        ("Stringable.slug", signature(Stringable.slug)),
        ("Stringable.substr", signature(Stringable.substr)),
        (
            "Fluent.to_json",
            signature(Fluent[str, object].to_json),
        ),
    )

    for method_name, method_signature in string_signatures:
        parameters = method_signature.parameters
        assert "encoding" not in parameters
        assert "language" not in parameters, method_name

    assert "options" not in string_signatures[-1][1].parameters
