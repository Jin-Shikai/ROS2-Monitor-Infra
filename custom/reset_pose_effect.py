"""Check that a successful `/reset_pose` call is followed by odom near origin."""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path
from verdict import Verdict, VerdictService


def _field(data: dict, path: str, default: float = 0.0):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else default


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
        self.pending: dict[str, Any] | None = None
        self.latest_odom: tuple[str, float, float] | None = None
        self._emit: Callable[[Any], None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, emit: Callable[[Any], None]) -> None:
        self._emit = emit
        self._thread = threading.Thread(target=self._watch_deadline, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_name == self.service_name and record.phase == "response":
            if record.data.get("success") is True:
                self.pending = {
                    "time": record.timestamp,
                    "record_id": record.record_id,
                    "sequence_number": record.metadata.get("sequence_number"),
                }
            return None

        if record.source_name != self.odom_name:
            return None
        distance = self._odom_distance(record)
        self.latest_odom = (record.record_id, record.timestamp, distance)
        if not self.pending:
            return None
        if distance <= self.tolerance_m:
            return self._finish(True, record.timestamp, distance)
        if record.timestamp - float(self.pending["time"]) > self.deadline_sec:
            return self._finish(False, record.timestamp, distance)
        return None

    def _watch_deadline(self) -> None:
        while not self._stop.wait(0.05):
            if not self.pending or self._emit is None:
                continue
            if time.time() - float(self.pending["time"]) > self.deadline_sec:
                distance = self.latest_odom[2] if self.latest_odom else None
                self._emit(self._finish(False, time.time(), distance))

    def _odom_distance(self, record: DataRecord) -> float:
        x = float(_field(record.data, "pose.pose.position.x"))
        y = float(_field(record.data, "pose.pose.position.y"))
        return math.hypot(x, y)

    def _finish(self, ok: bool, ts: float, distance: float | None) -> dict:
        pending = self.pending or {"time": ts, "record_id": "", "sequence_number": None}
        self.pending = None
        input_ids = [pending["record_id"]]
        if self.latest_odom:
            input_ids.append(self.latest_odom[0])
        return {
            "reset_effect_ok": ok,
            "elapsed_sec": ts - float(pending["time"]),
            "distance_to_origin": distance,
            "deadline_sec": self.deadline_sec,
            "tolerance_m": self.tolerance_m,
            "sequence_number": pending["sequence_number"],
            "_property_id": self.property_id,
            "_timestamp": ts,
            "_source_name": "reset_pose_effect",
            "_input_record_ids": input_ids,
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
