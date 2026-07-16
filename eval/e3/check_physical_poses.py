#!/usr/bin/env python3
"""Validate E3 initial and successful goal poses against Gazebo ground truth."""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any


def load_gt(path: str) -> list[tuple[float, float, float]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        if len(header) != 3 or header[0] != "time":
            raise ValueError(f"unexpected single-robot GT header: {header}")
        for line in f:
            values = line.strip().split(",")
            if len(values) == 3:
                rows.append(tuple(float(v) for v in values))
    return rows


def check_events(
    rows: list[tuple[float, float, float]],
    events: list[dict[str, Any]],
    tolerance: float,
) -> tuple[list[dict[str, Any]], bool]:
    sent = {e["goal"]: e for e in events if e.get("type") == "goal_sent"}
    checks = []
    targets = []
    initial = next((e for e in events if e.get("type") == "initial_pose"), None)
    if initial is not None:
        targets.append(("initial", initial, initial))
    for result in (e for e in events if e.get("type") == "goal_result"):
        if result.get("result") == "SUCCEEDED" and result.get("goal") in sent:
            targets.append((result["goal"], result, sent[result["goal"]]))

    all_ok = bool(rows) and initial is not None and bool(sent)
    for name, timed_event, pose_event in targets:
        if not rows:
            checks.append({"target": name, "found": False, "ok": False})
            all_ok = False
            continue
        sample = min(rows, key=lambda row: abs(row[0] - float(timed_event["t"])))
        goal = tuple(float(v) for v in pose_event["pose"][:2])
        error = math.hypot(sample[1] - goal[0], sample[2] - goal[1])
        ok = error <= tolerance
        checks.append({
            "target": name,
            "goal_xy": [round(v, 4) for v in goal],
            "gazebo_xy": [round(sample[1], 4), round(sample[2], 4)],
            "sample_time_offset_s": round(sample[0] - float(timed_event["t"]), 3),
            "position_error_m": round(error, 4),
            "tolerance_m": tolerance,
            "found": True,
            "ok": ok,
        })
        all_ok = all_ok and ok

    successful = [e for e in events
                  if e.get("type") == "goal_result" and e.get("result") == "SUCCEEDED"]
    all_ok = all_ok and len(checks) == 1 + len(successful)
    return checks, all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--mission-log", required=True)
    parser.add_argument("--tolerance", type=float, default=0.5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with open(args.mission_log, encoding="utf-8") as f:
        events = json.load(f)["events"]
    rows = load_gt(args.gt)
    checks, ok = check_events(rows, events, args.tolerance)
    report = {"gt_samples": len(rows), "pose_checks": checks, "ok": ok}
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
