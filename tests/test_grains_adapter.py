import copy
import json
from pathlib import Path

from rag_qualcode.adapters import get_adapter
from rag_qualcode.config import load_project
from rag_qualcode.schema import validate_records

FIXTURES = Path(__file__).parent / "fixtures"


def _adapter(**data_overrides):
    cfg = load_project(FIXTURES / "project.yaml")
    return get_adapter(cfg.adapter, {**cfg.data, **data_overrides})


def test_load_maps_canonical_fields():
    records = _adapter().load()
    assert validate_records(records) == []
    assert len(records) == 2

    r = records[0]
    assert r.id == "aaa111"
    assert r.source_type == "media"
    assert r.reference_answer == "Financial losses across turbine makers."
    assert r.metrics["sas_score"] == 0.71
    assert r.metrics["retrieval_latency_ms"] == 800.0
    # deterministic identity match: GT url == retrieved doc_url at rank 1
    assert r.signals["Ground-truth document"] == "retrieved @ position 1"
    assert r.metrics["evidence_overlap"] == 0.62  # kept as secondary info
    assert r.ground_truth is not None
    assert "Turbine makers" in r.ground_truth.chunk_text

    src = r.retrieval_events[0].sources[0]
    assert src.rank == 1 and src.doc_type == "media"
    assert src.url == "https://example.org/wind"
    # system-specific fields survive in extras
    assert src.extras["tech_entities"] == ["wind"]


def test_gt_not_retrieved_and_empty_sources():
    records = _adapter().load()
    r = records[1]
    assert r.signals["Ground-truth document"] == "not retrieved"
    assert r.retrieval_events[0].sources == []


def test_lazy_trace_loading():
    adapter = _adapter()
    records = adapter.load()
    trace = adapter.load_trace(records[0])
    assert trace["retrieval"]["fusion_json"]["items"][0]["doc_id"] == "media_1"
    assert adapter.load_trace(records[1]) is None  # no trace file for bbb222


def test_trace_signals_passage_delivered():
    adapter = _adapter()
    record = adapter.load()[0]
    signals = adapter.trace_signals(record, adapter.load_trace(record))
    assert signals == {"Ground-truth passage": "delivered at position 1"}


def test_trace_signals_dropped_before_generation():
    adapter = _adapter()
    record = copy.deepcopy(adapter.load()[0])
    record.retrieval_events[0].sources[0].id = "not-in-trace"  # nothing delivered
    signals = adapter.trace_signals(record, adapter.load_trace(record))
    assert signals == {
        "Ground-truth passage": "not delivered",
        "Ground-truth candidate": "dropped before generation, candidate 1 of 1",
    }


def test_trace_signals_absent_from_all_candidates(tmp_path):
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"aaa111": ["a passage that appears nowhere"]}), encoding="utf-8")
    adapter = _adapter(gold_chunk_texts=str(gold))
    record = adapter.load()[0]
    signals = adapter.trace_signals(record, adapter.load_trace(record))
    assert signals == {
        "Ground-truth passage": "not delivered",
        "Ground-truth candidate": "absent from all 1 candidates",
    }


def test_trace_signals_without_gold_texts_or_trace():
    adapter = _adapter()
    first, second = adapter.load()
    assert adapter.trace_signals(second, {"retrieval": {}}) == {}  # no gold text for bbb222
    assert adapter.trace_signals(first, None) == {}


def test_signal_level_prefixes():
    adapter = _adapter()
    expected = {
        ("Ground-truth document", "retrieved @ position 3"): "good",
        ("Ground-truth document", "not retrieved"): "bad",
        ("Ground-truth document", "no ground truth available"): "neutral",
        ("Ground-truth passage", "delivered at position 2"): "good",
        ("Ground-truth passage", "not delivered"): "bad",
        ("Ground-truth candidate", "dropped before generation, candidate 4 of 9"): "warn",
        ("Ground-truth candidate", "absent from all 9 candidates"): "bad",
        ("Other key", "retrieved @ position 1"): None,
        ("Ground-truth document", "something else"): None,
    }
    for (key, value), level in expected.items():
        assert adapter.signal_level(key, value) == level, (key, value)


def test_blind_metrics_hides_sas_score():
    assert _adapter().blind_metrics == frozenset({"sas_score"})
