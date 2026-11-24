"""Read process environment values and update dotenv files.

The public methods follow Laravel's Support Env API. Python's environment
mapping and immutable adapter snapshots replace Dotenv repositories and PHP's
separate process environment adapters.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

type EnvironmentScalar = str | int | float | bool | None
type EnvironmentAdapter = Callable[[], Mapping[str, str | None]]
type _EnvironmentAdapterEntry = tuple[str | None, EnvironmentAdapter]
_ENV_KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SAFE_UNQUOTED_VALUE_PATTERN = re.compile(r"[A-Za-z0-9]+\Z")
_QUOTED_VALUE_MIN_LENGTH = 2
_MISSING_FILE_ERROR = "The file [{path}] does not exist."
_GET_OR_FAIL_ERROR = "Environment variable [{key}] has no value."
_ENV_KEY_ERROR = "environment variable name must be a valid identifier"
_ENV_VALUE_ERROR = "environment values must be strings or scalar values"
_ENV_SINGLE_LINE_ERROR = "environment values must be single line strings"
_ENV_FINITE_NUMBER_ERROR = "environment numeric values must be finite"
_ENV_ADAPTER_ERROR = "environment adapters must return a string mapping"
_ENV_ADAPTER_FACTORY_ERROR = "environment adapter factory must be callable"
_ENV_ADAPTER_NAME_ERROR = "environment adapter name must be non-empty text"
_ENV_KEY_TYPE_ERROR = "environment variable key must be a string"
_ENV_VARIABLES_TYPE_ERROR = "variables must be a mapping"
_ENV_PATH_TYPE_ERROR = "path_to_file must be text or pathlib.Path"
_ENV_OVERWRITE_TYPE_ERROR = "overwrite must be a boolean"
_ENV_VALUE_RETURN_ERROR = "environment value must be a string or boolean"


class _EnvironmentRepository:
    """Read process values before configured custom mappings.

    The native source remains live so changes made through ``os.environ`` are
    visible after repository construction. Custom mappings are copied into
    immutable snapshots when the repository is created.
    """

    def __init__(
        self,
        use_process_environment: bool,
        adapters: tuple[EnvironmentAdapter, ...],
    ) -> None:
        """Build an immutable repository for the active context.

        Args:
            use_process_environment: Whether ``os.environ`` is consulted.
            adapters: Factories for additional fallback mappings.

        Raises:
            TypeError: If an adapter returns a non-string mapping.
        """
        self._use_process_environment = use_process_environment
        self._adapters = tuple(
            self._snapshot_adapter(adapter) for adapter in adapters
        )

    def get(self, key: str) -> str | None:
        """Return the first non-null value for a key.

        Args:
            key: Environment variable name to read.

        Returns:
            The raw string value, or ``None`` when no adapter has it.
        """
        if self._use_process_environment:
            value = os.environ.get(key)
            if value is not None:
                return value
        for adapter in self._adapters:
            value = adapter.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _snapshot_adapter(
        factory: EnvironmentAdapter,
    ) -> Mapping[str, str | None]:
        """Create and validate an immutable adapter mapping.

        Args:
            factory: A callback that produces one adapter mapping.

        Returns:
            An immutable copy of the adapter's key-value pairs.

        Raises:
            TypeError: If the factory or its mapping values are invalid.
        """
        values = factory()
        if not isinstance(cast("object", values), Mapping):
            raise TypeError(_ENV_ADAPTER_ERROR)
        snapshot: dict[str, str | None] = {}
        for key, value in values.items():
            if not isinstance(cast("object", key), str) or (
                value is not None and not isinstance(cast("object", value), str)
            ):
                raise TypeError(_ENV_ADAPTER_ERROR)
            snapshot[key] = value
        return MappingProxyType(snapshot)


@dataclass(frozen=True, slots=True)
class _EnvironmentState:
    """Hold immutable adapter settings for one execution context.

    Attributes:
        use_process_environment: Whether reads consult ``os.environ``.
        adapter_factories: Ordered custom adapter factories.
        repository: Cached repository built from the current settings.
    """

    use_process_environment: bool = True
    adapter_factories: tuple[_EnvironmentAdapterEntry, ...] = ()
    repository: _EnvironmentRepository | None = None


_ENV_STATE: ContextVar[_EnvironmentState | None] = ContextVar(
    "titanspan_environment_state",
    default=None,
)


def _environment_state() -> _EnvironmentState:
    """Return the active context's immutable environment settings.

    Returns:
        The current settings or a new default state.
    """
    state = _ENV_STATE.get()
    if state is None:
        state = _EnvironmentState()
        _ENV_STATE.set(state)
    return state


class Env:
    """Provide typed access to environment values and dotenv files.

    Read process values through ``os.environ``, with optional custom mapping
    adapters. File writes are explicit and restricted to valid variable names
    and single-line scalar values. Application settings remain owned by
    Pydantic Settings.

    Notes:
        Adapter configuration is immutable and context-local. Python has no
        separate ``putenv`` lookup table, so the compatibility switch controls
        whether the native ``os.environ`` mapping is consulted.
    """

    @classmethod
    def enable_putenv(cls) -> None:
        """Enable reads from Python's process environment mapping.

        Returns:
            None.
        """
        state = _environment_state()
        _ENV_STATE.set(
            replace(
                state,
                use_process_environment=True,
                repository=None,
            )
        )

    @classmethod
    def disable_putenv(cls) -> None:
        """Disable reads from Python's process environment mapping.

        Custom adapters remain available after this change.

        Returns:
            None.
        """
        state = _environment_state()
        _ENV_STATE.set(
            replace(
                state,
                use_process_environment=False,
                repository=None,
            )
        )

    @classmethod
    def extend(
        cls,
        callback: EnvironmentAdapter,
        name: str | None = None,
    ) -> None:
        """Register or replace a custom environment mapping factory.

        Args:
            callback: A factory returning a mapping of string values.
            name: Optional name used to replace a prior adapter.

        Raises:
            TypeError: If the factory is not callable or the name is invalid.
        """
        if not callable(callback):
            raise TypeError(_ENV_ADAPTER_FACTORY_ERROR)
        if name is not None and (
            not isinstance(cast("object", name), str) or not name
        ):
            raise TypeError(_ENV_ADAPTER_NAME_ERROR)

        state = _environment_state()
        adapters = list(state.adapter_factories)
        if name is None:
            adapters.append((None, callback))
        else:
            for index, (existing_name, _) in enumerate(adapters):
                if existing_name == name:
                    adapters[index] = (name, callback)
                    break
            else:
                adapters.append((name, callback))

        _ENV_STATE.set(
            replace(
                state,
                adapter_factories=tuple(adapters),
                repository=None,
            )
        )

    @classmethod
    def get_repository(cls) -> _EnvironmentRepository:
        """Return the cached repository for the active context.

        Returns:
            A repository that reads process and custom environment values.

        Raises:
            TypeError: If a configured adapter factory returns invalid data.
        """
        state = _environment_state()
        if state.repository is not None:
            return state.repository

        adapters = tuple(callback for _, callback in state.adapter_factories)
        repository = _EnvironmentRepository(
            state.use_process_environment,
            adapters,
        )
        _ENV_STATE.set(replace(state, repository=repository))
        return repository

    @classmethod
    def get(
        cls,
        key: str,
        default: object | Callable[[], object] = None,
    ) -> object:
        """Read and normalize a variable, resolving a lazy default if absent.

        Args:
            key: Environment variable name to read.
            default: Constant or zero-argument fallback callback.

        Returns:
            A normalized boolean, string, null, or fallback value.

        Raises:
            TypeError: If ``key`` is not a string.
        """
        if not isinstance(cast("object", key), str):
            raise TypeError(_ENV_KEY_TYPE_ERROR)

        raw_value = cls.get_repository().get(key)
        if raw_value is None:
            return default() if callable(default) else default
        normalized = cls._normalize(raw_value)
        if normalized is None:
            return default() if callable(default) else default
        return normalized

    @classmethod
    def get_or_fail(cls, key: str) -> str | bool:
        """Return a required environment value or raise an error.

        Args:
            key: Environment variable name to read.

        Returns:
            A normalized string or boolean value.

        Raises:
            RuntimeError: If the variable is unset or has a null literal.
            TypeError: If ``key`` is not a string.
        """
        value = cls.get(key)
        if value is None:
            raise RuntimeError(_GET_OR_FAIL_ERROR.format(key=key))
        if isinstance(value, (str, bool)):
            return value
        raise TypeError(_ENV_VALUE_RETURN_ERROR)

    @classmethod
    def write_variables(
        cls,
        variables: Mapping[str, EnvironmentScalar],
        path_to_file: str | Path,
        overwrite: bool = False,
    ) -> None:
        """Write multiple dotenv values while preserving existing groups.

        Args:
            variables: Ordered variable names and scalar values to write.
            path_to_file: Existing dotenv file to update.
            overwrite: Whether populated existing assignments are replaced.

        Raises:
            FileNotFoundError: If the destination does not exist.
            TypeError: If inputs are not mappings, paths, or booleans.
            ValueError: If a key or value cannot be written safely.
            OSError: If reading or writing the destination fails.
        """
        if not isinstance(cast("object", variables), Mapping):
            raise TypeError(_ENV_VARIABLES_TYPE_ERROR)
        if not isinstance(cast("object", path_to_file), (str, Path)):
            raise TypeError(_ENV_PATH_TYPE_ERROR)
        if type(overwrite) is not bool:
            raise TypeError(_ENV_OVERWRITE_TYPE_ERROR)

        normalized = tuple(
            (cls._validate_key(key), cls._serialize_value(value))
            for key, value in variables.items()
        )
        path = Path(path_to_file)
        if not path.exists():
            raise FileNotFoundError(
                _MISSING_FILE_ERROR.format(path=path_to_file)
            )

        with path.open("r", encoding="utf-8", newline="") as env_file:
            contents = env_file.read()

        newline = cls._newline_for(contents)
        trailing_newline = bool(newline and contents.endswith(newline))
        lines = contents.split(newline) if newline else [contents]
        if trailing_newline:
            # Keep the terminal newline separate while edits are inserted.
            lines.pop()

        for key, value_variants in normalized:
            lines = cls._add_variable_to_lines(
                key,
                value_variants,
                lines,
                overwrite,
            )

        updated = newline.join(lines)
        if trailing_newline:
            updated += newline
        with path.open("w", encoding="utf-8", newline="") as env_file:
            env_file.write(updated)

    @classmethod
    def write_variable(
        cls,
        key: str,
        value: EnvironmentScalar,
        path_to_file: str | Path,
        overwrite: bool = False,
    ) -> None:
        """Write one dotenv value using the multi-variable writer.

        Args:
            key: Variable name to write.
            value: Scalar value to serialize.
            path_to_file: Existing dotenv file to update.
            overwrite: Whether a populated value may be replaced.

        Raises:
            FileNotFoundError: If the destination does not exist.
            TypeError: If inputs have unsupported types.
            ValueError: If the key or value cannot be written safely.
            OSError: If reading or writing the destination fails.
        """
        cls.write_variables(
            {key: value},
            path_to_file,
            overwrite=overwrite,
        )

    @staticmethod
    def _normalize(value: str) -> str | bool | None:
        """Apply Laravel dotenv literal and balanced-quote conversions.

        Args:
            value: Raw environment text.

        Returns:
            A converted boolean, null, empty string, or original text.
        """
        normalized = value.lower()
        if normalized in {"true", "(true)"}:
            return True
        if normalized in {"false", "(false)"}:
            return False
        if normalized in {"empty", "(empty)"}:
            return ""
        if normalized in {"null", "(null)"}:
            return None
        if (
            len(value) >= _QUOTED_VALUE_MIN_LENGTH
            and value[0] in {"'", '"'}
            and value[-1] == value[0]
        ):
            return value[1:-1]
        return value

    @staticmethod
    def _validate_key(key: object) -> str:
        """Require a portable identifier for a dotenv assignment.

        Args:
            key: Proposed environment variable name.

        Returns:
            The validated name.

        Raises:
            ValueError: If the name could alter dotenv assignment structure.
        """
        if not isinstance(key, str) or not _ENV_KEY_PATTERN.fullmatch(key):
            raise ValueError(_ENV_KEY_ERROR)
        return key

    @staticmethod
    def _serialize_value(value: object) -> tuple[str, ...]:
        """Convert a scalar to safely quoted dotenv assignment text.

        Args:
            value: Text or scalar value to serialize.

        Returns:
            Quoted and unquoted assignment values in compatibility order.

        Raises:
            ValueError: If text contains newlines, NUL, or non-finite numbers.
            TypeError: If the value is not a supported scalar.
        """
        if value is None:
            return ("",)
        if type(value) is bool:
            # PHP string concatenation writes true as "1" and false as "".
            raw_value = "1" if value else ""
            return (raw_value,)
        if isinstance(value, int):
            raw_value = str(value)
            return (raw_value,)
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(_ENV_FINITE_NUMBER_ERROR)
            return (str(value),)
        if not isinstance(value, str):
            raise TypeError(_ENV_VALUE_ERROR)
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError(_ENV_SINGLE_LINE_ERROR)
        if value == "":
            return ("",)
        if _SAFE_UNQUOTED_VALUE_PATTERN.fullmatch(value):
            return (value,)
        quote = "'" if '"' in value else '"'
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace('"', '\\"')
        excluded_quote = '"' if quote == "'" else "'"
        escaped = escaped.replace("\\" + excluded_quote, excluded_quote)
        return (f"{quote}{escaped}{quote}", value)

    @staticmethod
    def _newline_for(contents: str) -> str:
        """Choose the existing file's first newline sequence.

        Args:
            contents: Current dotenv text.

        Returns:
            CRLF, LF, CR, or the platform default when no newline exists.
        """
        match = re.search(r"\r\n|\n|\r", contents)
        return match.group(0) if match is not None else os.linesep

    @classmethod
    def _add_variable_to_lines(
        cls,
        key: str,
        value_variants: tuple[str, ...],
        lines: list[str],
        overwrite: bool,
    ) -> list[str]:
        """Insert or replace one assignment while retaining prefix groups.

        Args:
            key: Validated variable name.
            value_variants: Equivalent serialized forms for the value.
            lines: Current dotenv lines without a terminal newline marker.
            overwrite: Whether existing populated assignments are replaced.

        Returns:
            A new line list containing the assignment when applicable.
        """
        line_variations = tuple(
            dict.fromkeys(f"{key}={value}" for value in value_variants)
        )
        line_to_add = line_variations[0]
        prefix = f"{key.split('_', maxsplit=1)[0]}_"
        last_prefix_index = -1

        for index, line in enumerate(lines):
            if line.startswith(prefix):
                last_prefix_index = index
            if line in line_variations:
                return lines
            if line == f"{key}=" or line.startswith(f"{key}="):
                if line == f"{key}=" or overwrite:
                    updated = list(lines)
                    updated[index] = line_to_add
                    return updated
                return lines

        updated = list(lines)
        if last_prefix_index == -1:
            if updated and updated[-1] != "":
                updated.append("")
            updated.append(line_to_add)
            return updated

        updated.insert(last_prefix_index + 1, line_to_add)
        return updated

    enablePutenv = enable_putenv
    disablePutenv = disable_putenv
    getRepository = get_repository
    getOrFail = get_or_fail
    writeVariables = write_variables
    writeVariable = write_variable
