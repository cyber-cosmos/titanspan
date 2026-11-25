"""Verify Laravel-inspired process environment access and dotenv writing.

The cases cover value normalization, adapter lifecycle, and safe file edits.
"""

from __future__ import annotations

import importlib
import math
from contextvars import ContextVar
from typing import TYPE_CHECKING, cast

import pytest

from titanspan.support import Env, env

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

_REQUIRED_ENV_ERROR_PATTERN = (
    r"Environment variable \[TITANSPAN_REQUIRED_VALUE\] has no value\."
)
_SCOPE_FAILURE = "scope failure"


@pytest.fixture(autouse=True)
def isolate_environment_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset adapter settings for each test context.

    Returns:
        None after the active registry has been isolated.
    """
    module = importlib.import_module("titanspan.support.env")
    test_state: ContextVar[object | None] = ContextVar(
        "titanspan_environment_unit_test",
        default=None,
    )
    monkeypatch.setattr(module, "_ENV_STATE", test_state)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("(TRUE)", True),
        ("false", False),
        ("(False)", False),
        ("empty", ""),
        ("(empty)", ""),
        ("null", None),
        ("(NULL)", None),
        ('"null"', "null"),
        ("'false'", "false"),
        ('prefix"value"', 'prefix"value"'),
        ("", ""),
    ],
)
def test_get_normalizes_dotenv_tokens_and_balanced_quotes(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: object,
) -> None:
    """Convert Laravel dotenv literals while preserving other strings.

    Args:
        monkeypatch: Fixture that restores process environment changes.
        raw: The source text assigned to the environment variable.
        expected: The normalized value returned by Env.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_ENV_CASE", raw)

    assert Env.get("TITANSPAN_ENV_CASE") == expected
    assert env("TITANSPAN_ENV_CASE") == expected


@pytest.mark.unit
def test_get_resolves_default_only_when_variable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call a deferred default only when no non-null value exists.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    calls: list[str] = []

    def default() -> str:
        """Record and return a lazy default value.

        Returns:
            The fallback text.
        """
        calls.append("default")
        return "fallback"

    monkeypatch.setenv("TITANSPAN_ENV_VALUE", "present")
    assert Env.get("TITANSPAN_ENV_VALUE", default) == "present"
    assert calls == []

    monkeypatch.delenv("TITANSPAN_ENV_VALUE")
    assert Env.get("TITANSPAN_ENV_VALUE", default) == "fallback"
    assert calls == ["default"]

    monkeypatch.setenv("TITANSPAN_ENV_VALUE", "null")
    assert Env.get("TITANSPAN_ENV_VALUE", default) == "fallback"
    assert calls == ["default", "default"]


@pytest.mark.unit
def test_get_or_fail_returns_values_and_reports_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return required values and raise on missing or null values.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_REQUIRED_VALUE", "available")
    assert Env.get_or_fail("TITANSPAN_REQUIRED_VALUE") == "available"
    assert Env.getOrFail("TITANSPAN_REQUIRED_VALUE") == "available"

    monkeypatch.delenv("TITANSPAN_REQUIRED_VALUE")
    with pytest.raises(RuntimeError, match=_REQUIRED_ENV_ERROR_PATTERN):
        Env.get_or_fail("TITANSPAN_REQUIRED_VALUE")

    monkeypatch.setenv("TITANSPAN_REQUIRED_VALUE", "(null)")
    with pytest.raises(RuntimeError):
        Env.get_or_fail("TITANSPAN_REQUIRED_VALUE")


@pytest.mark.unit
def test_repository_prefers_process_environment_and_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read live process values through a stable repository instance.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_ENV_SOURCE", "process")
    repository = Env.get_repository()

    assert Env.getRepository() is repository
    assert repository.get("TITANSPAN_ENV_SOURCE") == "process"

    monkeypatch.setenv("TITANSPAN_ENV_SOURCE", "updated")
    assert repository.get("TITANSPAN_ENV_SOURCE") == "updated"


@pytest.mark.unit
def test_named_adapters_are_lazy_replaceable_and_fallback_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve adapter values lazily and replace named adapter factories.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    calls: list[str] = []
    first: Mapping[str, str | None] = {"CUSTOM_VALUE": "first"}
    second: Mapping[str, str | None] = {"CUSTOM_VALUE": "second"}

    def create_first() -> Mapping[str, str | None]:
        """Create the first adapter and record factory calls.

        Returns:
            The first adapter mapping.
        """
        calls.append("first")
        return first

    Env.extend(create_first, name="test-source")
    repository = Env.get_repository()
    assert Env.get("CUSTOM_VALUE") == "first"
    assert Env.get_repository() is repository
    assert calls == ["first"]

    first_values = cast("dict[str, str | None]", first)
    first_values["CUSTOM_VALUE"] = "mutated"
    assert Env.get("CUSTOM_VALUE") == "first"

    Env.extend(lambda: second, name="test-source")
    assert Env.get("CUSTOM_VALUE") == "second"
    assert calls == ["first"]

    Env.extend(lambda: {"ANOTHER_CUSTOM_VALUE": "next"}, name="other-source")
    assert Env.get("ANOTHER_CUSTOM_VALUE") == "next"

    monkeypatch.setenv("CUSTOM_VALUE", "process")
    assert Env.get("CUSTOM_VALUE") == "process"


@pytest.mark.unit
def test_disable_putenv_skips_process_environment_but_keeps_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disable native environment reads without disabling extensions.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.setenv("TITANSPAN_NATIVE_VALUE", "native")
    Env.extend(lambda: {"TITANSPAN_CUSTOM_VALUE": "adapter"})
    Env.disable_putenv()

    assert Env.get("TITANSPAN_NATIVE_VALUE") is None
    assert Env.get("TITANSPAN_CUSTOM_VALUE") == "adapter"

    Env.enablePutenv()
    assert Env.get("TITANSPAN_NATIVE_VALUE") == "native"
    Env.disablePutenv()
    assert Env.get("TITANSPAN_NATIVE_VALUE") is None
    Env.enable_putenv()


@pytest.mark.unit
def test_write_variables_matches_laravel_grouping_and_overwrite_rules(
    tmp_path: Path,
) -> None:
    """Group new variables by prefix and replace blank values safely.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text(
        "APP_NAME=Titanspan\n"
        "APP_ENV=local\n"
        "APP_DEBUG=true\n"
        "\n"
        "DB_CONNECTION=sqlite\n"
        "DB_HOST=",
        encoding="utf-8",
    )

    Env.write_variables(
        {
            "APP_MODE": "safe",
            "DB_HOST": "127:0:0:1",
            "DB_PORT": 5432,
            "BRAND_LABEL": "new value",
        },
        path,
    )

    assert path.read_text(encoding="utf-8") == (
        "APP_NAME=Titanspan\n"
        "APP_ENV=local\n"
        "APP_DEBUG=true\n"
        "APP_MODE=safe\n"
        "\n"
        "DB_CONNECTION=sqlite\n"
        'DB_HOST="127:0:0:1"\n'
        "DB_PORT=5432\n"
        "\n"
        'BRAND_LABEL="new value"'
    )

    Env.write_variables({"APP_MODE": "changed"}, path)
    assert "APP_MODE=safe" in path.read_text(encoding="utf-8")

    Env.writeVariables({"APP_MODE": "changed"}, path, overwrite=True)
    assert "APP_MODE=changed" in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_write_variable_preserves_newline_style_and_trailing_newline(
    tmp_path: Path,
) -> None:
    """Preserve a file's newline convention when adding a variable.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_bytes(b"APP_NAME=Titanspan\r\n")

    Env.writeVariable("APP_ENV", "testing", path)

    assert path.read_bytes() == b"APP_NAME=Titanspan\r\nAPP_ENV=testing\r\n"


@pytest.mark.unit
def test_write_variable_escapes_quotes_and_backslashes(tmp_path: Path) -> None:
    """Quote special values without creating additional assignments.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text("APP_NAME=Titanspan\n", encoding="utf-8")

    Env.write_variable("APP_MESSAGE", 'It\'s a "safe" path\\file', path)

    assert path.read_text(encoding="utf-8") == (
        "APP_NAME=Titanspan\nAPP_MESSAGE='It\\'s a \"safe\" path\\\\file'\n"
    )


@pytest.mark.unit
def test_write_variable_keeps_an_existing_unquoted_equivalent(
    tmp_path: Path,
) -> None:
    """Avoid rewriting an equivalent raw assignment when overwriting.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text("APP_HOST=127:0:0:1\n", encoding="utf-8")

    Env.write_variable("APP_HOST", "127:0:0:1", path, overwrite=True)

    assert path.read_text(encoding="utf-8") == "APP_HOST=127:0:0:1\n"


@pytest.mark.unit
def test_write_variable_accepts_empty_and_scalar_values(tmp_path: Path) -> None:
    """Serialize supported scalars using dotenv-friendly text values.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")

    Env.write_variables(
        {
            "APP_EMPTY": "",
            "APP_COUNT": 4,
            "APP_RATIO": 1.25,
            "APP_ENABLED": True,
            "APP_DISABLED": False,
            "APP_UNSET": None,
        },
        path,
    )

    contents = path.read_text(encoding="utf-8")
    assert "APP_EMPTY=" in contents
    assert "APP_COUNT=4" in contents
    assert "APP_RATIO=1.25" in contents
    assert "APP_ENABLED=1" in contents
    assert "APP_DISABLED=" in contents
    assert "APP_UNSET=" in contents


@pytest.mark.unit
def test_write_variable_rejects_missing_files_invalid_keys_and_injection(
    tmp_path: Path,
) -> None:
    """Fail closed when the target or dotenv assignment is invalid.

    Args:
        tmp_path: Isolated temporary directory for the env file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text("APP_NAME=Titanspan\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="does not exist"):
        Env.write_variable("APP_NAME", "value", tmp_path / "missing")
    with pytest.raises(ValueError, match="environment variable name"):
        Env.write_variable("APP_NAME\nINJECTED", "value", path)
    with pytest.raises(ValueError, match="single line"):
        Env.write_variable("APP_VALUE", "first\nINJECTED=true", path)

    assert path.read_text(encoding="utf-8") == "APP_NAME=Titanspan\n"


@pytest.mark.unit
def test_environment_validation_rejects_invalid_runtime_values(
    tmp_path: Path,
) -> None:
    """Reject invalid values even when callers bypass type annotations.

    Args:
        tmp_path: Isolated temporary directory for the dotenv file.

    Returns:
        None.
    """
    path = tmp_path / ".env"
    path.write_text("APP_NAME=Titanspan\n", encoding="utf-8")

    with pytest.raises(TypeError, match="key must be a string"):
        Env.get(cast("str", None))
    with pytest.raises(TypeError, match="factory must be callable"):
        Env.extend(cast("Callable[[], Mapping[str, str | None]]", None))
    with pytest.raises(TypeError, match="name must be non-empty"):
        Env.extend(dict, name="")

    invalid_adapter = cast(
        "Callable[[], Mapping[str, str | None]]",
        lambda: cast("object", []),
    )
    Env.extend(invalid_adapter)
    with pytest.raises(TypeError, match="adapters must return"):
        Env.get_repository()

    with pytest.raises(TypeError, match="variables must be a mapping"):
        Env.write_variables(
            cast("Mapping[str, str | int | float | bool | None]", []),
            path,
        )
    with pytest.raises(TypeError, match="path_to_file must be text"):
        Env.write_variables({}, cast("str | Path", 5))
    with pytest.raises(TypeError, match="overwrite must be a boolean"):
        Env.write_variables({}, path, overwrite=cast("bool", 1))

    with pytest.raises(ValueError, match="must be finite"):
        Env.write_variable("APP_NUMBER", math.inf, path)
    with pytest.raises(TypeError, match="must be strings or scalar"):
        Env.write_variable("APP_OBJECT", cast("str", object()), path)
    with pytest.raises(ValueError, match="single line"):
        Env.write_variable("APP_NUL", "first\x00second", path)

    assert path.read_text(encoding="utf-8") == "APP_NAME=Titanspan\n"


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid_values",
    [{1: "wrong key"}, {"APP_VALUE": 2}],
)
def test_adapter_rejects_non_string_keys_and_values(
    invalid_values: object,
) -> None:
    """Require custom adapters to contain string names and values.

    Returns:
        None.
    """

    def adapter() -> Mapping[str, str | None]:
        """Return malformed values under the declared adapter contract.

        Returns:
            The invalid mapping cast to the expected adapter type.
        """
        return cast("Mapping[str, str | None]", invalid_values)

    Env.extend(adapter)

    with pytest.raises(TypeError, match="adapters must return"):
        Env.get_repository()


@pytest.mark.unit
def test_required_read_rejects_invalid_repository_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard the required-read contract against malformed adapters.

    Args:
        monkeypatch: Fixture for replacing environment lookup temporarily.

    Returns:
        None.
    """

    def invalid_get(_cls: type[Env], _key: str) -> object:
        """Return an unsupported value to exercise defensive validation.

        Args:
            _cls: Environment utility class passed by the class method.
            _key: Requested environment variable name.

        Returns:
            An unsupported integer value.
        """
        return 5

    monkeypatch.setattr(Env, "get", classmethod(invalid_get))
    with pytest.raises(TypeError, match="must be a string or boolean"):
        Env.get_or_fail("APP_VALUE")


@pytest.mark.unit
def test_using_scopes_an_environment_mapping_and_restores_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose file-backed values only within a restored context scope.

    Args:
        monkeypatch: Fixture that restores process environment changes.

    Returns:
        None.
    """
    monkeypatch.delenv("TITANSPAN_SCOPED_ENV", raising=False)

    def fail_within_environment_scope() -> None:
        """Raise after observing the scoped environment value.

        Returns:
            None.
        """
        with Env.using({"TITANSPAN_SCOPED_ENV": "file-value"}):
            assert Env.get("TITANSPAN_SCOPED_ENV") == "file-value"
            raise RuntimeError(_SCOPE_FAILURE)

    with pytest.raises(RuntimeError, match=_SCOPE_FAILURE):
        fail_within_environment_scope()

    assert Env.get("TITANSPAN_SCOPED_ENV") is None
