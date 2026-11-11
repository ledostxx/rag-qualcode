"""Streamlit entry point. Launched via the ``qualcode`` CLI (preferred) or:

    QUALCODE_PROJECT=path/to/qualcode.yaml streamlit run src/rag_qualcode/app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from rag_qualcode.adapters import resolve_adapter_class
from rag_qualcode.adapters.base import Adapter
from rag_qualcode.config import ProjectConfig, load_project
from rag_qualcode.loading import adapter_mtime, adapter_spec, load_records
from rag_qualcode.schema import Record
from rag_qualcode.storage import AnnotationStore
from rag_qualcode.ui import axial_coding, open_coding

st.set_page_config(page_title="rag-qualcode", page_icon="🧬", layout="wide")


def _project_path() -> str:
    return os.environ.get("QUALCODE_PROJECT", "qualcode.yaml")


def _cache_key(cfg: ProjectConfig) -> str:
    """Changes when any configured data file or the adapter file changes,
    invalidating the cache."""
    parts = []
    for key, value in sorted(cfg.data.items()):
        p = Path(str(value))
        parts.append(f"{key}={value}:{p.stat().st_mtime if p.exists() else 0}")
    parts.append(f"adapter:{adapter_mtime(cfg)}")
    return "|".join(parts)


@st.cache_resource(show_spinner=False)
def _adapter_class(spec: str, base_dir: str, mtime: float | None) -> type[Adapter]:
    """The adapter class, cached per adapter spec and file modification time."""
    return resolve_adapter_class(spec, Path(base_dir))


@st.cache_data(show_spinner="Loading benchmark records ...")
def _load_records(
    spec: str, base_dir: str, data: dict, cache_key: str, _adapter: Adapter
) -> tuple[list[Record], list[str]]:
    # ``_adapter`` is left out of hashing by its leading underscore.
    return load_records(_adapter)


def _fail(exc: Exception) -> None:
    st.error(f"{type(exc).__name__}: {exc}")
    st.stop()


def main() -> None:
    try:
        cfg = load_project(_project_path())
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    spec, base_dir = adapter_spec(cfg)
    try:
        # Fresh instance per run, also used for lazy trace loads.
        adapter = _adapter_class(spec, str(base_dir), adapter_mtime(cfg))(cfg.data)
        records, problems = _load_records(
            spec, str(base_dir), cfg.data, _cache_key(cfg), adapter
        )
    except Exception as exc:  # AdapterLoadError, or an exception raised by load()
        _fail(exc)
    if problems:
        st.warning("Adapter output problems:\n\n- " + "\n- ".join(problems[:10]))

    store = AnnotationStore(cfg.annotations_path)

    st.sidebar.title("rag-qualcode")
    st.sidebar.caption(
        f"Project **{cfg.name}** · adapter `{cfg.adapter}` · {len(records)} records"
    )
    phase = st.sidebar.radio(
        "Phase",
        ["1 · Open coding", "2 · Axial coding"],
        key="phase",
    )

    if phase.startswith("1"):
        open_coding.render(records, adapter, store, cfg)
    else:
        axial_coding.render(records, adapter, store, cfg)


main()
