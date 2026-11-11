"""End-to-end smoke test: boot the Streamlit app against fixture data."""

import re
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parent.parent
APP = REPO / "src" / "ragnostics" / "app.py"
DEMO = REPO / "examples" / "demo"


def _write_config(tmp_path: Path) -> Path:
    """Demo project with absolute paths; annotations go to tmp_path, not the repo."""
    config = tmp_path / "project.yaml"
    config.write_text(
        f"""
name: smoke
adapter: {DEMO / "demo_adapter.py"}:DemoAdapter
data:
  logs: {DEMO / "logs.jsonl"}
annotations: {tmp_path / "annotations.json"}
sample:
  per_source_type: 2
  seed: 7
""",
        encoding="utf-8",
    )
    return config


def _boot(tmp_path, monkeypatch) -> AppTest:
    monkeypatch.setenv("RAGNOSTICS_PROJECT", str(_write_config(tmp_path)))
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_app_boots_and_draws_sample(tmp_path, monkeypatch):
    at = _boot(tmp_path, monkeypatch)

    draw = [b for b in at.sidebar.button if "sample" in b.label.lower()]
    assert draw, "expected a draw-sample button on first launch"
    draw[0].click().run()
    assert not at.exception
    assert (tmp_path / "annotations.json").exists()

    # Drawing the sample switches the scope to it (2 per source type, 2 types).
    scopes = [r for r in at.sidebar.radio if r.label == "Scope"]
    assert scopes and scopes[0].value == "Sample (4)"


def test_only_open_and_axial_phases_are_offered(tmp_path, monkeypatch):
    at = _boot(tmp_path, monkeypatch)
    phase = [r for r in at.sidebar.radio if r.label == "Phase"][0]
    assert list(phase.options) == ["1 · Open coding", "2 · Axial coding"]


def test_shown_badges_come_from_the_adapter(tmp_path, monkeypatch):
    from ragnostics.adapters import get_adapter

    at = _boot(tmp_path, monkeypatch)
    adapter = get_adapter(
        "./demo_adapter.py:DemoAdapter", {"logs": str(DEMO / "logs.jsonl")}, DEMO
    )
    records = {r.id: r for r in adapter.load()}

    captions = [c.value for c in at.caption if c.value.startswith("Record ")]
    record_id = re.search(r"id `([^`]+)`", captions[0]).group(1)
    record = records[record_id]
    allowed = set(record.signals) | set(
        adapter.trace_signals(record, adapter.load_trace(record))
    )

    header = [m.value for m in at.markdown if m.value.startswith(":blue[")]
    assert header, "expected the badge line"
    badge_keys = re.findall(r":\w+\[([^:\]]+): \*\*", header[0])
    assert badge_keys, "expected at least one signal badge on the first demo record"
    assert set(badge_keys) <= allowed
