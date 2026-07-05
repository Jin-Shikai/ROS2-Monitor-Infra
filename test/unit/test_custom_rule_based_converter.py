"""Tests for custom/rule_based.py (the user-facing demo)."""

import pytest

from data_record import DataRecord
from custom.rule_based import RuleBasedConverter


def _data_record(source_name="/odom", data=None):
    return DataRecord.from_topic_msg(
        session_id="sid",
        topic_name=source_name,
        msg_type="nav_msgs/msg/Odometry",
        data=data or {"twist": {"twist": {"linear": {"x": 0.7}}}},
        seq=1,
    )


def test_projects_fields():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"velocity": "twist.twist.linear.x"},
        property_id="speed_limit",
    )
    out = c.convert(_data_record())
    assert out is not None
    assert out["velocity"] == 0.7
    assert out["_property_id"] == "speed_limit"
    assert out["_source_name"] == "/odom"
    assert "_timestamp" in out


def test_skips_unmatched_source():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"v": "twist.twist.linear.x"},
    )
    assert c.convert(_data_record(source_name="/cmd_vel")) is None


def test_require_all_drops_when_field_missing():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"v": "twist.twist.linear.x", "missing": "no.such.path"},
        require_all=True,
    )
    assert c.convert(_data_record()) is None


def test_partial_extraction_default():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"v": "twist.twist.linear.x", "missing": "no.such.path"},
    )
    out = c.convert(_data_record())
    assert out is not None
    assert out["v"] == 0.7
    assert "missing" not in out


def test_drops_when_no_field_extracted():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"missing": "no.such.path"},
    )
    assert c.convert(_data_record()) is None


def test_projects_flat_key_from_field_extractor_output():
    """RuleBasedConverter must read records that already passed through
    FieldExtractor, where dot-paths are literal flat keys, not nested dicts."""
    flat_data = {"twist.twist.linear.x": 0.4, "pose.pose.position.x": 1.2}
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"velocity": "twist.twist.linear.x"},
        property_id="speed_limit",
    )
    out = c.convert(_data_record(data=flat_data))
    assert out is not None
    assert out["velocity"] == 0.4


def test_omits_property_id_when_not_configured():
    c = RuleBasedConverter(
        source_match="^/odom$",
        field_map={"v": "twist.twist.linear.x"},
    )
    out = c.convert(_data_record())
    assert out is not None
    assert "_property_id" not in out
