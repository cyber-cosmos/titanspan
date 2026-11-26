"""Discover trusted application listeners and validate JSON manifests.

Cached metadata never contains live callables or container resources.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from titanspan.events.exceptions import EventDiscoveryError
from titanspan.events.listener import (
    ListenerReference,
    declared_events,
    is_subscriber,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from types import ModuleType
    from typing import NoReturn

    from titanspan.contracts.events import EventSelector
    from titanspan.events.dispatcher import NativeEventDispatcher

_MANIFEST_VERSION = 1
_MANIFEST_ERROR = (
    "The event discovery manifest is invalid or stale; rebuild the cache."
)
_CACHE_CLEAR_ERROR = "Unable to clear the event cache."
_ANNOTATION_ERROR = "Unable to resolve an event listener annotation."
_UNTRUSTED_SELECTOR_ERROR = (
    "Cached class event selectors must use trusted modules."
)
_ABSOLUTE_MODULE_ERROR = "Discovery modules must use absolute trusted names."
_CACHE_SOURCE_ERROR = "Cached event modules require source files."
_MODULE_HASH_ERROR = "Unable to hash an event module."
_CACHE_WRITE_ERROR = "Unable to write the event cache."


@dataclass(frozen=True, slots=True)
class DiscoveryEntry:
    """Describe one listener or subscriber without retaining live instances.

    Attributes:
        module: Trusted importable application module.
        qualname: Stable module member name.
        method: Optional listener method selected from a class.
        selectors: Event types or names declared by this target.
        is_subscriber: Whether startup registers this class as a subscriber.
    """

    module: str
    qualname: str
    method: str | None
    selectors: tuple[EventSelector, ...]
    is_subscriber: bool = False

    @property
    def key(self) -> str:
        """Return a deterministic deduplication key for this entry.

        The key distinguishes listener metadata without serializing the target.
        """
        method = "" if self.method is None else self.method
        return f"{self.module}:{self.qualname}:{method}"


async def discover_events(
    dispatcher: NativeEventDispatcher,
    modules: Sequence[str],
    *,
    manifest_path: Path | None = None,
) -> tuple[DiscoveryEntry, ...]:
    """Register listeners from explicitly trusted application modules.

    Args:
        dispatcher: Application-owned native event dispatcher.
        modules: Ordered module names selected by application configuration.
        manifest_path: Optional validated JSON cache path.

    Returns:
        Discovered listener and subscriber descriptors in stable order.

    Raises:
        EventDiscoveryError: If a module, annotation, or manifest is invalid.
    """
    names = tuple(dict.fromkeys(modules))
    if not names:
        return ()
    imported = _import_modules(names)
    if manifest_path is None:
        entries = _inspect_modules(imported)
    elif manifest_path.exists():
        entries = _load_manifest(manifest_path, names, imported)
    else:
        entries = _inspect_modules(imported)
        write_event_manifest(manifest_path, names, entries, imported)

    for entry in entries:
        if not dispatcher.claim_discovery(entry.key):
            continue
        target = _resolve_member(imported[entry.module], entry.qualname)
        if entry.is_subscriber:
            await dispatcher.subscribe_async(target)
            continue
        listener_target: object = target
        if entry.method is not None:
            listener_target = ListenerReference(target, entry.method)
        dispatcher.listen(entry.selectors, listener_target)
    return entries


def inspect_events(modules: Sequence[str]) -> tuple[DiscoveryEntry, ...]:
    """Inspect trusted modules without registering discovered listeners.

    Args:
        modules: Ordered module names selected by application configuration.

    Returns:
        Deterministic listener and subscriber descriptors.

    Raises:
        EventDiscoveryError: If a module import or annotation fails.
    """
    return _inspect_modules(_import_modules(tuple(dict.fromkeys(modules))))


def cache_events(modules: Sequence[str], path: Path) -> Path:
    """Write a deterministic JSON discovery manifest atomically.

    Args:
        modules: Trusted modules whose registrations are described.
        path: Destination path selected by application configuration.

    Returns:
        The manifest destination path.

    Raises:
        EventDiscoveryError: If entries cannot be safely represented.
    """
    names = tuple(dict.fromkeys(modules))
    imported = _import_modules(names)
    entries = _inspect_modules(imported)
    write_event_manifest(path, names, entries, imported)
    return path


def clear_event_cache(path: Path) -> None:
    """Remove one configured event discovery manifest if it exists.

    Args:
        path: Manifest path selected by application configuration.

    Raises:
        EventDiscoveryError: If the path cannot be removed safely.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise EventDiscoveryError(_CACHE_CLEAR_ERROR) from error


def write_event_manifest(
    path: Path,
    modules: Sequence[str],
    entries: Sequence[DiscoveryEntry],
    imported: Mapping[str, ModuleType],
) -> None:
    """Serialize stable import metadata and source hashes as JSON.

    Args:
        path: Destination path for the generated manifest.
        modules: Trusted modules included in the manifest.
        entries: Listener metadata discovered from those modules.
        imported: Already imported trusted module objects.

    Raises:
        EventDiscoveryError: If metadata is not importable or writing fails.
    """
    body: dict[str, object] = {
        "version": _MANIFEST_VERSION,
        "modules": [
            {"name": name, "sha256": _module_digest(imported[name])}
            for name in modules
        ],
        "entries": [_serialize_entry(entry, modules) for entry in entries],
    }
    serialized_body = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    document = dict(body)
    document["sha256"] = hashlib.sha256(
        serialized_body.encode("utf-8"),
    ).hexdigest()
    _atomic_write(path, document)


def _inspect_modules(
    modules: Mapping[str, ModuleType],
) -> tuple[DiscoveryEntry, ...]:
    """Build descriptors from module-owned functions, classes, and methods.

    Args:
        modules: Explicitly trusted imported application modules.

    Returns:
        Stable descriptors ordered by module and qualified member name.

    Raises:
        EventDiscoveryError: If listener annotations cannot be resolved.
    """
    entries: list[DiscoveryEntry] = []
    for module_name in sorted(modules):
        module = modules[module_name]
        for member_name, member in sorted(vars(module).items()):
            if member_name.startswith("_"):
                continue
            if getattr(member, "__module__", None) != module_name:
                continue
            qualname = getattr(member, "__qualname__", member_name)
            if inspect.isfunction(member):
                selectors = declared_events(member) or _parameter_events(member)
                if selectors:
                    entries.append(
                        DiscoveryEntry(module_name, qualname, None, selectors),
                    )
            elif inspect.isclass(member):
                if is_subscriber(member):
                    entries.append(
                        DiscoveryEntry(
                            module_name,
                            qualname,
                            None,
                            (),
                            is_subscriber=True,
                        ),
                    )
                    continue
                class_selectors = declared_events(member)
                if class_selectors:
                    entries.append(
                        DiscoveryEntry(
                            module_name,
                            qualname,
                            None,
                            class_selectors,
                        ),
                    )
                    continue
                entries.extend(
                    _class_listener_entries(module_name, qualname, member),
                )
    unique = {entry.key: entry for entry in entries}
    return tuple(unique[key] for key in sorted(unique))


def _class_listener_entries(
    module: str,
    qualname: str,
    target: type[object],
) -> tuple[DiscoveryEntry, ...]:
    """Find declared handle methods and resolve event type annotations.

    Args:
        module: Trusted module defining the class.
        qualname: Stable class member name.
        target: Listener class inspected by discovery.

    Returns:
        Entries for handle methods with declared event selectors.
    """
    entries: list[DiscoveryEntry] = []
    for method_name, method in sorted(vars(target).items()):
        if method_name != "handle" and not method_name.startswith("handle_"):
            continue
        callback = _unwrap_method(method)
        if callback is None:
            continue
        selectors = declared_events(callback) or _parameter_events(callback)
        if selectors:
            entries.append(
                DiscoveryEntry(module, qualname, method_name, selectors),
            )
    return tuple(entries)


def _unwrap_method(value: object) -> Callable[..., object] | None:
    """Return the function behind ordinary, static, or class methods.

    Args:
        value: Class member collected from its own namespace.

    Returns:
        Underlying method function or ``None`` for unsupported descriptors.
    """
    if isinstance(value, classmethod):
        return None
    if isinstance(value, staticmethod):
        value = cast("object", value.__func__)
    if inspect.isfunction(value):
        return cast("Callable[..., object]", value)
    return None


def _parameter_events(
    callback: Callable[..., object],
) -> tuple[EventSelector, ...]:
    """Extract class selectors from the first listener payload annotation.

    Args:
        callback: Listener function or method under inspection.

    Returns:
        Event classes inferred from one class or union annotation.

    Raises:
        EventDiscoveryError: If forward references cannot be resolved.
    """
    try:
        parameters = tuple(inspect.signature(callback).parameters.values())
        hints = get_type_hints(callback, include_extras=True)
    except (NameError, TypeError, ValueError) as error:
        raise EventDiscoveryError(_ANNOTATION_ERROR) from error
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and parameter.name not in {"self", "cls"}
    ]
    if not positional:
        return ()
    annotation = hints.get(positional[0].name)
    return _class_annotations(annotation)


def _class_annotations(annotation: object) -> tuple[EventSelector, ...]:
    """Return concrete event classes from ordinary or union annotations.

    Args:
        annotation: Evaluated first parameter annotation.

    Returns:
        Unique class selectors supported by runtime matching.
    """
    origin = get_origin(annotation)
    if origin is not None:
        if origin is Annotated:
            arguments = get_args(annotation)
            return _class_annotations(arguments[0]) if arguments else ()
        return tuple(
            selector
            for argument in get_args(annotation)
            for selector in _class_annotations(argument)
        )
    if not isinstance(annotation, type):
        return ()
    if annotation in {object, str, int, float, bool, bytes, type(None)}:
        return ()
    return (annotation,)


def _serialize_entry(
    entry: DiscoveryEntry,
    modules: Sequence[str],
) -> dict[str, object]:
    """Convert one descriptor to JSON-safe import metadata.

    Args:
        entry: Discovered registration descriptor.
        modules: Trusted module names allowed during cache loading.

    Returns:
        JSON object containing only strings, booleans, and arrays.

    Raises:
        EventDiscoveryError: If a class selector is outside trusted modules.
    """
    selectors: list[dict[str, str]] = []
    for selector in entry.selectors:
        if isinstance(selector, str):
            selectors.append({"name": selector})
            continue
        if selector.__module__ not in modules:
            raise EventDiscoveryError(_UNTRUSTED_SELECTOR_ERROR)
        selectors.append(
            {
                "module": selector.__module__,
                "qualname": selector.__qualname__,
            },
        )
    return {
        "module": entry.module,
        "qualname": entry.qualname,
        "method": entry.method or "",
        "subscriber": entry.is_subscriber,
        "selectors": selectors,
    }


def _load_manifest(
    path: Path,
    modules: Sequence[str],
    imported: Mapping[str, ModuleType],
) -> tuple[DiscoveryEntry, ...]:
    """Validate checksum, configured modules, source hashes, and entries.

    Args:
        path: JSON manifest selected by application configuration.
        modules: Trusted configured module names in canonical order.
        imported: Already imported trusted modules.

    Returns:
        Reconstructed descriptors without deserializing Python objects.

    Raises:
        EventDiscoveryError: If data is malformed, incompatible, or stale.
    """
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            _raise_invalid_manifest()
        document = cast("dict[str, object]", loaded)
        checksum = document.pop("sha256", None)
        if not isinstance(checksum, str):
            _raise_invalid_manifest()
        actual = hashlib.sha256(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        ).hexdigest()
        if checksum != actual or document.get("version") != _MANIFEST_VERSION:
            _raise_invalid_manifest()
        expected_modules = [
            {"name": name, "sha256": _module_digest(imported[name])}
            for name in modules
        ]
        if document.get("modules") != expected_modules:
            _raise_invalid_manifest()
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list):
            _raise_invalid_manifest()
        entries = cast("list[object]", raw_entries)
        return tuple(
            _deserialize_entry(raw, modules, imported) for raw in entries
        )
    except EventDiscoveryError:
        raise
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise EventDiscoveryError(_MANIFEST_ERROR) from error


def _deserialize_entry(
    raw: object,
    modules: Sequence[str],
    imported: Mapping[str, ModuleType],
) -> DiscoveryEntry:
    """Validate and resolve one manifest descriptor from trusted modules.

    Args:
        raw: Untrusted JSON value from the manifest file.
        modules: Configured trusted module names.
        imported: Imported trusted modules resolved independently of JSON.

    Returns:
        Descriptor with importable class selectors and target metadata.

    Raises:
        EventDiscoveryError: If fields or referenced members are invalid.
    """
    if not isinstance(raw, dict):
        _raise_invalid_manifest()
    descriptor = cast("dict[str, object]", raw)
    module = descriptor.get("module")
    qualname = descriptor.get("qualname")
    method = descriptor.get("method")
    subscriber_value = descriptor.get("subscriber")
    serialized_selectors = descriptor.get("selectors")
    if (
        not isinstance(module, str)
        or module not in modules
        or not isinstance(qualname, str)
        or not isinstance(method, str)
        or not isinstance(subscriber_value, bool)
        or not isinstance(serialized_selectors, list)
    ):
        _raise_invalid_manifest()
    _resolve_member(imported[module], qualname)
    selectors: list[EventSelector] = []
    items = cast("list[object]", serialized_selectors)
    for item in items:
        if not isinstance(item, dict):
            _raise_invalid_manifest()
        selector_item = cast("dict[str, object]", item)
        name = selector_item.get("name")
        if isinstance(name, str):
            selectors.append(name)
            continue
        event_module = selector_item.get("module")
        event_qualname = selector_item.get("qualname")
        if (
            not isinstance(event_module, str)
            or event_module not in modules
            or not isinstance(event_qualname, str)
        ):
            _raise_invalid_manifest()
        event_type = _resolve_member(imported[event_module], event_qualname)
        if not isinstance(event_type, type):
            _raise_invalid_manifest()
        selectors.append(event_type)
    if not subscriber_value and not selectors:
        _raise_invalid_manifest()
    return DiscoveryEntry(
        module,
        qualname,
        method or None,
        tuple(selectors),
        subscriber_value,
    )


def _import_modules(names: Sequence[str]) -> dict[str, ModuleType]:
    """Import only configured module names and preserve configured order.

    Args:
        names: Module names explicitly trusted by application configuration.

    Returns:
        Imported modules keyed by their configured names.

    Raises:
        EventDiscoveryError: If any configured import fails.
    """
    imported: dict[str, ModuleType] = {}
    for name in names:
        if not name or name.startswith("."):
            raise EventDiscoveryError(_ABSOLUTE_MODULE_ERROR)
        try:
            imported[name] = importlib.import_module(name)
        except ImportError as error:
            message = f"Unable to import configured event module {name!r}."
            raise EventDiscoveryError(message) from error
    return imported


def _resolve_member(module: ModuleType, qualname: str) -> object:
    """Resolve a dotted member without importing a module from the manifest.

    Args:
        module: Already imported configured module.
        qualname: Dotted member path stored by discovery.

    Returns:
        Module-owned class or function object.

    Raises:
        EventDiscoveryError: If a member is missing or local-only.
    """
    current: object = module
    parts = qualname.split(".")
    if "<locals>" in parts:
        _raise_invalid_manifest()
    try:
        for part in parts:
            current = getattr(current, part)
    except AttributeError as error:
        raise EventDiscoveryError(_MANIFEST_ERROR) from error
    return current


def _module_digest(module: ModuleType) -> str:
    """Hash trusted source bytes so stale manifests fail closed.

    Args:
        module: Imported trusted application module.

    Returns:
        SHA-256 hex digest of the defining Python source file.

    Raises:
        EventDiscoveryError: If the module has no readable source file.
    """
    filename = getattr(module, "__file__", None)
    if not isinstance(filename, str):
        raise EventDiscoveryError(_CACHE_SOURCE_ERROR)
    try:
        source = Path(filename).read_bytes()
    except OSError as error:
        raise EventDiscoveryError(_MODULE_HASH_ERROR) from error
    return hashlib.sha256(source).hexdigest()


def _atomic_write(path: Path, document: Mapping[str, object]) -> None:
    """Write one UTF-8 JSON manifest by replacing a temporary file.

    Args:
        path: Destination file selected by trusted configuration.
        document: JSON-safe deterministic manifest mapping.

    Raises:
        EventDiscoveryError: If the destination cannot be written.
    """
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        temporary.replace(path)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise EventDiscoveryError(_CACHE_WRITE_ERROR) from error


def _raise_invalid_manifest() -> NoReturn:
    """Raise the canonical cache failure for malformed manifest data.

    Invalid cache data fails closed with a native event error.
    """
    raise EventDiscoveryError(_MANIFEST_ERROR)


__all__ = [
    "DiscoveryEntry",
    "cache_events",
    "clear_event_cache",
    "discover_events",
    "inspect_events",
]
