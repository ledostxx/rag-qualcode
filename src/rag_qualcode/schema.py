"""Canonical record schema.

Every adapter maps its system's raw benchmark logs into these dataclasses.
The UI renders only this schema; anything system-specific goes into the
``extras`` dicts, which are displayed generically as collapsible sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedSource:
    """One retrieved item (chunk, document, or API result)."""

    id: str
    """Identifier of the source (chunk id, document id). Used to look up its full
    text in ``Adapter.chunk_texts``, so it must match the keys that hook returns."""
    title: str | None = None
    """Title of the source, if the system provides one."""
    snippet: str | None = None
    """Short text of the source, shown when no full chunk text is available."""
    score: float | None = None
    """Retrieval or ranking score as reported by the system."""
    rank: int | None = None
    """Rank as reported by the system. Shown next to the position in the list,
    which is the order in which the sources were handed to the answer model."""
    url: str | None = None
    """Location of the source, if it has one."""
    doc_type: str | None = None
    """Kind of document (news, paper, patent, web page ...)."""
    extras: dict[str, Any] = field(default_factory=dict)
    """System-specific fields without a place in this schema."""


@dataclass
class RetrievalEvent:
    """One retrieval step: a tool call, an API query, or a fused retrieval pass."""

    channel: str
    """Name of the retrieval channel or tool that produced the sources."""
    query: str | None = None
    """The query that was sent, if known."""
    sources: list[RetrievedSource] = field(default_factory=list)
    """The sources this step returned, in the order the system delivered them."""
    extras: dict[str, Any] = field(default_factory=dict)
    """System-specific fields without a place in this schema."""


@dataclass
class GroundTruth:
    """The benchmark's ground truth for a record, when available."""

    chunk_text: str | None = None
    """The passage that answers the question."""
    title: str | None = None
    """Title of the document the passage comes from."""
    url: str | None = None
    """Location of that document."""
    expected_channel: str | None = None
    """The retrieval channel or tool that should have found it, if the benchmark says."""
    extras: dict[str, Any] = field(default_factory=dict)
    """System-specific fields without a place in this schema."""


@dataclass
class Record:
    """One benchmark trace in canonical form, as the GUI shows it.

    How a signal is coloured is decided by the adapter (``Adapter.signal_level``);
    see ``docs/schema.md`` for where the GUI shows each field.
    """

    id: str
    """Unique, non-empty identifier of the record."""
    source_type: str
    """Kind of source the question was made from (for example news or patent). The
    sample for open coding is stratified by it."""
    question: str
    """The benchmark question. Must not be empty."""
    system_answer: str
    """The answer the evaluated system gave."""
    reference_answer: str | None = None
    """The benchmark's expected answer, if there is one."""
    status: str = "success"
    """Outcome reported by the system or harness (for example success, error)."""
    retrieval_events: list[RetrievalEvent] = field(default_factory=list)
    """Retrieval steps, in order. Empty if the system did not retrieve."""
    citations: list[str] = field(default_factory=list)
    """Sources the answer cites in its text."""
    metrics: dict[str, float] = field(default_factory=dict)
    """Numeric per-record values (latency, scores ...), shown under the badges."""
    signals: dict[str, str] = field(default_factory=dict)
    """Short text diagnostics shown as coloured badges, for example
    ``{"Ground-truth document": "retrieved @ position 2"}``."""
    ground_truth: GroundTruth | None = None
    """The benchmark's ground truth, or None when the record has none."""
    extras: dict[str, Any] = field(default_factory=dict)
    """System-specific fields, shown as a collapsible JSON section."""


def validate_records(records: list[Record]) -> list[str]:
    """Return a list of human-readable problems (empty = valid)."""
    problems: list[str] = []
    if not records:
        problems.append("adapter returned no records")
        return problems
    seen: set[str] = set()
    for i, r in enumerate(records):
        if not r.id:
            problems.append(f"record #{i} has an empty id")
        elif r.id in seen:
            problems.append(f"duplicate record id: {r.id}")
        seen.add(r.id)
        if not r.question:
            problems.append(f"record {r.id or i} has an empty question")
    return problems
