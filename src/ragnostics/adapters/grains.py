"""Reference adapter for the GRAINS hybrid RAG system (BM25 + dense + knowledge graph, RRF).

This is the full example adapter: it shows lazy traces, full chunk texts and
adapter-owned diagnostics (``trace_signals``, ``signal_level``, ``blind_metrics``).

Expected ``data:`` keys in the project YAML:

    results:          benchmark results JSONL (one record per line). If a
                      SAS-augmented variant exists, point here to include
                      ``sas_score`` as a metric.
    evidence_hits:    optional JSON produced by the evidence precompute
                      (token overlap between ground-truth chunk and retrieved
                      items), keyed by chunk_hash.
    traces_dir:       optional directory of per-record trace JSON files named
                      ``<chunk_hash>.json`` (lazy-loaded on demand).
    ground_truth_csv: optional benchmark CSV with ``doc_hash`` and ``text``
                      columns (plus title/url) for the ground-truth panel.
    gold_chunk_texts: optional JSON mapping record id -> list of ground-truth
                      chunk texts, used to decide whether the ground-truth
                      passage was delivered (``trace_signals``).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from ..schema import GroundTruth, Record, RetrievalEvent, RetrievedSource
from .base import Adapter, Level

# Source fields kept out of ``extras`` because they map to canonical fields.
_CANONICAL_SOURCE_KEYS = {"chunk_id", "rank", "score", "snippet", "doc_url", "doc_type"}

# Ground-truth lookups keyed by CSV path, shared across adapter instances because
# the app creates a throwaway one per rerun for lazy trace access.
_GT_CACHE: dict[str, dict[str, dict[str, str]]] = {}


def _norm_url(value: Any) -> str | None:
    """Normalize a URL for identity matching.

    Drops the fragment, since ground-truth URLs carry anchors like ``#respond``
    that the retrieved source does not. Keeps the query string: one publisher
    encodes the article id there, so stripping it would collapse ~1.5k distinct
    articles onto a single key. The trailing slash is removed last, after the
    fragment, otherwise ``…/#respond`` would leave one behind.
    """
    if not value:
        return None
    u = str(value).strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    if u.startswith("www."):
        u = u[4:]
    u = u.split("#")[0]
    return u.rstrip("/") or None


def _norm_patent(value: Any) -> str | None:
    """Normalize a patent number to its kind-code-agnostic base so an application
    (…-A) and its grant (…-B) match: 'patent_CN-114539761-B' -> 'CN114539761'."""
    if not value:
        return None
    x = str(value).upper()
    if x.startswith("PATENT_"):
        x = x[len("PATENT_"):]
    x = re.sub(r"[^A-Z0-9]", "", x)   # CN-114539761-A -> CN114539761A
    x = re.sub(r"[A-Z]\d?$", "", x)   # strip trailing kind code -> CN114539761
    return x or None


def _norm_doi(value: Any) -> str | None:
    if not value:
        return None
    x = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if x.startswith(prefix):
            x = x[len(prefix):]
    return x or None


_NON_ALNUM_TEXT = re.compile(r"[^a-z0-9]+")
_EQUAL, _CONTAINS = "equal", "contains"
_TIER_RANK = {_EQUAL: 2, _CONTAINS: 1}
_GOLD_TEXT_CACHE: dict[str, dict[str, list[str]]] = {}


def _norm_chunk_text(value: Any) -> str:
    return _NON_ALNUM_TEXT.sub(" ", str(value or "").lower()).strip()


def _text_tier(gold: str, candidate: str) -> str | None:
    """How one candidate chunk relates to the ground-truth chunk.

    Both sides come out of the same chunking pipeline, so equality is the primary
    test. Containment covers a near-duplicate document whose chunk boundaries fall
    elsewhere. Identifiers are never compared: the same passage occurs in this
    corpus under several document identifiers.
    """
    if not gold or not candidate:
        return None
    if gold == candidate:
        return _EQUAL
    if gold in candidate or candidate in gold:
        return _CONTAINS
    return None


def _locate(gold_texts: list[str], candidates: list[str]) -> tuple[int | None, str | None]:
    """Strongest match wins rather than the first, ties keep the earlier position."""
    best_position, best_tier = None, None
    for position, candidate in enumerate(candidates, start=1):
        for gold in gold_texts:
            found = _text_tier(gold, candidate)
            if found and (best_tier is None or _TIER_RANK[found] > _TIER_RANK[best_tier]):
                best_position, best_tier = position, found
                break
        if best_tier == _EQUAL:
            break
    return best_position, best_tier


def _trace_items(trace: dict[str, Any] | None, section: str) -> list[dict[str, Any]]:
    retrieval = (trace or {}).get("retrieval") or {}
    return (retrieval.get(section) or {}).get("items") or []


def _texts_by_id(trace: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for section in ("ctx_pack", "fusion_json"):
        for item in _trace_items(trace, section):
            if not isinstance(item, dict) or not item.get("text"):
                continue
            text = _norm_chunk_text(item["text"])
            for key in (item.get("chunk_id"), item.get("doc_id"), item.get("id")):
                if key and str(key) not in out:
                    out[str(key)] = text
    return out


def _gt_retrieved_rank(
    gt_row: dict[str, str] | None, sources: list[dict[str, Any]]
) -> tuple[bool, int | None]:
    """Deterministic identity match: is the ground-truth document present in the
    retrieved set, and at what final delivered position? Matches by URL
    (media/openalex), DOI (openalex), or normalized patent base number (patent,
    kind-code agnostic) — deliberately NOT by fuzzy text overlap.

    The reported rank is the 1-based POSITION in the delivered ``sources`` list
    (the final, post-rerank order the generator actually saw), not each item's
    ``rank`` field, which is the pre-rerank fusion candidate rank and can differ
    wildly (e.g. reranked from candidate 17 to delivered position 1)."""
    if not gt_row:
        return False, None
    keys = _gt_keys(gt_row)
    for position, s in enumerate(sources, start=1):
        if _item_matches_gt(s, keys, url_field="doc_url"):
            return True, position
    return False, None


def _gt_keys(gt_row: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    """The three identity keys used for ground-truth matching."""
    return (
        _norm_url(gt_row.get("url")),
        _norm_doi(gt_row.get("doi")),
        _norm_patent(gt_row.get("publication_number")),
    )


def _item_matches_gt(
    item: dict[str, Any],
    keys: tuple[str | None, str | None, str | None],
    url_field: str,
) -> bool:
    """Identity match of one retrieved item against the ground truth.

    ``url_field`` differs between the two places this runs: delivered sources
    carry ``doc_url``, raw fusion candidates in the trace carry ``url``.
    """
    gt_url, gt_doi, gt_patent = keys
    if gt_url and _norm_url(item.get(url_field)) == gt_url:
        return True
    if gt_doi:
        haystack = " ".join(
            str(item.get(k) or "") for k in (url_field, "openalex", "doc_id")
        ).lower()
        if gt_doi in haystack:
            return True
    if gt_patent and _norm_patent(item.get("doc_id")) == gt_patent:
        return True
    return False


class GrainsAdapter(Adapter):
    name = "grains"
    blind_metrics = frozenset({"sas_score"})

    def load(self) -> list[Record]:
        results_path = Path(self.data["results"])
        evidence = self._load_json_if_set("evidence_hits")
        ground_truth = self._load_ground_truth()

        records: list[Record] = []
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(self._to_record(json.loads(line), evidence, ground_truth))
        return records

    def load_trace(self, record: Record) -> dict[str, Any] | None:
        traces_dir = self.data.get("traces_dir")
        if not traces_dir:
            return None
        path = Path(traces_dir) / f"{record.id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def trace_signals(
        self, record: Record, trace: dict[str, Any] | None
    ) -> dict[str, str]:
        """Passage-level diagnostics decided on chunk text.

        "Ground-truth passage": was the ground-truth chunk among the delivered
        sources. "Ground-truth candidate": when it was not, whether it was among the
        raw fusion candidates (dropped before generation) or absent from all of them.
        """
        if trace is None or not self._gold_chunk_texts().get(record.id):
            return {}
        signals: dict[str, str] = {}
        position = self._delivered_position(record, trace)
        if position is not None:
            signals["Ground-truth passage"] = f"delivered at position {position}"
            return signals
        signals["Ground-truth passage"] = "not delivered"
        candidate, total = self._candidate_position(record, trace)
        if candidate is not None:
            signals["Ground-truth candidate"] = (
                f"dropped before generation, candidate {candidate} of {total}"
            )
        elif total > 0:
            signals["Ground-truth candidate"] = f"absent from all {total} candidates"
        return signals

    def signal_level(self, key: str, value: str) -> Level | None:
        if key == "Ground-truth document":
            if value.startswith("retrieved @"):
                return "good"
            if value.startswith("not retrieved"):
                return "bad"
            if value.startswith("no ground truth"):
                return "neutral"
        elif key == "Ground-truth passage":
            if value.startswith("delivered at position"):
                return "good"
            if value.startswith("not delivered"):
                return "bad"
        elif key == "Ground-truth candidate":
            if value.startswith("dropped before generation"):
                return "warn"
            if value.startswith("absent from all"):
                return "bad"
        return None

    def _candidate_position(
        self, record: Record, trace: dict[str, Any] | None
    ) -> tuple[int | None, int]:
        """Position of the ground truth among the raw fusion candidates and the
        number of candidates, matched on chunk text.

        The app builds a fresh adapter for lazy trace loads and never calls load()
        on it, so this must not depend on instance state left behind by load().
        The gold texts come from a process-wide cache keyed by file path.
        """
        gold = self._gold_chunk_texts().get(record.id) or []
        pool = [_norm_chunk_text(i.get("text")) for i in _trace_items(trace, "fusion_json")]
        position, _ = _locate(gold, pool)
        return position, len(pool)

    def _delivered_position(
        self, record: Record, trace: dict[str, Any] | None
    ) -> int | None:
        """1-based position of the ground-truth chunk among the delivered sources.

        Decided on chunk text through the same rule the scaling step applies, so the
        signal shown while coding and the code assigned later cannot disagree.
        """
        gold = self._gold_chunk_texts().get(record.id) or []
        texts = _texts_by_id(trace)
        delivered = [
            texts.get(source.id, "")
            for event in record.retrieval_events
            for source in event.sources
        ]
        position, _ = _locate(gold, delivered)
        return position

    def _gold_chunk_texts(self) -> dict[str, list[str]]:
        """Normalised text of each question's ground-truth chunks, keyed by question."""
        path = str(self.data.get("gold_chunk_texts") or "")
        if path not in _GOLD_TEXT_CACHE:
            if path and Path(path).exists():
                with open(path, encoding="utf-8") as handle:
                    _GOLD_TEXT_CACHE[path] = json.load(handle)
            else:
                _GOLD_TEXT_CACHE[path] = {}
        return _GOLD_TEXT_CACHE[path]

    def _ground_truth_cached(self) -> dict[str, dict[str, str]]:
        path = str(self.data.get("ground_truth_csv") or "")
        if path not in _GT_CACHE:
            _GT_CACHE[path] = self._load_ground_truth()
        return _GT_CACHE[path]

    def chunk_texts(self, trace: dict[str, Any] | None) -> dict[str, str]:
        """Join retrieved sources to their full chunk text via the trace's
        ctx_pack / fusion_json items (keyed by chunk_id, with doc_id/id fallback)."""
        if not trace:
            return {}
        retrieval = trace.get("retrieval") or {}
        out: dict[str, str] = {}
        for section in ("ctx_pack", "fusion_json"):
            items = (retrieval.get(section) or {}).get("items") or []
            for it in items:
                if not isinstance(it, dict):
                    continue
                text = it.get("text")
                if not text:
                    continue
                for key in (it.get("chunk_id"), it.get("doc_id"), it.get("id")):
                    if key and str(key) not in out:
                        out[str(key)] = text
        return out

    # -- internals ---------------------------------------------------------

    def _load_json_if_set(self, key: str) -> dict[str, Any]:
        path = self.data.get(key)
        if not path or not Path(path).exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_ground_truth(self) -> dict[str, dict[str, str]]:
        path = self.data.get("ground_truth_csv")
        if not path or not Path(path).exists():
            return {}
        lookup: dict[str, dict[str, str]] = {}
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lookup[row["doc_hash"]] = row
        return lookup

    def _to_record(
        self,
        raw: dict[str, Any],
        evidence: dict[str, Any],
        ground_truth: dict[str, dict[str, str]],
    ) -> Record:
        chunk_hash = raw["chunk_hash"]

        sources = [
            RetrievedSource(
                id=str(s.get("chunk_id") or s.get("doc_id") or ""),
                snippet=s.get("snippet") or s.get("summary"),
                score=_as_float(s.get("score")),
                rank=s.get("rank"),
                url=s.get("doc_url"),
                doc_type=s.get("doc_type"),
                extras={k: v for k, v in s.items() if k not in _CANONICAL_SOURCE_KEYS and v},
            )
            for s in raw.get("sources") or []
        ]

        metrics: dict[str, float] = {}
        for key in ("elapsed_seconds", "retrieval_latency_ms", "sas_score"):
            value = _as_float(raw.get(key))
            if value is not None:
                metrics[key] = value

        gt_row = ground_truth.get(chunk_hash)

        # Primary evidence signal: deterministic "was the GT document retrieved?"
        signals: dict[str, str] = {}
        if gt_row is None:
            signals["Ground-truth document"] = "no ground truth available"
        else:
            found, rank = _gt_retrieved_rank(gt_row, raw.get("sources") or [])
            if found:
                signals["Ground-truth document"] = (
                    f"retrieved @ position {rank}" if rank is not None else "retrieved"
                )
            else:
                signals["Ground-truth document"] = "not retrieved"

        # Secondary: keep the fuzzy lexical overlap as a muted metric only.
        hit = evidence.get(chunk_hash)
        if hit:
            overlap = _as_float(hit.get("best_overlap"))
            if overlap is not None:
                metrics["evidence_overlap"] = overlap
        gt = None
        if gt_row is not None:
            gt = GroundTruth(
                chunk_text=gt_row.get("text"),
                title=gt_row.get("title"),
                url=gt_row.get("url"),
            )

        extras: dict[str, Any] = {"index": raw.get("index"), "title": raw.get("title")}
        if hit:
            extras["evidence_overlap"] = hit

        return Record(
            id=chunk_hash,
            source_type=raw.get("source", "unknown"),
            question=raw.get("question", ""),
            system_answer=raw.get("system_answer", ""),
            reference_answer=raw.get("expected_answer"),
            status=raw.get("status", "unknown"),
            retrieval_events=[
                RetrievalEvent(channel="hybrid-fusion (BM25 + dense + graph, RRF)", sources=sources)
            ],
            citations=[],  # GRAINS emits no in-text citations
            metrics=metrics,
            signals=signals,
            ground_truth=gt,
            extras=extras,
        )


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
