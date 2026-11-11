"""Adapter interface.

An adapter maps one system's raw benchmark logs into the canonical
:class:`~rag_qualcode.schema.Record` list. Implement ``load()``; the other hooks
are optional and have defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from ..schema import Record

Level = Literal["good", "warn", "bad", "neutral"]


class Adapter(ABC):
    """Base class for system adapters.

    ``data`` is the ``data:`` mapping from the project YAML, with paths already
    resolved. Each adapter documents the keys it expects.

    Public hooks and attributes (every one has a default except ``load``):

    - ``load()``: required, returns the list of records.
    - ``load_trace(record)``: the full trace of one record, loaded lazily.
    - ``chunk_texts(trace)``: full text of each retrieved source.
    - ``trace_signals(record, trace)``: diagnostics shown as badges.
    - ``signal_level(key, value)``: how a badge is coloured.
    - ``blind_metrics``: metrics hidden during open coding.

    The change policy for this interface is in ``docs/adapters.md``.
    """

    name: str = "base"

    #: Names of metrics hidden during open coding so the coder is not biased.
    blind_metrics: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @abstractmethod
    def load(self) -> list[Record]:
        """Parse the benchmark output into canonical records."""

    def load_trace(self, record: Record) -> dict[str, Any] | None:
        """Return the full heavy trace for one record, or None if not available."""
        return None

    def chunk_texts(self, trace: dict[str, Any] | None) -> dict[str, str]:
        """Map source id (chunk_id/doc_id) -> full retrieved chunk text, extracted
        from this system's trace. Lets the UI show the full chunk a coder needs for
        attribution checks instead of a truncated snippet. Default: none."""
        return {}

    def trace_signals(
        self, record: Record, trace: dict[str, Any] | None
    ) -> dict[str, str]:
        """Diagnostics derived from the record and its trace, shown as badges.

        Called whenever a record is shown, after its trace is loaded. The result is
        merged with ``record.signals``; on a key collision this result wins.
        Runs on every Streamlit rerun of the record view, so it must not re-read
        whole log files. Default: no signals."""
        return {}

    def signal_level(self, key: str, value: str) -> Level | None:
        """How the badge ``key: value`` is coloured: ``"good"`` (green), ``"warn"``
        (orange), ``"bad"`` (red) or ``"neutral"`` (grey). ``None`` means no opinion,
        and the GUI falls back to a built-in word list. Default: ``None``."""
        return None
