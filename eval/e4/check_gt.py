#!/usr/bin/env python3
"""E4 ground-truth validation of the fleet-separation verdicts.

Computes the physical separation timeline from the simulator ground-truth
pose log (gt_logger.py CSV) and checks it against the verdict stream:

  * every online violation episode (violation verdict .. next recovery)
    must overlap a ground-truth sub-threshold episode, and vice versa
    (tolerance for AMCL estimation error and clock skew: --slack seconds);
  * reports the true minimum separation per episode (two TB3 waffles in
    bumper contact are ~0.25 m center to center — smaller AMCL-based
    readings are estimation error, not physics).
  * when a mission log is supplied, every navigation goal must report
    SUCCEEDED and the corresponding Gazebo world pose must be within the
    configured tolerance of the requested map-frame goal. The E4 map and
    Gazebo world are registered, so this catches AMCL / initial-pose errors
    that a relative-separation check cannot detect.

Usage:
    python3 eval/e4/check_gt.py --gt gt_poses.csv \
        --verdicts verdicts_separation_*.jsonl --min-distance 1.0 \
        [--mission-log mission_log.json] [--goal-tolerance 0.5] \
        [--slack 3.0] [--out gt.json]

Exit code 0 when the episodes correspond one to one.
"""

from __future__ import annotations

import argparse
import json
import math
import sys


def episodes_from_gt(path: str, threshold: float):
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        assert header.startswith("time"), "unexpected gt CSV header"
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            t, x1, y1, x2, y2 = (float(v) for v in parts[:5])
            rows.append((t, x1, y1, x2, y2,
                         math.hypot(x1 - x2, y1 - y2)))
    episodes = []
    current = None
    min_overall = None
    for t, _x1, _y1, _x2, _y2, d in rows:
        min_overall = d if min_overall is None else min(min_overall, d)
        if d < threshold:
            if current is None:
                current = {"start": t, "end": t, "min_m": d}
            else:
                current["end"] = t
                current["min_m"] = min(current["min_m"], d)
        elif current is not None:
            episodes.append(current)
            current = None
    if current is not None:
        episodes.append(current)
    return rows, episodes, min_overall


def episodes_from_verdicts(path: str):
    verdicts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                verdicts.append(json.loads(line))
    episodes = []
    start = None
    for v in verdicts:
        if v.get("result") is False and start is None:
            start = v["timestamp"]
        elif v.get("result") is True and start is not None:
            episodes.append({"start": start, "end": v["timestamp"]})
            start = None
    if start is not None:
        episodes.append({"start": start, "end": None})
    return episodes


def overlaps(a, b, slack: float) -> bool:
    a_end = a["end"] if a["end"] is not None else a["start"]
    b_end = b["end"] if b["end"] is not None else b["start"]
    return a["start"] - slack <= b_end and b["start"] - slack <= a_end


def physical_goal_checks(rows, mission_path: str, tolerance: float):
    with open(mission_path, encoding="utf-8") as f:
        events = json.load(f)["events"]

    sent = {
        (e["leg"], e["robot"]): e
        for e in events
        if e.get("type") == "goal_sent"
    }
    results = {
        (e["leg"], e["robot"]): e
        for e in events
        if e.get("type") == "goal_result"
    }
    checks = []
    all_ok = bool(sent) and set(sent) == set(results)
    for key, goal_event in sent.items():
        result = results.get(key)
        if result is None or not rows:
            checks.append({
                "leg": key[0],
                "robot": key[1],
                "result": None if result is None else result.get("result"),
                "found": False,
                "ok": False,
            })
            all_ok = False
            continue

        t = float(result["t"])
        sample = min(rows, key=lambda row: abs(row[0] - t))
        robot_index = 1 if key[1] == "robot1" else 3
        physical = (sample[robot_index], sample[robot_index + 1])
        goal = tuple(float(v) for v in goal_event["pose"][:2])
        error = math.hypot(physical[0] - goal[0], physical[1] - goal[1])
        check_ok = result.get("result") == "SUCCEEDED" and error <= tolerance
        checks.append({
            "leg": key[0],
            "robot": key[1],
            "result": result.get("result"),
            "found": True,
            "goal_xy": [round(v, 4) for v in goal],
            "gazebo_xy": [round(v, 4) for v in physical],
            "sample_time_offset_s": round(sample[0] - t, 3),
            "position_error_m": round(error, 4),
            "tolerance_m": tolerance,
            "ok": check_ok,
        })
        all_ok = all_ok and check_ok
    return checks, all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--min-distance", type=float, required=True)
    parser.add_argument("--slack", type=float, default=3.0)
    parser.add_argument("--mission-log", default=None)
    parser.add_argument("--goal-tolerance", type=float, default=0.5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    rows, gt_eps, min_overall = episodes_from_gt(args.gt, args.min_distance)
    verdict_eps = episodes_from_verdicts(args.verdicts)

    gt_matched = [any(overlaps(g, v, args.slack) for v in verdict_eps)
                  for g in gt_eps]
    verdict_matched = [any(overlaps(v, g, args.slack) for g in gt_eps)
                       for v in verdict_eps]
    all_ok = all(gt_matched) and all(verdict_matched) and bool(gt_eps)
    goal_checks = []
    if args.mission_log:
        goal_checks, goals_ok = physical_goal_checks(
            rows, args.mission_log, args.goal_tolerance)
        all_ok = all_ok and goals_ok

    report = {
        "min_distance_m": args.min_distance,
        "gt_samples": len(rows),
        "gt_min_separation_m": round(min_overall, 3) if min_overall else None,
        "gt_episodes": [
            {
                "start": g["start"],
                "end": g["end"],
                "duration_s": round(g["end"] - g["start"], 2),
                "min_m": round(g["min_m"], 3),
                "matched_by_verdicts": m,
            }
            for g, m in zip(gt_eps, gt_matched)
        ],
        "verdict_episodes": [
            {"start": v["start"], "end": v["end"], "matched_by_gt": m}
            for v, m in zip(verdict_eps, verdict_matched)
        ],
        "physical_goal_checks": goal_checks,
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
