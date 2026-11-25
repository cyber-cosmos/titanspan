"""Verify safe, atomic configuration cache persistence.

Cache values use JSON-compatible data only and are intentionally stored with
private file permissions because configuration can contain credentials.
"""

import json
import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from stat import S_IMODE
from typing import cast

import pytest

import titanspan.config.cache as cache_module
from titanspan.config import ConfigCache, ConfigurationCacheError

pytestmark = pytest.mark.unit
_OWNER_READ_WRITE_MODE = 0o600


def test_cache_round_trip_uses_private_permissions_and_clears_only_its_file(
    tmp_path: Path,
) -> None:
    """Persist a safe snapshot and remove only the configured cache path.

    Args:
        tmp_path: Isolated cache directory.

    Returns:
        None.
    """
    cache_path = tmp_path / "config.json"
    cache = ConfigCache(cache_path)
    values: dict[str, object] = {
        "app": {"name": "Titanspan", "debug": False},
        "queue": {"workers": 4},
        "ai": {"temperature": 0.25},
    }

    cache.write(values)

    assert cache.load() == values
    if os.name == "posix":
        assert S_IMODE(cache_path.stat().st_mode) == _OWNER_READ_WRITE_MODE
    assert list(tmp_path.iterdir()) == [cache_path]

    cache.clear()

    assert not cache_path.exists()


@pytest.mark.parametrize("value", [object(), lambda: "value", {1, 2}])
def test_cache_rejects_unsupported_values_without_writing_them(
    tmp_path: Path,
    value: object,
) -> None:
    """Reject executable or unsupported values without partial cache files.

    Args:
        tmp_path: Isolated cache directory.
        value: Unsafe or non-JSON configuration value.

    Returns:
        None.
    """
    path = tmp_path / "config.json"
    cache = ConfigCache(path)

    with pytest.raises(ConfigurationCacheError):
        cache.write({"unsafe": value})

    assert not path.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_cache_rejects_cycles_and_does_not_expose_cached_values(
    tmp_path: Path,
) -> None:
    """Reject recursive values and malformed cache data safely.

    Args:
        tmp_path: Isolated cache directory.

    Returns:
        None.
    """
    recursive: list[object] = []
    recursive.append(recursive)
    cache = ConfigCache(tmp_path / "config.json")

    with pytest.raises(ConfigurationCacheError):
        cache.write({"recursive": recursive})

    cache.path.write_text(
        '{"schema_version": 999, "secret": "do-not-leak"}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationCacheError) as error:
        cache.load()
    assert "do-not-leak" not in str(error.value)


def test_cache_clear_does_not_follow_a_symlink(tmp_path: Path) -> None:
    """Remove a symlink itself without touching the referenced external file.

    Args:
        tmp_path: Temporary root for the cache link and target.

    Returns:
        None.
    """
    target = tmp_path / "external.json"
    target.write_text("{}", encoding="utf-8")
    path = tmp_path / "cache.json"
    path.symlink_to(target)

    ConfigCache(path).clear()

    assert target.read_text(encoding="utf-8") == "{}"
    assert not path.exists()


def test_cache_returns_none_when_the_cache_file_is_absent(
    tmp_path: Path,
) -> None:
    """Treat an absent cache as a normal cache miss.

    Args:
        tmp_path: Isolated directory that does not contain a cache file.

    Returns:
        None.
    """
    assert ConfigCache(tmp_path / "missing.json").load() is None


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", 999),
        ("package_version", "incompatible"),
        ("configuration", []),
    ],
)
def test_cache_rejects_incompatible_metadata_and_root_types(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    """Reject cache envelopes with unsupported versions or root values.

    Args:
        tmp_path: Isolated cache directory.
        field: Envelope field changed for this validation case.
        replacement: Invalid value stored in the selected envelope field.

    Returns:
        None.
    """
    cache = ConfigCache(tmp_path / "cache.json")
    cache.write({"safe": True})
    payload = cast(
        "dict[str, object]",
        json.loads(cache.path.read_text(encoding="utf-8")),
    )
    payload[field] = replacement
    cache.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationCacheError):
        cache.load()


def test_cache_rejects_non_object_and_malformed_json_payloads(
    tmp_path: Path,
) -> None:
    """Reject malformed cache data without exposing parser details.

    Args:
        tmp_path: Isolated cache directory.

    Returns:
        None.
    """
    cache = ConfigCache(tmp_path / "cache.json")
    for content in ("[]", "not-json"):
        cache.path.write_text(content, encoding="utf-8")

        with pytest.raises(ConfigurationCacheError):
            cache.load()


def test_cache_rejects_symlinked_cache_files(tmp_path: Path) -> None:
    """Reject reads through a cache path that targets another file.

    Args:
        tmp_path: Temporary root for the cache link and target.

    Returns:
        None.
    """
    target = tmp_path / "external.json"
    target.write_text("{}", encoding="utf-8")
    path = tmp_path / "cache.json"
    path.symlink_to(target)

    with pytest.raises(ConfigurationCacheError, match="symbolic-link"):
        ConfigCache(path).load()


def test_cache_rejects_nonfinite_values_nested_keys_and_deep_data(
    tmp_path: Path,
) -> None:
    """Reject JSON values that lose meaning or exceed safe recursion limits.

    Args:
        tmp_path: Isolated cache directory.

    Returns:
        None.
    """
    cache = ConfigCache(tmp_path / "cache.json")
    deeply_nested: object = "value"
    for _ in range(66):
        deeply_nested = [deeply_nested]

    invalid_values: tuple[object, ...] = (
        float("inf"),
        {1: "value"},
        deeply_nested,
    )
    for value in invalid_values:
        with pytest.raises(ConfigurationCacheError):
            cache.write({"unsafe": value})

    assert not cache.path.exists()


def test_cache_write_failure_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean a temporary cache after an atomic replacement fails.

    Args:
        tmp_path: Isolated cache directory.
        monkeypatch: Fixture replacing the final atomic rename operation.

    Returns:
        None.
    """
    cache = ConfigCache(tmp_path / "cache.json")

    def fail_replace(_path: Path, _target: Path) -> Path:
        """Raise a filesystem failure at the atomic commit boundary.

        Args:
            _path: Temporary file path supplied by pathlib.
            _target: Final cache path supplied by pathlib.

        Returns:
            This callback always raises before returning.
        """
        raise PermissionError

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(ConfigurationCacheError):
        cache.write({"safe": True})

    assert tuple(tmp_path.iterdir()) == ()


def test_cache_write_reports_parent_directory_errors(
    tmp_path: Path,
) -> None:
    """Translate filesystem errors without leaking operating-system details.

    Args:
        tmp_path: Isolated cache parent.

    Returns:
        None.
    """
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")
    cache = ConfigCache(parent_file / "config.json")

    with pytest.raises(ConfigurationCacheError):
        cache.write({"safe": True})


def test_cache_clear_reports_filesystem_errors(tmp_path: Path) -> None:
    """Translate an unlink failure into a native cache exception.

    Args:
        tmp_path: Isolated path whose directory cannot be unlinked as a file.

    Returns:
        None.
    """
    directory = tmp_path / "cache.json"
    directory.mkdir()

    with pytest.raises(ConfigurationCacheError):
        ConfigCache(directory).clear()


def test_cache_load_rejects_nonfinite_values_in_valid_envelopes(
    tmp_path: Path,
) -> None:
    """Reject non-finite numbers even when the envelope is otherwise valid.

    Args:
        tmp_path: Isolated cache directory.

    Returns:
        None.
    """
    cache = ConfigCache(tmp_path / "cache.json")
    cache.write({"safe": True})
    payload = cast(
        "dict[str, object]",
        json.loads(cache.path.read_text(encoding="utf-8")),
    )
    payload["configuration"] = {"score": float("nan")}
    cache.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationCacheError):
        cache.load()


def test_cache_reports_missing_distribution_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail clearly if a cache cannot be tied to a package version.

    Args:
        tmp_path: Isolated cache directory.
        monkeypatch: Fixture replacing installed distribution metadata lookup.

    Returns:
        None.
    """

    def missing_version(_distribution: str) -> str:
        """Represent an unavailable installed distribution record.

        Args:
            _distribution: Distribution name requested by the cache writer.

        Returns:
            This callback always raises before returning.
        """
        raise PackageNotFoundError

    monkeypatch.setattr(cache_module, "version", missing_version)

    with pytest.raises(ConfigurationCacheError, match="metadata"):
        ConfigCache(tmp_path / "cache.json").write({"safe": True})
