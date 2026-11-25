"""Verify configuration precedence and explicit cache lifecycle.

The manager composes settings, package defaults, application files, cache
snapshots, and bootstrap overrides without creating global state.
"""

from pathlib import Path

import pytest

from titanspan.config import (
    ConfigManager,
    ConfigurationCacheError,
    Settings,
    SettingsValidationError,
)

pytestmark = pytest.mark.unit
_BOOTSTRAP_WORKER_COUNT = 4
_EXPLICIT_APPLICATION_WORKER_COUNT = 8
_APPLICATION_FILE_WORKER_COUNT = 6
_QUEUE_FILE_WORKER_COUNT = 3
_SETTINGS_QUEUE_WORKER_COUNT = 5
_QUEUE_PREFETCH_COUNT = 4


class ApplicationSettings(Settings):
    """Declare custom fields that should join the repository source order.

    Attributes:
        application: Additional settings in the application namespace.
        queue: Partial queue namespace provided by the environment schema.
    """

    application: dict[str, str | int]
    queue: dict[str, str | int]


class _UnstructuredSettings(Settings):
    """Represent settings that permit non-text keys at runtime.

    Attributes:
        values: Mapping checked at the configuration path boundary.
    """

    values: dict[object, object]


def test_manager_applies_settings_and_bootstrap_overrides_in_order(
    tmp_path: Path,
) -> None:
    """Apply explicit settings and bootstrap values above app files.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "app.py").write_text(
        "config = {'name': 'file-name', 'debug': False}\n",
        encoding="utf-8",
    )
    manager = ConfigManager(
        tmp_path,
        settings=Settings(app_name="settings-name", debug=True),
        package_defaults={"queue": {"workers": 2}},
    )

    repository = manager.load(
        overrides={
            "app.name": "bootstrap-name",
            "queue.workers": _BOOTSTRAP_WORKER_COUNT,
        }
    )

    assert repository.string("app.name") == "bootstrap-name"
    assert repository.boolean("app.debug") is True
    assert repository.integer("queue.workers") == _BOOTSTRAP_WORKER_COUNT


def test_manager_cache_uses_json_snapshot_until_explicitly_cleared(
    tmp_path: Path,
) -> None:
    """Read a valid cache, then return to file discovery after clearing it.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    config_file = config_directory / "app.json"
    config_file.write_text('{"name": "before"}', encoding="utf-8")
    manager = ConfigManager(tmp_path)

    cache_path = manager.cache_configuration()
    config_file.write_text('{"name": "after"}', encoding="utf-8")

    assert manager.load().string("app.name") == "before"
    assert cache_path.is_file()

    manager.clear_cache()

    assert not cache_path.exists()
    assert manager.load().string("app.name") == "after"


def test_valid_cache_bypasses_environment_settings_until_fresh_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a valid cache before reading changed environment settings.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Environment fixture for an invalid settings value.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "app.json").write_text(
        '{"name": "cached", "debug": false}',
        encoding="utf-8",
    )
    ConfigManager(tmp_path).cache_configuration()
    monkeypatch.setenv("TITANSPAN_DEBUG", "not-a-boolean")
    manager = ConfigManager(tmp_path)

    assert manager.load().string("app.name") == "cached"
    with pytest.raises(SettingsValidationError):
        manager.validate()


def test_manager_rejects_nonserializable_values_when_caching(
    tmp_path: Path,
) -> None:
    """Reject executable settings rather than stringify them in the cache.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "app.py").write_text(
        "config = {'factory': lambda: 'runtime'}\n",
        encoding="utf-8",
    )
    manager = ConfigManager(tmp_path)

    with pytest.raises(ConfigurationCacheError):
        manager.cache_configuration()


def test_manager_validates_from_fresh_sources_without_writing_cache(
    tmp_path: Path,
) -> None:
    """Load and validate source files without creating a cache artifact.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "app.toml").write_text(
        'name = "valid"\n',
        encoding="utf-8",
    )
    manager = ConfigManager(tmp_path)

    repository = manager.validate()

    assert repository.string("app.name") == "valid"
    assert not manager.cache_path.exists()


def test_manager_resolves_relative_cache_path_and_settings_over_cache(
    tmp_path: Path,
) -> None:
    """Anchor relative cache paths and apply explicit settings above cache.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    first_manager = ConfigManager(
        tmp_path,
        cache_path="runtime/config.json",
    )
    assert first_manager.cache_path == tmp_path / "runtime" / "config.json"
    first_manager.cache_configuration()
    second_manager = ConfigManager(
        tmp_path,
        settings=Settings(app_name="Explicit application"),
        cache_path="runtime/config.json",
    )

    loaded = second_manager.load()

    assert loaded.string("app.name") == "Explicit application"


def test_manager_projects_explicit_custom_and_nested_settings(
    tmp_path: Path,
) -> None:
    """Merge explicitly supplied settings into their config namespaces.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "application.py").write_text(
        f"config = {{'worker_count': {_APPLICATION_FILE_WORKER_COUNT}}}\n",
        encoding="utf-8",
    )
    (config_directory / "queue.py").write_text(
        "config = {'name': 'redis', "
        f"'workers': {_QUEUE_FILE_WORKER_COUNT}, "
        f"'prefetch': {_QUEUE_PREFETCH_COUNT}}}\n",
        encoding="utf-8",
    )
    settings = ApplicationSettings(
        application={"worker_count": _EXPLICIT_APPLICATION_WORKER_COUNT},
        queue={"workers": _SETTINGS_QUEUE_WORKER_COUNT},
    )

    repository = ConfigManager(tmp_path, settings=settings).validate()

    assert (
        repository.integer("application.worker_count")
        == _EXPLICIT_APPLICATION_WORKER_COUNT
    )
    assert repository.get("queue") == {
        "name": "redis",
        "workers": _SETTINGS_QUEUE_WORKER_COUNT,
        "prefetch": _QUEUE_PREFETCH_COUNT,
    }


def test_manager_rejects_non_string_nested_settings_keys(
    tmp_path: Path,
) -> None:
    """Reject mapping keys that cannot form a configuration path.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    settings = _UnstructuredSettings(values={1: "private-value"})

    with pytest.raises(TypeError, match="mapping keys must be strings"):
        ConfigManager(tmp_path, settings=settings).validate()
