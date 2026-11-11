"""Adapter registry and loader.

A system is connected by subclassing :class:`~rag_qualcode.adapters.base.Adapter`.
The project file names the adapter either as a built-in name (for example
``grains``) or as ``<file>.py:<ClassName>``, which is imported from that file.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from .base import Adapter
from .grains import GrainsAdapter

_REGISTRY: dict[str, type[Adapter]] = {}


class AdapterLoadError(Exception):
    """An adapter could not be resolved, imported or validated.

    The message names the file and class (or the built-in name) concerned.
    """


def register_adapter(cls: type[Adapter]) -> type[Adapter]:
    """Register a built-in adapter class under its ``name``."""
    _REGISTRY[cls.name] = cls
    return cls


register_adapter(GrainsAdapter)


def _is_file_spec(spec: str) -> bool:
    head, sep, _ = spec.rpartition(":")
    return bool(sep) and head.endswith(".py")


def _load_from_file(spec: str, base_dir: Path | None) -> type[Adapter]:
    file_part, _, class_name = spec.rpartition(":")
    path = Path(file_part).expanduser()
    if not path.is_absolute():
        path = (base_dir if base_dir is not None else Path.cwd()) / path
    path = path.resolve()

    if not path.is_file():
        raise AdapterLoadError(f"Adapter file not found: {path} (looking for class '{class_name}')")
    if not class_name:
        raise AdapterLoadError(f"No class name given for adapter file {path}")

    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    module_name = f"rag_qualcode_user_adapter_{path.stem}_{digest}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise AdapterLoadError(f"Cannot import adapter file {path} (class '{class_name}')")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise AdapterLoadError(
            f"Error while running adapter file {path} (class '{class_name}'): "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise AdapterLoadError(f"Class '{class_name}' not found in adapter file {path}")
    if not (isinstance(cls, type) and issubclass(cls, Adapter)):
        raise AdapterLoadError(
            f"'{class_name}' in {path} is not a subclass of rag_qualcode.adapters.base.Adapter"
        )
    return cls


def resolve_adapter_class(spec: str, base_dir: Path | None = None) -> type[Adapter]:
    """Resolve an adapter spec to a class.

    ``spec`` is either ``<file>.py:<ClassName>`` (the file is resolved against
    ``base_dir``, or the current folder when ``None``) or the name of a built-in
    adapter. Raises :class:`AdapterLoadError` on every failure.
    """
    if _is_file_spec(spec):
        return _load_from_file(spec, base_dir)
    if spec not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise AdapterLoadError(
            f"Unknown adapter '{spec}'. Built-in adapters: {known}. "
            "To use your own, write '<file>.py:<ClassName>'."
        )
    return _REGISTRY[spec]


def get_adapter(name: str, data: dict[str, Any], base_dir: Path | None = None) -> Adapter:
    """Return a fresh adapter instance for ``name`` (built-in name or file spec)."""
    return resolve_adapter_class(name, base_dir)(data)


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)
