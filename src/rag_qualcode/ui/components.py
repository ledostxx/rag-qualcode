"""Shared rendering helpers for canonical records."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from ..adapters.base import Level
from ..schema import Record, RetrievalEvent

_GREEN = {"hit", "ok", "correct", "success", "cited", "answer"}
_ORANGE = {"partial", "warning", "decline", "follow-up"}
_RED = {"miss", "error", "wrong", "failure", "failed", "timeout"}


def level_from_words(value: str) -> Level | None:
    """Fallback colour level from the whole lower-cased value, ``None`` if unknown."""
    v = value.lower()
    if v in _GREEN:
        return "good"
    if v in _ORANGE:
        return "warn"
    if v in _RED:
        return "bad"
    return None


def _color(level: Level | None) -> str:
    return {"good": "green", "warn": "orange", "bad": "red"}.get(level or "", "gray")


def render_header(
    record: Record,
    signals: dict[str, str],
    level_of: Callable[[str, str], Level | None],
    *,
    show_status: bool = True,
    hide_metrics: frozenset[str] = frozenset(),
) -> None:
    """One line of colored badges: source type, (optional) status, signals.

    ``signals`` are the badges to show. Each is coloured by ``level_of(key, value)``,
    falling back to a built-in word list when that returns ``None``. ``show_status`` and
    ``hide_metrics`` let a caller blind the coder to the harness's own evaluative
    verdicts so they don't anchor open coding; the data stays available for later
    quantitative triangulation."""
    parts = [f":blue[**{record.source_type}**]"]
    if show_status:
        parts.append(f":{_color(level_from_words(record.status))}[{record.status}]")
    for key, value in signals.items():
        level = level_of(key, value)
        if level is None:
            level = level_from_words(value)
        parts.append(f":{_color(level)}[{key}: **{value}**]")
    st.markdown(" &nbsp;·&nbsp; ".join(parts))
    metrics = {k: v for k, v in record.metrics.items() if k not in hide_metrics}
    if metrics:
        st.caption(" · ".join(f"{k} = {v:.4g}" for k, v in metrics.items()))


def render_retrieval_event(event: RetrievalEvent, chunk_texts: dict[str, str] | None = None) -> None:
    st.markdown(f"**Channel:** `{event.channel}`" + (f" — query: *{event.query}*" if event.query else ""))
    if not event.sources:
        st.caption("No sources retrieved.")
        return
    chunk_texts = chunk_texts or {}
    rows = [
        {
            "position": i,
            "rank": s.rank,
            "doc_type": s.doc_type,
            "score": s.score,
            "url": s.url,
            "id": s.id,
        }
        for i, s in enumerate(event.sources, start=1)
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(320, 60 + 35 * len(rows)))
    st.caption("‘position’ = final delivered order · ‘rank’ = rank as reported by the adapter")

    # Full chunk text per source (for attribution checks), delivered order.
    for i, s in enumerate(event.sources, start=1):
        text = chunk_texts.get(s.id) or s.snippet or "_(no chunk text available)_"
        with st.container(border=True):
            head = f"**Position {i}** · {s.doc_type or '—'}"
            if s.score is not None:
                head += f" · score {s.score:.3g}"
            if s.rank is not None:
                head += f" · rank {s.rank}"
            st.markdown(head)
            if s.url:
                st.caption(s.url)
            st.markdown(text)


def render_trace(trace: dict[str, Any]) -> None:
    """Generic renderer for a system-specific heavy trace: one collapsed JSON
    section per top-level key so large payloads stay navigable."""
    for key, value in trace.items():
        if isinstance(value, (dict, list)):
            st.markdown(f"**{key}**")
            st.json(value, expanded=False)
        else:
            st.markdown(f"**{key}:** `{value}`")
