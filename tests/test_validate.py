"""``qualcode validate``: problems, warnings, exit codes and the demo."""

import subprocess
import sys
from pathlib import Path

import pytest

from rag_qualcode import cli

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parent.parent
DEMO = REPO / "examples" / "demo" / "qualcode.yaml"


def _project(tmp_path: Path, cls: str) -> Path:
    path = tmp_path / "project.yaml"
    path.write_text(
        f"name: broken\nadapter: {FIXTURES / 'broken_adapters.py'}:{cls}\n"
        f"data: {{}}\nannotations: {tmp_path / 'ann.json'}\n",
        encoding="utf-8",
    )
    return path


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli._validate(list(argv))
    return code, capsys.readouterr().out


@pytest.mark.parametrize(
    "cls, expected",
    [
        ("DuplicateIds", "duplicate record id: same"),
        ("TraceRaises", "load_trace(a) raised RuntimeError: trace boom"),
        ("SignalsReturnList", "trace_signals(a) returned"),
        ("BadSignalLevel", "returned 'green'"),
    ],
)
def test_problem_cases_exit_1_with_matching_message(tmp_path, capsys, cls, expected):
    code, out = _run(capsys, str(_project(tmp_path, cls)))
    assert code == 1
    assert expected in out
    assert "FAILED" in out


def test_blind_metric_absent_is_a_warning_not_a_problem(tmp_path, capsys):
    code, out = _run(capsys, str(_project(tmp_path, "BlindMetricAbsent")))
    assert code == 0
    assert "no_such_metric" in out and "Warnings" in out
    assert "Problems" not in out


def test_load_raising_is_a_problem_without_traceback(tmp_path, capsys):
    project = _project(tmp_path, "LoadRaises")
    code, out = _run(capsys, str(project))
    assert code == 1
    assert "load boom" in out
    assert "Traceback" not in out

    code, out = _run(capsys, str(project), "--traceback")
    assert code == 1
    assert "Traceback" in out


def test_missing_project_file_exits_1(tmp_path, capsys):
    code, out = _run(capsys, str(tmp_path / "missing.yaml"))
    assert code == 1
    assert "Problem" in out


def test_demo_counts_and_exit_code(capsys):
    code, out = _run(capsys, str(DEMO))
    assert code == 0
    assert "records:                    20" in out
    assert "news: 10, paper: 10" in out
    assert "with ground truth:          18" in out
    assert "empty system answer:        0" in out
    assert "OK: no problems found" in out


def test_demo_reports_trace_signal_keys_of_shown_records(capsys):
    code, out = _run(capsys, str(DEMO), "--show", "3")
    assert code == 0
    line = next(x for x in out.splitlines() if "trace signal keys (shown records)" in x)
    assert "Gold rank" in line


def test_trace_signal_keys_empty_when_no_records_shown(capsys):
    code, out = _run(capsys, str(DEMO), "--show", "0")
    assert code == 0
    line = next(x for x in out.splitlines() if "trace signal keys (shown records)" in x)
    assert line.rstrip().endswith("-")


def test_console_script_exit_code_on_demo():
    result = subprocess.run(
        [sys.executable, "-m", "rag_qualcode.cli", "validate", str(DEMO)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
