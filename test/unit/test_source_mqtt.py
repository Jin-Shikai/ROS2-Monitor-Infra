"""Unit tests for monitor/source_mqtt.py.

A MagicMock paho client is injected so tests can drive the on_connect /
on_message callbacks directly without a real broker.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import source_mqtt
from data_record import DataRecord
from source_mqtt import MQTTSource


def _fake_message(topic: str, payload_obj) -> SimpleNamespace:
    if isinstance(payload_obj, DataRecord):
        payload = payload_obj.to_json().encode("utf-8")
    elif isinstance(payload_obj, str):
        payload = payload_obj.encode("utf-8")
    else:
        payload = payload_obj
    return SimpleNamespace(topic=topic, payload=payload)


def test_on_message_parses_json_and_invokes_sink():
    client = MagicMock()
    src = MQTTSource(client=client)
    received: list[DataRecord] = []
    src.start(received.append)

    rec = DataRecord.from_topic_msg(
        session_id="sid", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4}, seq=7,
    )
    src._on_message(client, None, _fake_message("monitor/topic/odom", rec))

    assert len(received) == 1
    out = received[0]
    assert out.source_name == "/odom"
    assert out.data == {"twist.twist.linear.x": 0.4}
    assert out.metadata["seq"] == 7
    assert src._received == 1


def test_on_message_drops_invalid_json(caplog):
    client = MagicMock()
    src = MQTTSource(client=client)
    received: list[DataRecord] = []
    src.start(received.append)
    src._on_message(client, None, _fake_message("monitor/topic/odom", "not-json{"))
    assert received == []
    assert src._received == 0


def test_on_message_swallows_sink_errors():
    client = MagicMock()
    src = MQTTSource(client=client)

    def bad_sink(_):
        raise RuntimeError("downstream blew up")

    src.start(bad_sink)
    rec = DataRecord.from_topic_msg("sid", "/x", "y", {}, 1)
    # Must not raise: sink errors must be isolated.
    src._on_message(client, None, _fake_message("monitor/topic/x", rec))


def test_on_connect_subscribes_to_topic_filter():
    client = MagicMock()
    src = MQTTSource(client=client, topic_filter="monitor/#", qos=2)
    src.start(lambda _: None)
    src._on_connect(client, None, {}, 0, None)
    client.subscribe.assert_called_once_with("monitor/#", qos=2)


def test_on_connect_failure_does_not_subscribe(caplog):
    client = MagicMock()
    src = MQTTSource(client=client)
    src.start(lambda _: None)
    src._on_connect(client, None, {}, 5, None)
    client.subscribe.assert_not_called()


def test_stop_does_not_touch_externally_supplied_client():
    client = MagicMock()
    src = MQTTSource(client=client)
    src.start(lambda _: None)
    src.stop()
    client.loop_stop.assert_not_called()
    client.disconnect.assert_not_called()


def test_no_paho_start_is_noop(monkeypatch):
    monkeypatch.setattr(source_mqtt, "_HAS_PAHO", False)
    monkeypatch.setattr(source_mqtt, "mqtt", None)
    src = MQTTSource()
    assert src._client is None
    # Must not raise.
    src.start(lambda _: None)
    src.stop()
