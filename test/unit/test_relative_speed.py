"""Unit tests for the two-robot relative-speed converter."""

from __future__ import annotations

import pytest

from custom.relative_speed import RelativeSpeedConverter
from data_record import DataRecord


def _odom(robot: str, vx: float, vy: float = 0.0, seq: int = 1) -> DataRecord:
    return DataRecord.from_topic_msg(
        session_id="S", topic_name=f"{robot}/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": vx, "twist.twist.linear.y": vy}, seq=seq,
    )


def test_emits_relative_speed_once_both_robots_seen():
    conv = RelativeSpeedConverter(robot_a="/robot1", robot_b="/robot2")
    assert conv.convert(_odom("/robot1", 0.6)) is None
    result = conv.convert(_odom("/robot2", 0.0, seq=2))
    assert result is not None
    assert result["relative_speed"] == pytest.approx(0.6)
    assert result["_property_id"] == "fleet_relative_speed"
    assert len(result["_input_record_ids"]) == 2


def test_ignores_unrelated_sources():
    conv = RelativeSpeedConverter(robot_a="/robot1", robot_b="/robot2")
    assert conv.convert(_odom("/robot3", 1.0)) is None


def test_updates_with_latest_velocity():
    conv = RelativeSpeedConverter(robot_a="/robot1", robot_b="/robot2")
    conv.convert(_odom("/robot1", 0.5))
    conv.convert(_odom("/robot2", 0.5, seq=2))
    result = conv.convert(_odom("/robot2", 0.1, seq=3))
    assert result is not None
    assert result["relative_speed"] == pytest.approx(0.4)
