"""Unit tests for the fleet minimum-separation converter and verdict."""

from __future__ import annotations

import pytest

from custom.separation_converter import SeparationDistanceConverter
from custom.separation_verdict import SeparationDistanceVerdict
from data_record import DataRecord


def _pose(robot: str, x: float, y: float = 0.0, seq: int = 1) -> DataRecord:
    return DataRecord.from_topic_msg(
        session_id="S", topic_name=f"{robot}/amcl_pose",
        msg_type="geometry_msgs/msg/PoseWithCovarianceStamped",
        data={"pose.pose.position.x": x, "pose.pose.position.y": y}, seq=seq,
    )


def test_emits_distance_once_both_robots_seen():
    conv = SeparationDistanceConverter(robot_a="/robot1", robot_b="/robot2")
    assert conv.convert(_pose("/robot1", 0.0)) is None
    result = conv.convert(_pose("/robot2", 3.0, 4.0, seq=2))
    assert result is not None
    assert result["separation_m"] == pytest.approx(5.0)
    assert result["_property_id"] == "fleet_separation"
    assert result["positions"] == {"/robot1": [0.0, 0.0], "/robot2": [3.0, 4.0]}
    assert len(result["_input_record_ids"]) == 2


def test_can_infer_robot_pair_from_runtime_filtered_inputs():
    conv = SeparationDistanceConverter()
    assert conv.convert(_pose("/robot1", 0.0)) is None
    result = conv.convert(_pose("/robot2", 2.0, seq=2))
    assert result is not None
    assert result["separation_m"] == pytest.approx(2.0)


def test_ignores_unrelated_sources():
    conv = SeparationDistanceConverter(robot_a="/robot1", robot_b="/robot2")
    assert conv.convert(_pose("/robot3", 1.0)) is None


def test_updates_with_latest_position():
    conv = SeparationDistanceConverter(robot_a="/robot1", robot_b="/robot2")
    conv.convert(_pose("/robot1", 0.0))
    conv.convert(_pose("/robot2", 4.0, seq=2))
    result = conv.convert(_pose("/robot2", 1.5, seq=3))
    assert result is not None
    assert result["separation_m"] == pytest.approx(1.5)


def _dsl(distance: float, ts: float = 100.0) -> dict:
    return {
        "separation_m": distance,
        "positions": {"/robot1": [0.0, 0.0], "/robot2": [distance, 0.0]},
        "_property_id": "fleet_separation",
        "_timestamp": ts,
        "_input_record_ids": ["a", "b"],
        "_source_name": "fleet",
    }


def test_verdict_edge_triggered_on_threshold_crossings():
    svc = SeparationDistanceVerdict(min_distance=1.0)
    assert svc.evaluate(_dsl(4.0)) is None  # satisfied from the start: no edge
    verdict = svc.evaluate(_dsl(0.8, ts=101.0))
    assert verdict is not None and verdict.result is False
    assert verdict.details["separation_m"] == pytest.approx(0.8)
    assert svc.evaluate(_dsl(0.5, ts=102.0)) is None  # still violating: no edge
    recovery = svc.evaluate(_dsl(1.4, ts=103.0))
    assert recovery is not None and recovery.result is True
    assert recovery.timestamp == pytest.approx(103.0)


def test_verdict_property_id_falls_back_to_record():
    svc = SeparationDistanceVerdict(min_distance=1.0)
    verdict = svc.evaluate(_dsl(0.2))
    assert verdict is not None
    assert verdict.property_id == "fleet_separation"
