"""Verify trusted configuration discovery and source precedence.

Configuration files are isolated in temporary directories and loaded through
the same explicit loader used by application initialization.
"""

import os
from pathlib import Path
from typing import NoReturn

import pytest

import titanspan.config.loader as loader_module
from titanspan.config import ConfigLoader, ConfigurationLoadError

pytestmark = pytest.mark.unit
_EXPECTED_RETRY_ATTEMPTS = 3


def test_loader_merges_defaults_and_loads_python_using_scoped_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load a trusted Python file without mutating process environment.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that restores process environment.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (tmp_path / ".env").write_text("APP_NAME=dotenv-name\n")
    (config_directory / "app.py").write_text(
        "from titanspan.support import env\n"
        "config = {\n"
        "    'name': env('APP_NAME', 'default-name'),\n"
        "    'nested': {'application': True},\n"
        "}\n"
    )
    monkeypatch.delenv("APP_NAME", raising=False)

    loader = ConfigLoader(
        tmp_path,
        package_defaults={
            "app": {"nested": {"package": True}},
        },
    )
    repository = loader.load()

    assert repository.get("app.name") == "dotenv-name"
    assert repository.get("app.nested") == {
        "package": True,
        "application": True,
    }
    assert "APP_NAME" not in os.environ


def test_loader_gives_process_environment_precedence_over_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prefer process values while keeping dotenv scoped to loading.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that restores process environment.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (tmp_path / ".env").write_text("APP_NAME=dotenv-name\n")
    (config_directory / "app.py").write_text(
        "from titanspan.support import env\n"
        "config = {'name': env('APP_NAME', 'default-name')}\n"
    )
    monkeypatch.setenv("APP_NAME", "process-name")

    repository = ConfigLoader(tmp_path).load()

    assert repository.string("app.name") == "process-name"


def test_loader_reads_json_and_toml_with_deterministic_namespaces(
    tmp_path: Path,
) -> None:
    """Parse supported data files without executing their contents.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "logging.json").write_text(
        '{"level": "info", "enabled": true}'
    )
    (config_directory / "queue.toml").write_text(
        "workers = 4\n[retry]\nattempts = 3\n"
    )

    repository = ConfigLoader(tmp_path).load()

    assert repository.get("logging.level") == "info"
    assert repository.get("queue.retry.attempts") == _EXPECTED_RETRY_ATTEMPTS


def test_loader_rejects_duplicate_namespaces_and_invalid_exports(
    tmp_path: Path,
) -> None:
    """Reject ambiguous file sources and non-mapping Python exports.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / "app.py").write_text("config = {}\n")
    (config_directory / "app.json").write_text("{}")

    with pytest.raises(ConfigurationLoadError, match="ambiguous"):
        ConfigLoader(tmp_path).load()

    (config_directory / "app.json").unlink()
    (config_directory / "app.py").write_text("config = []\n")

    with pytest.raises(ConfigurationLoadError):
        ConfigLoader(tmp_path).load()


def test_loader_rejects_configuration_symlinks_outside_application_root(
    tmp_path: Path,
) -> None:
    """Prevent trusted-source discovery from escaping the config directory.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    outside = tmp_path.parent / f"outside-{tmp_path.name}.py"
    outside.write_text("config = {}\n")
    (config_directory / "linked.py").symlink_to(outside)

    try:
        with pytest.raises(ConfigurationLoadError, match="outside"):
            ConfigLoader(tmp_path).load()
    finally:
        outside.unlink(missing_ok=True)


def test_loader_rejects_a_config_directory_that_is_a_file(
    tmp_path: Path,
) -> None:
    """Reject a config path that cannot contain trusted source files.

    Args:
        tmp_path: Isolated application root.

    Returns:
        None.
    """
    (tmp_path / "config").write_text("not a directory", encoding="utf-8")

    with pytest.raises(ConfigurationLoadError, match="not a directory"):
        ConfigLoader(tmp_path).load()


def test_loader_rejects_a_config_directory_symlink_outside_the_root(
    tmp_path: Path,
) -> None:
    """Keep configuration discovery within the selected application root.

    Args:
        tmp_path: Temporary parent for the application and external folder.

    Returns:
        None.
    """
    application = tmp_path / "application"
    application.mkdir()
    external = tmp_path / "external-config"
    external.mkdir()
    (application / "config").symlink_to(external, target_is_directory=True)

    with pytest.raises(ConfigurationLoadError, match="outside"):
        ConfigLoader(application).load()


def test_loader_rejects_invalid_dotenv_paths_and_namespaces(
    tmp_path: Path,
) -> None:
    """Validate selected environment paths and package namespace names.

    Args:
        tmp_path: Isolated application root and external path parent.

    Returns:
        None.
    """
    outside_env = tmp_path.parent / f"outside-{tmp_path.name}.env"

    with pytest.raises(ValueError, match="inside base_path"):
        ConfigLoader(tmp_path, environment_file=outside_env)

    loader = ConfigLoader(tmp_path)
    with pytest.raises(ValueError, match="identifier"):
        loader.register_defaults("not-valid", {})


def test_loader_rejects_dotenv_symlinks(
    tmp_path: Path,
) -> None:
    """Reject a dotenv file that resolves through a symbolic link.

    Args:
        tmp_path: Isolated application root and dotenv target parent.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    outside = tmp_path / "selected-secrets.env"
    outside.write_text("APP_NAME=secret", encoding="utf-8")
    (tmp_path / ".env").symlink_to(outside)

    try:
        with pytest.raises(ConfigurationLoadError, match="symlinks"):
            ConfigLoader(tmp_path).load()
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("filename", "contents"),
    [
        ("bad-name.json", "{}"),
        ("app.json", "{"),
        ("app.toml", "[invalid"),
        ("app.py", "config = {1: 'invalid'}\n"),
    ],
)
def test_loader_rejects_invalid_namespaces_and_source_contents(
    tmp_path: Path,
    filename: str,
    contents: str,
) -> None:
    """Reject malformed trusted sources without exposing their contents.

    Args:
        tmp_path: Isolated application root.
        filename: Source file name under test.
        contents: Malformed or invalid configuration contents.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (config_directory / filename).write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigurationLoadError):
        ConfigLoader(tmp_path).load()


def test_loader_can_skip_dotenv_loading_without_changing_process_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave dotenv values unused when the application disables that source.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture that removes any inherited test value.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    (tmp_path / ".env").write_text("APP_NAME=dotenv", encoding="utf-8")
    (config_directory / "app.py").write_text(
        "from titanspan.support import env\n"
        "config = {'name': env('APP_NAME', 'default')}\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APP_NAME", raising=False)

    repository = ConfigLoader(
        tmp_path,
        load_environment_file=False,
    ).load()

    assert repository.string("app.name") == "default"


def test_loader_translates_config_directory_iteration_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate permission failures while listing trusted config files.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture replacing pathlib directory iteration.

    Returns:
        None.
    """
    (tmp_path / "config").mkdir()
    loader = ConfigLoader(tmp_path)

    def fail_iteration(_path: Path) -> NoReturn:
        """Simulate a directory listing permission error.

        Args:
            _path: Directory that the loader attempts to enumerate.

        Returns:
            This callback always raises before returning.
        """
        raise PermissionError

    monkeypatch.setattr(Path, "iterdir", fail_iteration)

    with pytest.raises(ConfigurationLoadError, match="PermissionError"):
        loader.load()


def test_loader_translates_config_directory_resolution_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate failures resolving the trusted config directory path.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture replacing resolution for the selected directory.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    loader = ConfigLoader(tmp_path)
    original_resolve = Path.resolve

    def fail_config_resolution(path: Path, strict: bool = False) -> Path:
        """Fail only when the loader resolves its config directory.

        Args:
            path: Filesystem path currently being resolved.
            strict: Whether the original path must exist.

        Returns:
            The original resolution result for all other paths.
        """
        if path == config_directory and strict:
            raise PermissionError
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_config_resolution)

    with pytest.raises(ConfigurationLoadError, match="PermissionError"):
        loader.load()


def test_loader_translates_config_file_resolution_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate a source file that disappears during trusted discovery.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture replacing resolution for one source file.

    Returns:
        None.
    """
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    source = config_directory / "app.json"
    source.write_text("{}", encoding="utf-8")
    loader = ConfigLoader(tmp_path)
    original_resolve = Path.resolve

    def fail_source_resolution(path: Path, strict: bool = False) -> Path:
        """Fail only when the loader resolves the selected config file.

        Args:
            path: Filesystem path currently being resolved.
            strict: Whether the original path must exist.

        Returns:
            The original resolution result for all other paths.
        """
        if path == source and strict:
            raise PermissionError
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_source_resolution)

    with pytest.raises(ConfigurationLoadError, match="PermissionError"):
        loader.load()


def test_loader_translates_dotenv_parser_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate dotenv reader errors without exposing raw parser details.

    Args:
        tmp_path: Isolated application root.
        monkeypatch: Fixture replacing the dotenv parser.

    Returns:
        None.
    """
    (tmp_path / ".env").write_text("APP_NAME=Titanspan", encoding="utf-8")

    def fail_dotenv_read(
        _path: Path,
        *,
        encoding: str,
    ) -> dict[str, str | None]:
        """Simulate a dotenv source decoding failure.

        Args:
            _path: Selected dotenv file.
            encoding: Requested file encoding.

        Returns:
            This callback always raises before returning.
        """
        del encoding
        raise UnicodeError

    monkeypatch.setattr(loader_module, "dotenv_values", fail_dotenv_read)

    with pytest.raises(ConfigurationLoadError, match="UnicodeError"):
        ConfigLoader(tmp_path).load()
