"""Unit tests for monitor/verdict.py — framework abstractions only.

For tests of the ThresholdVerdict demo, see test_custom_threshold_verdict.py.
"""

import json

import pytest

from verdict import (
    Verdict,
    VerdictExporter,
    VerdictService,
    resolve_verdict_class,
)


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


def test_verdict_exporter_invokes_sink_on_emit():
    captured = []
    exp = VerdictExporter(_AlwaysFires(), sink=captured.append)
    exp.export({"any": "record"})
    assert len(captured) == 1
    assert captured[0].property_id == "p"


def test_verdict_exporter_silent_when_service_returns_none():
    captured = []
    exp = VerdictExporter(_NeverFires(), sink=captured.append)
    exp.export({"any": "record"})
    assert captured == []


def test_verdict_exporter_default_sink_prints(capsys):
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
