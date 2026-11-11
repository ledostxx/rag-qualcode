"""Small adapters that each break one rule, for tests/test_validate.py."""

from __future__ import annotations

from ragnostics.adapters.base import Adapter
from ragnostics.schema import Record


def _record(rid: str, **kw) -> Record:
    return Record(id=rid, source_type="t", question="q?", system_answer="a", **kw)


class Healthy(Adapter):
    def load(self):
        return [_record("a", metrics={"m": 1.0}), _record("b", metrics={"m": 2.0})]


class DuplicateIds(Adapter):
    def load(self):
        return [_record("same"), _record("same")]


class TraceRaises(Healthy):
    def load_trace(self, record):
        raise RuntimeError("trace boom")


class SignalsReturnList(Healthy):
    def trace_signals(self, record, trace):
        return ["not", "a", "dict"]


class BadSignalLevel(Healthy):
    def load(self):
        return [_record("a", signals={"k": "v"})]

    def signal_level(self, key, value):
        return "green"


class BlindMetricAbsent(Healthy):
    blind_metrics = frozenset({"no_such_metric"})


class LoadRaises(Adapter):
    def load(self):
        raise RuntimeError("load boom")
