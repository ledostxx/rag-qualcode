"""Pure helpers of ui/components.py (no Streamlit runtime)."""

import pytest

from ragnostics.ui.components import _color, level_from_words


@pytest.mark.parametrize(
    "value, level",
    [
        ("hit", "good"), ("OK", "good"), ("Cited", "good"),
        ("partial", "warn"), ("decline", "warn"), ("Follow-up", "warn"),
        ("miss", "bad"), ("error", "bad"), ("TIMEOUT", "bad"),
        ("retrieved", None), ("not retrieved", None), ("something else", None), ("", None),
    ],
)
def test_level_from_words(value, level):
    assert level_from_words(value) == level


@pytest.mark.parametrize(
    "level, color",
    [("good", "green"), ("warn", "orange"), ("bad", "red"), ("neutral", "gray"), (None, "gray")],
)
def test_color(level, color):
    assert _color(level) == color


def test_trace_signal_wins_on_key_collision():
    # The merge used by the open and axial views.
    record_signals = {"k": "from record", "only_record": "x"}
    trace_signals = {"k": "from trace", "only_trace": "y"}
    merged = {**record_signals, **trace_signals}
    assert merged == {"k": "from trace", "only_record": "x", "only_trace": "y"}
    assert list(merged).count("k") == 1
