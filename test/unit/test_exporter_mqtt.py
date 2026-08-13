"""Unit tests for monitor/exporter_mqtt.py.

The real broker is not required: tests inject a MagicMock paho client via
the `client=` kwarg on MQTTExporter. The fallback path (paho not installed)
is exercised by monkeypatching the `_HAS_PAHO` flag.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import exporter_mqtt
from data_record import DataRecord
from exporter_mqtt import MQTTExporter


def _data_record(name="/odom", source_type="topic", data=None, seq=1):
    return DataRecord.from_topic_msg(
        session_id="sid",
        topic_name=name,
        msg_type="nav_msgs/msg/Odometry",
        data=data or {"v": 1.0},
        seq=seq,
    ) if source_type == "topic" else DataRecord(
        _type="data",
        session_id="sid",
        source_type=source_type,
        source_name=name,
        msg_type="x",
        timestamp=0.0,
        data=data or {},
    )


def test_export_publishes_to_correct_topic_and_payload():
    client = MagicMock()
    exp = MQTTExporter(client=client, topic_prefix="monitor/", qos=1)
    rec = _data_record(name="/odom", data={"twist.twist.linear.x": 0.4})
    exp.export(rec)
    client.publish.assert_called_once()
    args, kwargs = client.publish.call_args
    topic = args[0] if args else kwargs["topic"]
    payload = args[1] if len(args) > 1 else kwargs["payload"]
    assert topic == "monitor/topic/odom"
    parsed = json.loads(payload)
    assert parsed["source_name"] == "/odom"
    assert parsed["data"] == {"twist.twist.linear.x": 0.4}
    assert kwargs.get("qos", args[2] if len(args) > 2 else None) == 1


def test_topic_naming_for_service_and_action():
    client = MagicMock()
    exp = MQTTExporter(client=client, topic_prefix="m/")
    exp.export(_data_record(name="/set_bool", source_type="service"))
    exp.export(_data_record(name="/fibonacci", source_type="action"))
    topics = [c.args[0] for c in client.publish.call_args_list]
    assert topics == ["m/service/set_bool", "m/action/fibonacci"]


def test_session_bookends_publish_to_session_topic():
    client = MagicMock()
    exp = MQTTExporter(client=client, topic_prefix="monitor/")
    bookend = DataRecord.make_session_start("sid", {"k": "v"})
    exp.export(bookend)
    client.publish.assert_called_once()
    assert client.publish.call_args.args[0] == "monitor/_session"


def test_publish_bookends_false_skips_session_records():
    client = MagicMock()
    exp = MQTTExporter(client=client, publish_bookends=False)
    exp.export(DataRecord.make_session_start("sid", {}))
    exp.export(DataRecord.make_session_end("sid", {}))
    client.publish.assert_not_called()


def test_export_swallows_publish_exceptions(caplog):
    client = MagicMock()
    client.publish.side_effect = RuntimeError("broker gone")
    exp = MQTTExporter(client=client)
    # Must not raise — Dispatcher relies on exporters not killing the pipeline.
    exp.export(_data_record())


def test_close_does_not_touch_externally_supplied_client():
    client = MagicMock()
    exp = MQTTExporter(client=client)
    exp.close()
    client.loop_stop.assert_not_called()
    client.disconnect.assert_not_called()


def test_no_paho_falls_back_to_noop(monkeypatch, caplog):
    monkeypatch.setattr(exporter_mqtt, "_HAS_PAHO", False)
    monkeypatch.setattr(exporter_mqtt, "mqtt", None)
    exp = MQTTExporter(broker="localhost", port=1883, topic_prefix="monitor/")
    assert exp._client is None
    # export and close must be safe no-ops.
    assert exp.export(_data_record()) is None
    assert exp.close() is None


def test_export_increments_published_counter():
    client = MagicMock()
    exp = MQTTExporter(client=client)
    for i in range(3):
        exp.export(_data_record(seq=i))
    assert exp._published == 3
