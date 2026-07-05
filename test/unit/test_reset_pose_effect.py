from __future__ import annotations

import time

from custom.reset_pose_effect import ResetPoseEffectConverter, ResetPoseEffectVerdict
from data_record import DataRecord


def _reset(ts: float = 1.0) -> DataRecord:
    return DataRecord(
        session_id="S",
        record_id="S:service:/reset_pose:response:1",
        source_type="service",
        source_name="/reset_pose",
        phase="response",
        timestamp=ts,
        data={"success": True},
        metadata={"sequence_number": 7},
    )


def _odom(x: float, ts: float = 1.2) -> DataRecord:
    return DataRecord(
        session_id="S",
        record_id=f"S:topic:/odom:-:{int(ts * 10)}",
        source_type="topic",
        source_name="/odom",
        timestamp=ts,
        data={"pose.pose.position.x": x, "pose.pose.position.y": 0.0},
    )


def test_reset_success_followed_by_origin_emits_pass_record():
    conv = ResetPoseEffectConverter(deadline_sec=1.0, tolerance_m=0.05)

    assert conv.convert(_reset()) is None
    record = conv.convert(_odom(0.02))

    assert record["reset_effect_ok"] is True
    assert record["sequence_number"] == 7
    assert len(record["_input_record_ids"]) == 2


def test_reset_success_without_origin_emits_fail_record():
    conv = ResetPoseEffectConverter(deadline_sec=1.0, tolerance_m=0.05)

    conv.convert(_reset(ts=1.0))
    record = conv.convert(_odom(0.5, ts=2.2))

    assert record["reset_effect_ok"] is False
    assert record["distance_to_origin"] == 0.5


def test_reset_timeout_can_fire_without_new_odom():
    emitted = []
    conv = ResetPoseEffectConverter(deadline_sec=0.05)
    conv.start(emitted.append)
    try:
        conv.convert(_reset(ts=time.time()))
        time.sleep(0.15)
        assert emitted[0]["reset_effect_ok"] is False
    finally:
        conv.stop()


def test_verdict_passes_through_service_effect_result():
    verdict = ResetPoseEffectVerdict()
    result = verdict.evaluate({
        "reset_effect_ok": False,
        "elapsed_sec": 1.2,
        "distance_to_origin": 0.5,
        "deadline_sec": 1.0,
        "tolerance_m": 0.05,
        "sequence_number": 7,
        "_timestamp": 2.2,
    })

    assert result.property_id == "reset_pose_effect"
    assert result.result is False
    assert result.details["sequence_number"] == 7
