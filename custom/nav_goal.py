"""Navigation-goal deadline property for Nav2's /navigate_to_pose action.

`NavGoalDeadlineConverter` consumes the action's feedback and status records
(collected by the monitor's ActionCollector) and emits one DSL record per
goal, the first time the goal's outcome is decidable:

  * a feedback or status record arrives more than `deadline_sec` after the
    goal was first seen and the goal has not succeeded -> violated
    (detected in flight, before the goal terminates);
  * the goal reaches a terminal status: SUCCEEDED within the deadline ->
    satisfied; SUCCEEDED late, CANCELED, or ABORTED -> violated.

Elapsed time is judged on record collection timestamps (wall clock), so the
offline ground-truth check can recompute the same quantity from the mission
log. `NavGoalDeadlineVerdict` turns each DSL record into a Verdict.
"""

from __future__ import annotations

import time
from typing import Any

from converter import DataConverter
from data_record import DataRecord
from verdict import Verdict, VerdictService

STATUS_SUCCEEDED = 4
STATUS_CANCELED = 5
STATUS_ABORTED = 6
_TERMINAL = {STATUS_SUCCEEDED, STATUS_CANCELED, STATUS_ABORTED}


def _goal_key(goal_id: Any) -> str | None:
    if isinstance(goal_id, dict):
        uuid = goal_id.get("uuid")
        if uuid is not None:
            return ",".join(str(b) for b in uuid)
    return None


class NavGoalDeadlineConverter(DataConverter):
    name = "NavGoalDeadlineConverter"

    def __init__(
        self,
        action_name: str = "/navigate_to_pose",
        deadline_sec: float = 35.0,
        property_id: str = "nav_goal_deadline",
    ):
        self.action_name = action_name
        self.deadline_sec = float(deadline_sec)
        self.property_id = property_id
        self._first_seen: dict[str, tuple[float, str]] = {}  # key -> (ts, record_id)
        self._decided: set[str] = set()

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_name != self.action_name or record.source_type != "action":
            return None
        if record.phase == "feedback":
            key = _goal_key(record.data.get("goal_id"))
            return self._on_progress(key, record) if key else None
        if record.phase == "status":
            for entry in record.data.get("status_list", []):
                key = _goal_key(entry.get("goal_info", {}).get("goal_id"))
                if key is None or key in self._decided:
                    continue
                status = entry.get("status")
                if status in _TERMINAL:
                    return self._decide(key, record, status)
                emitted = self._on_progress(key, record)
                if emitted is not None:
                    return emitted
        return None

    def _on_progress(self, key: str, record: DataRecord) -> dict | None:
        if key in self._decided:
            return None
        first_ts, _ = self._first_seen.setdefault(
            key, (record.timestamp, record.record_id)
        )
        if record.timestamp - first_ts > self.deadline_sec:
            return self._emit(key, record, ok=False, status=None, in_flight=True)
        return None

    def _decide(self, key: str, record: DataRecord, status: int) -> dict:
        elapsed_known = key in self._first_seen
        first_ts = self._first_seen.get(key, (record.timestamp, record.record_id))[0]
        within = (record.timestamp - first_ts) <= self.deadline_sec
        ok = status == STATUS_SUCCEEDED and within and elapsed_known
        return self._emit(key, record, ok=ok, status=status, in_flight=False)

    def _emit(
        self,
        key: str,
        record: DataRecord,
        ok: bool,
        status: int | None,
        in_flight: bool,
    ) -> dict:
        self._decided.add(key)
        first_ts, first_id = self._first_seen.get(
            key, (record.timestamp, record.record_id)
        )
        return {
            "goal_within_deadline": ok,
            "elapsed_sec": record.timestamp - first_ts,
            "deadline_sec": self.deadline_sec,
            "terminal_status": status,
            "detected_in_flight": in_flight,
            "goal_key": key,
            "_property_id": self.property_id,
            "_timestamp": record.timestamp,
            "_source_name": self.action_name,
            "_input_record_ids": [
                rid for rid in dict.fromkeys([first_id, record.record_id]) if rid
            ],
        }


class NavGoalDeadlineVerdict(VerdictService):
    name = "NavGoalDeadlineVerdict"

    def __init__(self, property_id: str = "nav_goal_deadline"):
        self.property_id = property_id

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        if not isinstance(dsl_record, dict) or "goal_within_deadline" not in dsl_record:
            return None
        return Verdict(
            timestamp=float(dsl_record.get("_timestamp", time.time())),
            property_id=self.property_id,
            result=bool(dsl_record["goal_within_deadline"]),
            details={
                "elapsed_sec": dsl_record.get("elapsed_sec"),
                "deadline_sec": dsl_record.get("deadline_sec"),
                "terminal_status": dsl_record.get("terminal_status"),
                "detected_in_flight": dsl_record.get("detected_in_flight"),
                "goal_key": dsl_record.get("goal_key"),
            },
        )
