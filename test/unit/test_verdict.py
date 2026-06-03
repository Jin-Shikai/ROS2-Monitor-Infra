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

    def export(self, record: Verdict) -> None:
        self.items.append(record)


class _AlwaysFires(VerdictService):
    def __init__(self, property_id="p"):
        self.property_id = property_id
    def evaluate(self, dsl_record):
        return Verdict(
            timestamp=0.0, property_id=self.property_id,
            result=True, details={"echoed": dsl_record},
        )


class _NeverFires(VerdictService):
    def evaluate(self, dsl_record):
        return None


def test_verdict_service_is_abstract():
    with pytest.raises(TypeError):
        VerdictService()  # pyright: ignore[reportAbstractUsage]


def test_verdict_to_json_round_trip():
    vd = Verdict(timestamp=1.0, property_id="p", result=True, details={"k": 1})
    obj = json.loads(vd.to_json())
    assert obj == {
        "timestamp": 1.0, "property_id": "p", "result": True, "details": {"k": 1}
    }


def test_verdict_exporter_forwards_to_downstream_on_emit():
    exporter = _ListExporter()
    exp = VerdictExporter(_AlwaysFires(), exporter=exporter)
    exp.export({"any": "record"})
    assert len(exporter.items) == 1
    assert exporter.items[0].property_id == "p"


def test_verdict_exporter_silent_when_service_returns_none():
    exporter = _ListExporter()
    exp = VerdictExporter(_NeverFires(), exporter=exporter)
    exp.export({"any": "record"})
    assert exporter.items == []


def test_verdict_exporter_default_prints_to_stdout(capsys):
    exp = VerdictExporter(_AlwaysFires())
    exp.export({"x": 1})
    out = capsys.readouterr().out
    assert "[Verdict]" in out


def test_verdict_exporter_attaches_correlation_from_dsl_record():
    exporter = _ListExporter()
    exp = VerdictExporter(_AlwaysFires(), exporter=exporter)
    exp.export({
        "_session_id": "monitor-s",
        "_record_id": "monitor-s:topic:/odom:-:1",
    })
    verdict = exporter.items[0]
    assert verdict.monitor_session_id == "monitor-s"
    assert verdict.input_record_ids == ["monitor-s:topic:/odom:-:1"]


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
