"""G4 guard: the GUI knows no GRAINS vocabulary."""

from pathlib import Path

from ragnostics.adapters import get_adapter
from ragnostics.config import load_project

FIXTURES = Path(__file__).parent / "fixtures"
SRC = Path(__file__).parent.parent / "src" / "ragnostics"
HAND_KEPT = ["sas_score", "fusion", "rerank", "hybrid", "gold_chunk", "traces_dir"]
# "Ground-truth candidate" only appears when a passage is not delivered, which the
# default fixtures do not produce, so it is listed by hand.
HAND_KEPT.append("Ground-truth candidate")


def _grains_identifiers() -> set[str]:
    cfg = load_project(FIXTURES / "project.yaml")
    adapter = get_adapter(cfg.adapter, cfg.data)
    found: set[str] = set(HAND_KEPT)
    for record in adapter.load():
        found.update(record.signals)
        found.update(record.metrics)
        found.update(adapter.trace_signals(record, adapter.load_trace(record)))
    return found


def _gui_files() -> list[Path]:
    return sorted((SRC / "ui").glob("*.py")) + [SRC / "app.py"]


def test_identifier_collection_is_not_empty():
    # Guards the guard: the fixtures must yield the signal keys and metrics.
    found = {i.lower() for i in _grains_identifiers()}
    assert {"ground-truth document", "ground-truth candidate", "sas_score"} <= found


def test_gui_contains_no_grains_identifier():
    hits = []
    for path in _gui_files():
        text = path.read_text(encoding="utf-8").lower()
        for ident in _grains_identifiers():
            if ident.lower() in text:
                hits.append(f"{path.relative_to(SRC)}: {ident}")
    assert not hits, "GRAINS identifiers in the GUI: " + "; ".join(hits)
