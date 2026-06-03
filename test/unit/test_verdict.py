"""Unit tests for monitor/verdict.py — framework abstractions only.

For tests of the ThresholdVerdict demo, see test_custom_threshold_verdict.py.
"""

import json

import pytest

from exporter import Exporter
from verdict import (
    Verdict,
    VerdictExporter,
    VerdictService,
    resolve_verdict_class,
)


class _ListExporter(Exporter[Verdict]):
    """Test helper: collect emitted Verdicts into an in-memory list."""

    def __init__(self):
        self.items: list[Verdict] = []

    def export(self, verdict: Verdict) -> None:
        self.items.append(verdict)


class _AlwaysFires(VerdictService):
    def __init__(self, property_id="p"):
        self.property_id = property_id
    def evaluate(self, record):
        return Verdict(
            timestamp=0.0, property_id=self.property_id,
            result=True, details={"echoed": record},
        )


class _NeverFires(VerdictService):
    def evaluate(self, record):
        return None


def test_verdict_service_is_abstract():
    with pytest.raises(TypeError):
        VerdictService()


def test_verdict_to_json_round_trip():
    vd = Verdict(timestamp=1.0, property_id="p", result=True, details={"k": 1})
    obj = json.loads(vd.to_json())
    assert obj == {
        "timestamp": 1.0, "property_id": "p", "result": True, "details": {"k": 1}
    }


def test_verdict_exporter_forwards_to_downstream_on_emit():
    sink = _ListExporter()
    exp = VerdictExporter(_AlwaysFires(), exporter=sink)
    exp.export({"any": "record"})
    assert len(sink.items) == 1
    assert sink.items[0].property_id == "p"


def test_verdict_exporter_silent_when_service_returns_none():
    sink = _ListExporter()
    exp = VerdictExporter(_NeverFires(), exporter=sink)
    exp.export({"any": "record"})
    assert sink.items == []


def test_verdict_exporter_default_prints_to_stdout(capsys):
    exp = VerdictExporter(_AlwaysFires())
    exp.export({"x": 1})
    out = capsys.readouterr().out
    assert "[Verdict]" in out


def test_resolve_requires_module_path():
    with pytest.raises(ValueError):
        resolve_verdict_class("ThresholdVerdict")


def test_resolve_module_path_works():
    cls = resolve_verdict_class(
        "custom.threshold_verdict:ThresholdVerdict"
    )
    assert issubclass(cls, VerdictService)


def test_resolve_module_path_wrong_type_raises():
    with pytest.raises(TypeError):
        resolve_verdict_class("data_record:DataRecord")
