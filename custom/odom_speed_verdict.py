"""Demo verdict for the `/odom` speed-limit property."""

from __future__ import annotations

import time
from typing import Any

from custom.odom_speed_converter import PROPERTY_ID
from verdict import Verdict, VerdictService


SPEED_LIMIT_MPS = 0.30


class OdomSpeedVerdict(VerdictService):
    name = "OdomSpeedVerdict"

    def __init__(self):
        self._fired = False

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        if not isinstance(dsl_record, dict) or "speed" not in dsl_record:
            return None
        speed = dsl_record["speed"]
        ts = dsl_record.get("_timestamp", time.time())
        breached = speed > SPEED_LIMIT_MPS

        if breached and not self._fired:
            self._fired = True
            return Verdict(
                timestamp=ts,
                property_id=PROPERTY_ID,
                result=False,
                details={
                    "field": "speed",
                    "op": ">",
                    "threshold": SPEED_LIMIT_MPS,
                    "value": speed,
                },
            )
        if not breached and self._fired:
            self._fired = False
            return Verdict(
                timestamp=ts,
                property_id=PROPERTY_ID,
                result=True,
                details={
                    "field": "speed",
                    "value": speed,
                    "note": "breach cleared",
                },
            )
        return None
