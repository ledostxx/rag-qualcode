"""Project, adapter and record loading shared by the app and ``ragnostics validate``.

Deliberately free of Streamlit imports.
"""

from __future__ import annotations

from pathlib import Path

from .adapters import _is_file_spec
from .adapters.base import Adapter
from .config import ProjectConfig
from .schema import Record, validate_records


def adapter_spec(cfg: ProjectConfig) -> tuple[str, Path]:
    """The adapter value from the project file and the project file's folder."""
    base_dir = cfg.config_path.parent if cfg.config_path else Path.cwd()
    return cfg.adapter, base_dir


def adapter_mtime(cfg: ProjectConfig) -> float | None:
    """Modification time of a file-path adapter, ``None`` for built-in adapters
    (or when the file does not exist)."""
    spec, base_dir = adapter_spec(cfg)
    if not _is_file_spec(spec):
        return None
    path = Path(spec.rpartition(":")[0]).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    try:
        return path.resolve().stat().st_mtime
    except OSError:
        return None


def load_records(adapter: Adapter) -> tuple[list[Record], list[str]]:
    """Call ``adapter.load()`` and return the records plus the problems found by
    ``validate_records()``. Exceptions raised by ``load()`` propagate."""
    records = adapter.load()
    return records, validate_records(records)
