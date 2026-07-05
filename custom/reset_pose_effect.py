from __future__ import annotations

import math
import time
from typing import Any

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path
from verdict import Verdict, VerdictService


def _field(data: dict, path: str) -> float:
    if path in data:
        return float(data[path])
    found, value = _get_path(data, path)
    return float(value) if found else 0.0


class ResetPoseEffectConverter(DataConverter):
    name = "ResetPoseEffectConverter"

    def __init__(
        self,
        service_name: str = "/reset_pose",
        odom_name: str = "/odom",
        deadline_sec: float = 1.0,
        tolerance_m: float = 0.05,
        property_id: str = "reset_pose_effect",
    ):
        self.service_name = service_name
        self.odom_name = odom_name
        self.deadline_sec = float(deadline_sec)
        self.tolerance_m = float(tolerance_m)
        self.property_id = property_id
        self.reset: DataRecord | None = None

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_name == self.service_name and record.phase == "response":
            self.reset = record if record.data.get("success") is True else None
            return None
        if record.source_name != self.odom_name or self.reset is None:
            return None

        distance = math.hypot(
            _field(record.data, "pose.pose.position.x"),
            _field(record.data, "pose.pose.position.y"),
        )
        elapsed = record.timestamp - self.reset.timestamp
        if distance <= self.tolerance_m:
            return self._emit(True, record, distance, elapsed)
        if elapsed >= self.deadline_sec:
            return self._emit(False, record, distance, elapsed)
        return None

    def _emit(
        self,
        ok: bool,
        odom: DataRecord,
        distance: float,
        elapsed: float,
    ) -> dict:
        reset = self.reset
        self.reset = None
        return {
            "reset_effect_ok": ok,
            "elapsed_sec": elapsed,
            "distance_to_origin": distance,
            "deadline_sec": self.deadline_sec,
            "tolerance_m": self.tolerance_m,
            "sequence_number": reset.metadata.get("sequence_number") if reset else None,
            "_property_id": self.property_id,
            "_timestamp": odom.timestamp,
            "_source_name": "reset_pose_effect",
            "_input_record_ids": [
                record_id for record_id in [
                    reset.record_id if reset else "",
                    odom.record_id,
                ] if record_id
            ],
        }


class ResetPoseEffectVerdict(VerdictService):
    name = "ResetPoseEffectVerdict"

    def __init__(self, property_id: str = "reset_pose_effect"):
        self.property_id = property_id

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        if not isinstance(dsl_record, dict) or "reset_effect_ok" not in dsl_record:
            return None
        return Verdict(
            timestamp=float(dsl_record.get("_timestamp", time.time())),
            property_id=self.property_id,
            result=bool(dsl_record["reset_effect_ok"]),
            details={
                "elapsed_sec": dsl_record.get("elapsed_sec"),
                "distance_to_origin": dsl_record.get("distance_to_origin"),
                "deadline_sec": dsl_record.get("deadline_sec"),
                "tolerance_m": dsl_record.get("tolerance_m"),
                "sequence_number": dsl_record.get("sequence_number"),
            },
        )
