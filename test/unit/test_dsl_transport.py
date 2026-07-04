"""Unit tests for monitor/dsl_transport.py.

The DSL-record transport carries the dict a DataConverter emits across a host
boundary so the converter and its paired VerdictService can run separately. As
with the other MQTT modules, a MagicMock paho client is injected via `client=`
so the callbacks can be driven without a real broker, and the no-paho fallback
is exercised by monkeypatching `_HAS_PAHO`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import dsl_transport
from dsl_transport import DslRecordMQTTExporter, DslRecordMQTTSource
from exporter import Exporter


class _ListExporter(Exporter):
    def __init__(self):
        self.items: list = []

    def export(self, record) -> None:
        self.items.append(record)


def _fake_message(topic: str, payload) -> SimpleNamespace:
    if not isinstance(payload, (bytes, bytearray)):
        payload = payload.encode("utf-8")
    return SimpleNamespace(topic=topic, payload=payload)


# --- DslRecordMQTTExporter --------------------------------------------------

def test_export_publishes_json_to_single_topic():
    client = MagicMock()
    exp = DslRecordMQTTExporter(topic="dsl/odom_speed", client=client, qos=1)
    record = {"velocity": 0.4, "_property_id": "speed", "_timestamp": 1.0}
    exp.export(record)

    client.publish.assert_called_once()
    args, kwargs = client.publish.call_args
    assert args[0] == "dsl/odom_speed"
    assert json.loads(args[1]) == record
    assert kwargs.get("qos", args[2] if len(args) > 2 else None) == 1
    assert exp._published == 1


def test_export_swallows_publish_exceptions():
    client = MagicMock()
    client.publish.side_effect = RuntimeError("broker gone")
    exp = DslRecordMQTTExporter(topic="dsl/x", client=client)
    # Must not raise — Dispatcher relies on exporters not killing the pipeline.
    exp.export({"a": 1})


def test_export_serializes_non_json_native_values():
    """`default=str` keeps export robust if a converter leaks a non-JSON value."""
    client = MagicMock()
    exp = DslRecordMQTTExporter(topic="dsl/x", client=client)
    exp.export({"when": object()})  # not natively JSON-serializable
    payload = client.publish.call_args.args[1]
    assert isinstance(json.loads(payload)["when"], str)


def test_close_does_not_touch_externally_supplied_client():
    client = MagicMock()
    exp = DslRecordMQTTExporter(topic="dsl/x", client=client)
    exp.close()
    client.loop_stop.assert_not_called()
    client.disconnect.assert_not_called()


def test_exporter_no_paho_falls_back_to_noop(monkeypatch):
    monkeypatch.setattr(dsl_transport, "_HAS_PAHO", False)
    monkeypatch.setattr(dsl_transport, "mqtt", None)
    exp = DslRecordMQTTExporter(topic="dsl/x")
    assert exp._client is None
    assert exp.export({"a": 1}) is None
    assert exp.close() is None


# --- DslRecordMQTTSource ----------------------------------------------------

def test_on_message_parses_json_dict_and_pushes_downstream():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/x", client=client)
    downstream = _ListExporter()
    src.start(downstream)

    record = {"velocity": 0.4, "_property_id": "speed"}
    src._on_message(client, None, _fake_message("dsl/x", json.dumps(record)))

    assert downstream.items == [record]
    assert src._received == 1


def test_on_message_drops_invalid_json():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/x", client=client)
    downstream = _ListExporter()
    src.start(downstream)
    src._on_message(client, None, _fake_message("dsl/x", "not-json{"))
    assert downstream.items == []
    assert src._received == 0


def test_on_message_swallows_downstream_errors():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/x", client=client)

    class _Boom(Exporter):
        def export(self, record) -> None:
            raise RuntimeError("downstream blew up")

    src.start(_Boom())
    # Must not raise: downstream errors must be isolated.
    src._on_message(client, None, _fake_message("dsl/x", json.dumps({"a": 1})))
    assert src._received == 0


def test_on_connect_subscribes_to_topic():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/odom_speed", client=client, qos=2)
    src.start(_ListExporter())
    src._on_connect(client, None, {}, 0, None)
    client.subscribe.assert_called_once_with("dsl/odom_speed", qos=2)


def test_on_connect_failure_does_not_subscribe():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/x", client=client)
    src.start(_ListExporter())
    src._on_connect(client, None, {}, 5, None)
    client.subscribe.assert_not_called()


def test_stop_does_not_touch_externally_supplied_client():
    client = MagicMock()
    src = DslRecordMQTTSource(topic="dsl/x", client=client)
    src.start(_ListExporter())
    src.stop()
    client.loop_stop.assert_not_called()
    client.disconnect.assert_not_called()


def test_source_no_paho_start_is_noop(monkeypatch):
    monkeypatch.setattr(dsl_transport, "_HAS_PAHO", False)
    monkeypatch.setattr(dsl_transport, "mqtt", None)
    src = DslRecordMQTTSource(topic="dsl/x")
    assert src._client is None
    src.start(_ListExporter())  # must not raise
    src.stop()


# --- round trip -------------------------------------------------------------

def test_roundtrip_dsl_record_survives_publish_then_receive():
    """A DSL record published on the converter host arrives intact (and still a
    plain dict) on the verdict host — the contract the split relies on."""
    pub_client = MagicMock()
    exp = DslRecordMQTTExporter(topic="dsl/x", client=pub_client)
    record = {
        "velocity": 0.4,
        "_source_name": "/odom",
        "_session_id": "S",
        "_record_id": "S:topic:/odom:-:1",
        "_timestamp": 1.0,
        "_property_id": "speed",
    }
    exp.export(record)
    payload = pub_client.publish.call_args.args[1]

    src = DslRecordMQTTSource(topic="dsl/x", client=MagicMock())
    downstream = _ListExporter()
    src.start(downstream)
    src._on_message(src._client, None, _fake_message("dsl/x", payload))

    assert downstream.items == [record]


# --- File transports ---------------------------------------------------------

def test_file_exporter_and_source_roundtrip(tmp_path):
    from dsl_transport import DslRecordFileExporter, DslRecordFileSource
    import time

    path = tmp_path / "dsl.jsonl"
    exporter = DslRecordFileExporter(path=str(path))
    exporter.export({"speed": 0.4, "_property_id": "p"})
    exporter.close()

    sink = _ListExporter()
    source = DslRecordFileSource(path=str(path))
    source.start(sink)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sink.items:
        time.sleep(0.02)
    source.stop()
    assert sink.items == [{"speed": 0.4, "_property_id": "p"}]


def test_file_source_follow_reads_appended_lines(tmp_path):
    from dsl_transport import DslRecordFileExporter, DslRecordFileSource
    import time

    path = tmp_path / "dsl.jsonl"
    sink = _ListExporter()
    source = DslRecordFileSource(path=str(path), follow=True, poll_sec=0.05)
    source.start(sink)  # file does not exist yet; follow waits for it
    try:
        exporter = DslRecordFileExporter(path=str(path))
        exporter.export({"n": 1})
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(sink.items) < 1:
            time.sleep(0.02)
        exporter.export({"n": 2})
        exporter.close()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(sink.items) < 2:
            time.sleep(0.02)
    finally:
        source.stop()
    assert sink.items == [{"n": 1}, {"n": 2}]


def test_registries_resolve_builtins_and_import_paths():
    from dsl_transport import (
        DslRecordFileExporter,
        DslRecordFileSource,
        resolve_dsl_exporter_class,
        resolve_dsl_source_class,
    )

    assert resolve_dsl_exporter_class("file") is DslRecordFileExporter
    assert resolve_dsl_source_class("file") is DslRecordFileSource
    assert resolve_dsl_exporter_class("mqtt") is DslRecordMQTTExporter
    assert resolve_dsl_source_class("mqtt") is DslRecordMQTTSource
    with pytest.raises(KeyError):
        resolve_dsl_source_class("nope")
