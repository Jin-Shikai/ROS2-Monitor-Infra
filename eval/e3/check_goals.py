#!/usr/bin/env python3
"""E3 goal-deadline correctness check: verdicts vs. mission ground truth.

The mission log records, for every goal, when it was sent, when it finished,
its measured duration, and its outcome. The expected verdict for a goal is
therefore:

    satisfied  iff  result == SUCCEEDED and duration_sec <= deadline

The nav-goal verdict stream (one verdict per goal, in mission order) must
match this expectation goal by goal. For goals whose duration exceeded the
deadline but which still terminated later, the verdict should additionally
have been emitted in flight (emitted_at before the goal's end time).

Usage:
    python3 eval/e3/check_goals.py --mission-log mission_log.json \
        --verdicts verdicts_nav_*.jsonl --deadline 35 [--out goals.json]

Exit code 0 when all goals match.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-log", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with open(args.mission_log, encoding="utf-8") as f:
        events = json.load(f)["events"]
    results = [e for e in events if e["type"] == "goal_result"]
    verdicts = load_jsonl(args.verdicts)

    goals = []
    all_ok = len(results) == len(verdicts)
    for expected_event, verdict in zip(results, verdicts):
        expected_ok = (
            expected_event["result"] == "SUCCEEDED"
            and expected_event["duration_sec"] <= args.deadline
        )
        polarity_match = bool(verdict.get("result")) == expected_ok

        # A goal that overran the deadline but terminated anyway should have
        # been flagged before its end (in-flight detection).
        in_flight_expected = (
            not expected_ok and expected_event["duration_sec"] > args.deadline
        )
        emitted_at = verdict.get("emitted_at")
        in_flight_ok = (
            not in_flight_expected
            or (emitted_at is not None and emitted_at < expected_event["t"] + 0.5)
        )

        goals.append(
            {
                "goal": expected_event["goal"],
                "mission_result": expected_event["result"],
                "mission_duration_sec": round(expected_event["duration_sec"], 2),
                "expected_ok": expected_ok,
                "verdict_ok": bool(verdict.get("result")),
                "polarity_match": polarity_match,
                "detected_in_flight": verdict.get("details", {}).get(
                    "detected_in_flight"
                ),
                "in_flight_check": in_flight_ok,
            }
        )
        all_ok = all_ok and polarity_match and in_flight_ok

    report = {
        "deadline_sec": args.deadline,
        "mission_goals": len(results),
        "nav_verdicts": len(verdicts),
        "goals": goals,
        "ok": all_ok,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
