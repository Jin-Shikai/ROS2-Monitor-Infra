"""Unit tests for monitor/verdict_exporters.py — File / Stdout / MQTT
exporters and the registry resolver."""

import json

import pytest

from exporter import Exporter
from verdict import Verdict
from verdict_exporters import (
    VERDICT_EXPORTER_REGISTRY,
    VerdictFileExporter,
    VerdictMQTTExporter,
    VerdictStdoutExporter,
    resolve_verdict_exporter_class,
)


def _v(ts=1.0, pid="p", result=True, details=None):
    return Verdict(timestamp=ts, property_id=pid, result=result, details=details or {})


def test_file_exporter_appends_jsonl(tmp_path):
    path = tmp_path / "out.jsonl"
    exp = VerdictFileExporter(str(path))
    try:
        exp.export(_v(1.0, "p", False, {"v": 0.7}))
        exp.export(_v(2.0, "p", True, {}))
    finally:
        exp.close()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["property_id"] == "p"


def test_file_exporter_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "deep" / "v.jsonl"
    exp = VerdictFileExporter(str(path))
    exp.export(_v())
    exp.close()
    assert path.exists()


def test_file_exporter_close_idempotent(tmp_path):
    exp = VerdictFileExporter(str(tmp_path / "v.jsonl"))
    exp.close()
    exp.close()


def test_stdout_exporter_prints(capsys):
    exp = VerdictStdoutExporter()
    exp.export(_v())
    out = capsys.readouterr().out
    assert "[Verdict]" in out
    assert '"property_id": "p"' in out


def test_mqtt_exporter_publishes_to_topic():
    class FakeClient:
        def __init__(self):
            self.published = []
        def publish(self, topic, payload, qos=0):
            self.published.append((topic, payload, qos))

    client = FakeClient()
    exp = VerdictMQTTExporter(topic="verdicts/foo", client=client, qos=1)
    exp.export(_v(1.0, "speed", False, {"v": 0.4}))
    assert len(client.published) == 1
    topic, payload, qos = client.published[0]
    assert topic == "verdicts/foo"
    assert qos == 1
    assert json.loads(payload)["property_id"] == "speed"


def test_mqtt_exporter_swallows_publish_exceptions():
    class BadClient:
        def publish(self, *a, **kw):
            raise RuntimeError("network down")
    exp = VerdictMQTTExporter(topic="x", client=BadClient())
    # Must not raise — Dispatcher relies on exporters not killing the pipeline.
    exp.export(_v())


def test_mqtt_exporter_close_does_not_touch_external_client():
    class ClosableClient:
        def __init__(self):
            self.stopped = False
            self.disconnected = False
        def loop_stop(self):
            self.stopped = True
        def disconnect(self):
            self.disconnected = True
    client = ClosableClient()
    exp = VerdictMQTTExporter(topic="x", client=client)
    exp.close()
    assert not client.stopped
    assert not client.disconnected


def test_registry_has_builtins():
    assert set(VERDICT_EXPORTER_REGISTRY) >= {"file", "stdout", "mqtt"}


def test_resolve_registry_name():
    assert resolve_verdict_exporter_class("file") is VerdictFileExporter
    assert resolve_verdict_exporter_class("stdout") is VerdictStdoutExporter
    assert resolve_verdict_exporter_class("mqtt") is VerdictMQTTExporter


def test_resolve_unknown_name_raises():
    with pytest.raises(KeyError):
        resolve_verdict_exporter_class("nope")


def test_resolve_module_path_works():
    cls = resolve_verdict_exporter_class(
        "verdict_exporters:VerdictStdoutExporter"
    )
    assert cls is VerdictStdoutExporter


def test_resolve_module_path_wrong_type_raises():
    with pytest.raises(TypeError):
        resolve_verdict_exporter_class("verdict:Verdict")


def test_user_defined_exporter_class():
    """User-defined Exporter[Verdict] subclasses load via module:Class."""
    # The FakeExporter below is defined in this test module; we resolve
    # it via the same `module:Class` mechanism a real user would use.
    cls = resolve_verdict_exporter_class(
        "test_verdict_exporters:_UserExporter"
    )
    assert issubclass(cls, Exporter)


class _UserExporter(Exporter[Verdict]):
    def __init__(self, label="custom"):
        self.label = label
        self.received: list[Verdict] = []
    def export(self, record: Verdict) -> None:
        self.received.append(record)
