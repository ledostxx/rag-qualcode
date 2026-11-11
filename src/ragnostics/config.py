"""Project configuration.

A ragnostics project is a YAML file describing which adapter to use, where the
benchmark data lives, and where annotations are stored. Relative paths are
resolved against the config file's directory.

The ``adapter`` value is kept as the raw string: a built-in name such as
``grains``, or ``<file>.py:<ClassName>``, which ``ragnostics.adapters``
resolves against the project file's folder.

The optional ``llm`` mapping is passed through. Keys the app reads: ``model``,
``temperature`` and ``base_url`` (an OpenAI-compatible endpoint; without it the
client's own ``OPENAI_BASE_URL`` handling applies).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SampleConfig:
    per_source_type: int = 20
    seed: int = 42


@dataclass
class ProjectConfig:
    name: str
    adapter: str
    data: dict[str, Any]
    annotations_path: Path
    sample: SampleConfig = field(default_factory=SampleConfig)
    # Accepted but unused since D-004 (open coding is pure free text); kept so
    # existing project files still load.
    seed_codes: list[str] = field(default_factory=list)
    # Model settings for the axial phase, e.g. {"model": "gpt-4o-mini",
    # "base_url": "http://localhost:11434/v1"}.
    # Never holds a key: credentials come from the environment or the session only.
    llm: dict[str, Any] = field(default_factory=dict)
    config_path: Path | None = None


def _resolve(value: Any, base: Path) -> Any:
    """Resolve string values that look like paths relative to the config dir."""
    if not isinstance(value, str):
        return value
    looks_like_path = "/" in value or value.startswith((".", "~")) or (base / value).exists()
    if not looks_like_path:
        return value
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (base / p).resolve()
    return str(p)


def load_project(path: str | Path) -> ProjectConfig:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Project config not found: {path}\n"
            "Create one from ragnostics.example.yaml or pass a path: ragnostics <config.yaml>"
        )
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    for key in ("name", "adapter", "data", "annotations"):
        if key not in raw:
            raise ValueError(f"Project config {path} is missing required key: '{key}'")

    base = path.parent
    data = {k: _resolve(v, base) for k, v in dict(raw["data"]).items()}

    annotations = Path(_resolve(str(raw["annotations"]), base))

    sample_raw = raw.get("sample") or {}
    sample = SampleConfig(
        per_source_type=int(sample_raw.get("per_source_type", 20)),
        seed=int(sample_raw.get("seed", 42)),
    )

    return ProjectConfig(
        name=str(raw["name"]),
        adapter=str(raw["adapter"]),
        data=data,
        annotations_path=annotations,
        sample=sample,
        seed_codes=[str(c) for c in raw.get("seed_codes") or []],
        llm=dict(raw.get("llm") or {}),
        config_path=path,
    )
