"""Demo adapter: reads the flat JSONL log in logs.jsonl.

Copy this file to connect your own system. Every place you change is marked
CHANGE. The adapter is one file: helper files next to it cannot be imported.
Field meanings are documented in src/ragnostics/schema.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ragnostics.adapters.base import Adapter, Level
from ragnostics.schema import GroundTruth, Record, RetrievalEvent, RetrievedSource


def _norm(text: str) -> str:
    """Lower-case and collapse whitespace, so layout does not hide a match."""
    return " ".join(text.lower().split())


class DemoAdapter(Adapter):
    name = "demo"  # CHANGE: any short name

    # CHANGE: metrics to hide during open coding (the demo has none).
    blind_metrics = frozenset()

    def _lines(self) -> list[dict[str, Any]]:
        # CHANGE: "logs" is the key under `data:` in the project file.
        path = Path(self.data["logs"])
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def load(self) -> list[Record]:
        return [self._record(raw) for raw in self._lines()]

    def _record(self, raw: dict[str, Any]) -> Record:
        # CHANGE: the right-hand names are this log's fields.
        sources = [
            RetrievedSource(
                id=item["doc"], title=item["title"], snippet=item["text"],
                score=item["score"], rank=i + 1,
            )
            for i, item in enumerate(raw["retrieved"])
        ]
        gold_text, gold_doc = raw.get("gold_text"), raw.get("gold_doc")
        truth = None
        if gold_text or gold_doc:
            truth = GroundTruth(chunk_text=gold_text, extras={"doc": gold_doc})
        record = Record(
            id=raw["id"],
            source_type=raw["kind"],
            question=raw["question"],
            reference_answer=raw.get("expected"),
            system_answer=raw["answer"],
            retrieval_events=[RetrievalEvent(channel="retrieval", sources=sources)],
            ground_truth=truth,
        )
        if truth is not None:  # no ground truth, no evidence signal
            record.signals["evidence"] = self._evidence(raw)
        return record

    @staticmethod
    def _gold_position(raw: dict[str, Any]) -> int | None:
        """1-based position of the first retrieved text containing the gold text."""
        gold = _norm(raw.get("gold_text") or "")
        for i, item in enumerate(raw["retrieved"]):
            if gold and gold in _norm(item["text"]):
                return i + 1
        return None

    def _evidence(self, raw: dict[str, Any]) -> str:
        if self._gold_position(raw) is not None:
            return "hit"
        if raw.get("gold_doc") in {item["doc"] for item in raw["retrieved"]}:
            return "wrong passage"
        return "miss"

    def load_trace(self, record: Record) -> dict[str, Any] | None:
        # The trace is the raw log line. Systems with large traces read them lazily.
        return next((raw for raw in self._lines() if raw["id"] == record.id), None)

    def trace_signals(self, record: Record, trace: dict[str, Any] | None) -> dict[str, str]:
        position = self._gold_position(trace) if trace else None
        return {"Gold rank": f"rank {position}"} if position is not None else {}

    def signal_level(self, key: str, value: str) -> Level | None:
        if key == "evidence":
            return {"hit": "good", "wrong passage": "warn", "miss": "bad"}.get(value)
        return None
