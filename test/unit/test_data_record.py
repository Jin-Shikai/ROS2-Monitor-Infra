"""Unit tests for monitor/data_record.py (no ROS2 required)."""

import json
import re

from data_record import DataRecord, generate_session_id


def test_generate_session_id_format():
    sid = generate_session_id()
    assert re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{8}", sid), sid


def test_generate_session_id_unique():
    assert generate_session_id() != generate_session_id()


def test_to_json_drops_none_empty_and_empty_dict():
    rec = DataRecord(_type="data", session_id="s", source_type="topic",
                     source_name="/x", msg_type="t", timestamp=1.0,
                     data={"a": 1}, metadata={})
    d = json.loads(rec.to_json())
    assert "phase" not in d           # None dropped
    assert "ros_timestamp" not in d   # None dropped
    assert "metadata" not in d        # empty dict dropped
    assert d["data"] == {"a": 1}


def test_roundtrip_is_lossless():
    rec = DataRecord.from_topic_msg(
        session_id="sess",
        topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"pose": {"position": {"x": 1.5}}},
        seq=3,
        source_node=["fake_robot"],
    )
    out = DataRecord.from_json(rec.to_json())
    assert out.session_id == rec.session_id
    assert out.source_type == "topic"
    assert out.source_name == "/odom"
    assert out.source_node == ["fake_robot"]
    assert out.data == rec.data
    assert out.metadata["seq"] == 3


def test_session_start_and_end():
    start = DataRecord.make_session_start("sid", {"k": 1})
    assert start._type == "session_start"
    assert start.session_id == "sid"
    assert start.data == {"k": 1}
    assert start.timestamp > 0

    end = DataRecord.make_session_end("sid", {"total": 42})
    assert end._type == "session_end"
    assert end.data == {"total": 42}


def test_session_end_default_stats():
    end = DataRecord.make_session_end("sid")
    assert end.data == {}


def test_from_topic_msg_fields():
    rec = DataRecord.from_topic_msg(
        session_id="s", topic_name="/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        data={"linear": {"x": 0.1}}, seq=7,
    )
    assert rec._type == "data"
    assert rec.source_type == "topic"
    assert rec.phase is None
    assert rec.metadata == {"seq": 7}
    assert rec.ros_timestamp is None  # no header.stamp
    assert rec.record_id == "s:topic:/cmd_vel:-:7"


def test_from_topic_msg_extracts_ros_timestamp():
    rec = DataRecord.from_topic_msg(
        session_id="s", topic_name="/scan", msg_type="sensor_msgs/msg/LaserScan",
        data={"header": {"stamp": {"sec": 10, "nanosec": 500}}, "ranges": []}, seq=1,
    )
    assert rec.ros_timestamp == {"sec": 10, "nanosec": 500}


def test_from_topic_msg_skips_default_zero_stamp():
    rec = DataRecord.from_topic_msg(
        session_id="s", topic_name="/t", msg_type="m",
        data={"header": {"stamp": {"sec": 0, "nanosec": 0}}}, seq=1,
    )
    assert rec.ros_timestamp is None


def test_from_service_event_request_phase():
    event_data = {
        "info": {"event_type": 1, "client_gid": "abc", "sequence_number": 42,
                 "stamp": {"sec": 5, "nanosec": 0}},
        "request": [{"data": True}],
        "response": [],
    }
    rec = DataRecord.from_service_event(
        session_id="s", service_name="/set_bool",
        msg_type="std_srvs/srv/SetBool_Event",
        event_data=event_data, seq=1, source_node=["srv"],
    )
    assert rec.source_type == "service"
    assert rec.phase == "request"
    assert rec.data == {"data": True}
    assert rec.metadata["event_type"] == 1
    assert rec.metadata["sequence_number"] == 42
    assert rec.ros_timestamp == {"sec": 5, "nanosec": 0}


def test_from_service_event_response_phase():
    event_data = {
        "info": {"event_type": 2, "client_gid": "abc", "sequence_number": 42,
                 "stamp": {"sec": 0, "nanosec": 0}},
        "request": [],
        "response": [{"success": True, "message": "ok"}],
    }
    rec = DataRecord.from_service_event(
        session_id="s", service_name="/set_bool",
        msg_type="std_srvs/srv/SetBool_Event",
        event_data=event_data, seq=2,
    )
    assert rec.phase == "response"
    assert rec.data == {"success": True, "message": "ok"}
    assert rec.ros_timestamp is None  # zero stamp dropped


def test_from_service_event_empty_payload_defaults_to_empty_dict():
    event_data = {"info": {"event_type": 1}, "request": [], "response": []}
    rec = DataRecord.from_service_event(
        session_id="s", service_name="/x", msg_type="m", event_data=event_data, seq=1,
    )
    assert rec.data == {}


def test_from_action_feedback():
    rec = DataRecord.from_action_feedback(
        session_id="s", action_name="/fib",
        msg_type="example_interfaces/action/Fibonacci_FeedbackMessage",
        feedback_data={"feedback": {"sequence": [0, 1, 1]}}, seq=5,
    )
    assert rec.source_type == "action"
    assert rec.phase == "feedback"
    assert rec.data == {"feedback": {"sequence": [0, 1, 1]}}


def test_from_action_status_hardcodes_msg_type():
    rec = DataRecord.from_action_status(
        session_id="s", action_name="/fib",
        status_data={"status_list": []}, seq=1,
    )
    assert rec.msg_type == "action_msgs/msg/GoalStatusArray"
    assert rec.phase == "status"
