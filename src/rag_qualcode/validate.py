"""Checks behind ``qualcode validate``.

Uses the same loading code as the GUI. Reports problems (exit code 1), warnings
and counts that reveal a wrong field mapping, and prints a few records in full so
a person can compare them with the raw log.
"""

from __future__ import annotations

import dataclasses
import json
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .adapters import resolve_adapter_class
from .config import ProjectConfig
from .loading import adapter_spec, load_records
from .schema import Record

_LEVELS = ("good", "warn", "bad", "neutral", None)
_MAX_STRING = 300


@dataclass
class ValidationReport:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total: int = 0
    per_source_type: dict[str, int] = field(default_factory=dict)
    empty_system_answer: int = 0
    missing_reference_answer: int = 0
    zero_retrieval_events: int = 0
    with_ground_truth: int = 0
    metric_keys: set[str] = field(default_factory=set)
    signal_keys: set[str] = field(default_factory=set)
    trace_signal_keys: set[str] = field(default_factory=set)
    hook_timings: dict[str, float] = field(default_factory=dict)
    shown: list[str] = field(default_factory=list)


def _describe(exc: BaseException, with_traceback: bool) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if with_traceback:
        text += "\n" + "".join(traceback.format_exception(exc))
    return text


def _cut(value: Any) -> Any:
    """Cut long strings (recursively) and mark the cut."""
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + f"... [cut, {len(value)} chars in total]"
    if isinstance(value, dict):
        return {k: _cut(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_cut(v) for v in value]
    return value


def _print_record(record: Record) -> str:
    return json.dumps(_cut(dataclasses.asdict(record)), indent=2, ensure_ascii=False, default=str)


def run_validation(
    cfg: ProjectConfig, show: int, with_traceback: bool = False
) -> ValidationReport:
    """Load the project's adapter and records and run all checks."""
    report = ValidationReport()
    spec, base_dir = adapter_spec(cfg)
    try:
        adapter = resolve_adapter_class(spec, base_dir)(cfg.data)
        records, record_problems = load_records(adapter)
    except Exception as exc:  # AdapterLoadError or an exception raised by load()
        report.problems.append(f"Adapter '{spec}' failed: {_describe(exc, with_traceback)}")
        return report
    report.problems.extend(record_problems)

    report.total = len(records)
    report.per_source_type = dict(Counter(r.source_type for r in records))
    for r in records:
        if not (r.system_answer or "").strip():
            report.empty_system_answer += 1
        if not (r.reference_answer or "").strip():
            report.missing_reference_answer += 1
        if not r.retrieval_events:
            report.zero_retrieval_events += 1
        if r.ground_truth is not None:
            report.with_ground_truth += 1
        report.metric_keys.update(r.metrics)
        report.signal_keys.update(r.signals)

    def timed(name: str, call: Any) -> Any:
        started = time.perf_counter()
        try:
            return call()
        finally:
            report.hook_timings[name] = report.hook_timings.get(name, 0.0) + (
                time.perf_counter() - started
            )

    def check_level(key: str, value: str) -> None:
        try:
            level = adapter.signal_level(key, value)
        except Exception as exc:
            report.problems.append(
                f"signal_level({key!r}, {value!r}) raised {_describe(exc, with_traceback)}"
            )
            return
        if level not in _LEVELS:
            report.problems.append(
                f"signal_level({key!r}, {value!r}) returned {level!r}, expected "
                "'good', 'warn', 'bad', 'neutral' or None"
            )

    for r in records:
        for key, value in r.signals.items():
            check_level(key, str(value))

    shown = records[: max(0, min(show, len(records)))]
    for r in shown:
        trace: dict[str, Any] | None = None
        try:
            trace = timed("load_trace", lambda r=r: adapter.load_trace(r))
        except Exception as exc:
            report.problems.append(f"load_trace({r.id}) raised {_describe(exc, with_traceback)}")
        else:
            if trace is not None and not isinstance(trace, dict):
                report.problems.append(
                    f"load_trace({r.id}) returned {type(trace).__name__}, expected dict or None"
                )
                trace = None

        try:
            texts = timed("chunk_texts", lambda: adapter.chunk_texts(trace))
        except Exception as exc:
            report.problems.append(f"chunk_texts({r.id}) raised {_describe(exc, with_traceback)}")
        else:
            if not isinstance(texts, dict):
                report.problems.append(
                    f"chunk_texts({r.id}) returned {type(texts).__name__}, expected dict"
                )

        try:
            signals = timed("trace_signals", lambda: adapter.trace_signals(r, trace))
        except Exception as exc:
            report.problems.append(
                f"trace_signals({r.id}) raised {_describe(exc, with_traceback)}"
            )
        else:
            if not isinstance(signals, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in signals.items()
            ):
                report.problems.append(
                    f"trace_signals({r.id}) returned {signals!r}, expected dict[str, str]"
                )
            else:
                report.trace_signal_keys.update(signals)
                for key, value in signals.items():
                    check_level(key, value)
        report.shown.append(_print_record(r))

    for name in sorted(getattr(adapter, "blind_metrics", ())):
        if name not in report.metric_keys:
            report.warnings.append(
                f"blind_metrics names '{name}', which occurs in no record's metrics"
            )
    return report


def _pct(count: int, total: int) -> str:
    return f"{count} ({100 * count / total:.0f} %)" if total else str(count)


def format_report(report: ValidationReport) -> str:
    """Console output for ``qualcode validate``."""
    lines: list[str] = []
    if report.total:
        t = report.total
        lines += [
            "Counts",
            f"  records:                    {t}",
            "  per source_type:            "
            + (", ".join(f"{k}: {v}" for k, v in sorted(report.per_source_type.items())) or "-"),
            f"  empty system answer:        {_pct(report.empty_system_answer, t)}",
            f"  missing reference answer:   {_pct(report.missing_reference_answer, t)}",
            f"  zero retrieval events:      {_pct(report.zero_retrieval_events, t)}",
            f"  with ground truth:          {_pct(report.with_ground_truth, t)}",
            f"  metric keys:                {', '.join(sorted(report.metric_keys)) or '-'}",
            f"  signal keys:                {', '.join(sorted(report.signal_keys)) or '-'}",
            "  trace signal keys (shown records): "
            f"{', '.join(sorted(report.trace_signal_keys)) or '-'}",
        ]
        if report.hook_timings:
            lines.append(
                "  hook timings:               "
                + ", ".join(f"{k} {v * 1000:.0f} ms" for k, v in report.hook_timings.items())
            )
        lines.append("")
    if report.warnings:
        lines += ["Warnings"] + [f"  - {w}" for w in report.warnings] + [""]
    if report.shown:
        lines.append(f"Records shown ({len(report.shown)}), compare them with the raw log:")
        for i, text in enumerate(report.shown, start=1):
            lines += [f"--- record {i} ---", text]
        lines.append("")
    if report.problems:
        lines += [f"Problems ({len(report.problems)})"] + [f"  - {p}" for p in report.problems]
        lines.append("")
        lines.append("FAILED")
    else:
        lines.append("OK: no problems found")
    return "\n".join(lines)
