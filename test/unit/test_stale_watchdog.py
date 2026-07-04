"""Unit tests for the self-scheduled stale-source watchdog converter."""

from __future__ import annotations

import time

from custom.stale_watchdog import StaleWatchdogConverter
from data_record import DataRecord


def _record(seq=1):
    return DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom", msg_type="m", data={"v": 1}, seq=seq,
    )


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_watchdog_emits_once_when_source_goes_silent():
    emitted = []
    watchdog = StaleWatchdogConverter(timeout_sec=0.1, check_interval_sec=0.02)
    watchdog.start(emitted.append)
    try:
        assert watchdog.convert(_record()) is None
        assert _wait_for(lambda: len(emitted) == 1)
        time.sleep(0.15)
        assert len(emitted) == 1  # fires once per silence, not per check
        assert emitted[0]["silent_sec"] > 0.1
        assert emitted[0]["_property_id"] == "source_liveness"
    finally:
        watchdog.stop()


def test_watchdog_rearms_after_traffic_resumes():
    emitted = []
    watchdog = StaleWatchdogConverter(timeout_sec=0.1, check_interval_sec=0.02)
    watchdog.start(emitted.append)
    try:
        watchdog.convert(_record(1))
        assert _wait_for(lambda: len(emitted) == 1)
        watchdog.convert(_record(2))
        assert _wait_for(lambda: len(emitted) == 2)
    finally:
        watchdog.stop()


def test_watchdog_silent_before_first_record():
    emitted = []
    watchdog = StaleWatchdogConverter(timeout_sec=0.05, check_interval_sec=0.02)
    watchdog.start(emitted.append)
    try:
        time.sleep(0.2)
        assert emitted == []
    finally:
        watchdog.stop()
