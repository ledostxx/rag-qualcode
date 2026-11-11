import json

from rag_qualcode.sampling import stratified_sample
from rag_qualcode.schema import Record
from rag_qualcode.storage import AnnotationStore


def _record(rid: str, source_type: str) -> Record:
    return Record(id=rid, source_type=source_type, question="q", system_answer="a")


def test_store_roundtrip_and_atomic_write(tmp_path):
    path = tmp_path / "nested" / "ann.json"
    store = AnnotationStore(path)
    store.set("r1", codes=["b-code", "a-code", "a-code"], note="obs", no_issues=False)
    store.set_sample(["r1", "r2"])

    reloaded = AnnotationStore(path)
    assert reloaded.get("r1")["codes"] == ["a-code", "b-code"]  # deduped + sorted
    assert reloaded.get("r1")["note"] == "obs"
    assert reloaded.sample_ids() == ["r1", "r2"]
    assert reloaded.is_coded("r1") and not reloaded.is_coded("r2")
    assert set(reloaded.known_codes()) == {"a-code", "b-code"}
    # no temp files left behind
    assert [p.name for p in path.parent.iterdir()] == ["ann.json"]
    json.loads(path.read_text(encoding="utf-8"))  # valid JSON on disk


def test_no_issues_counts_as_coded(tmp_path):
    store = AnnotationStore(tmp_path / "ann.json")
    store.set("r1", codes=[], note="", no_issues=True)
    assert store.is_coded("r1")
    assert store.coded_count(["r1", "r2"]) == 1


def test_stratified_sample_is_deterministic_and_balanced():
    records = [_record(f"m{i}", "media") for i in range(10)]
    records += [_record(f"p{i}", "patent") for i in range(10)]
    records += [_record(f"s{i}", "science") for i in range(3)]

    a = stratified_sample(records, per_source_type=5, seed=42)
    b = stratified_sample(records, per_source_type=5, seed=42)
    assert a == b
    assert len([x for x in a if x.startswith("m")]) == 5
    assert len([x for x in a if x.startswith("p")]) == 5
    assert len([x for x in a if x.startswith("s")]) == 3  # capped at group size
    assert a != stratified_sample(records, per_source_type=5, seed=1)
