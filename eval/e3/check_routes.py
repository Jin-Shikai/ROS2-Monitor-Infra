#!/usr/bin/env python3
"""Check that E3 barriers produce the intended topological route changes."""

from __future__ import annotations

import argparse
import json
import sys


def load_gt(path: str) -> list[tuple[float, float, float]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        f.readline()
        for line in f:
            values = line.strip().split(",")
            if len(values) == 3:
                rows.append(tuple(float(v) for v in values))
    return rows


def crossing_y_values(
    rows: list[tuple[float, float, float]], start: float, end: float, x_gate: float
) -> list[float]:
    segment = [row for row in rows if start <= row[0] <= end]
    crossings = []
    for left, right in zip(segment, segment[1:]):
        x1, x2 = left[1], right[1]
        if (x1 - x_gate) * (x2 - x_gate) > 0 or x1 == x2:
            continue
        fraction = (x_gate - x1) / (x2 - x1)
        crossings.append(left[2] + fraction * (right[2] - left[2]))
    return crossings


def analyze(rows, events, x_gate: float = 1.4, opening_threshold: float = 0.75):
    sent = {e["goal"]: e for e in events if e.get("type") == "goal_sent"}
    results = {e["goal"]: e for e in events if e.get("type") == "goal_result"}
    goals = []
    crossings = {}
    for goal in ("A", "B", "C"):
        if goal not in sent or goal not in results:
            crossings[goal] = []
            goals.append({"goal": goal, "found": False})
            continue
        ys = crossing_y_values(rows, sent[goal]["t"], results[goal]["t"], x_gate)
        crossings[goal] = ys
        goals.append({
            "goal": goal,
            "result": results[goal].get("result"),
            "crossing_y": [round(y, 3) for y in ys],
            "route": (
                "upper" if any(y > opening_threshold for y in ys)
                else "lower" if any(y < -opening_threshold for y in ys)
                else "no_partition_crossing"
            ),
            "found": True,
        })

    a_lower = any(y < -opening_threshold for y in crossings["A"])
    b_upper = any(y > opening_threshold for y in crossings["B"])
    c_blocked = not crossings["C"]
    checks = {
        "goal_a_uses_lower_baseline": a_lower,
        "goal_b_forced_to_upper": b_upper,
        "goal_c_did_not_cross_closed_partition": c_blocked,
    }
    return goals, checks, all(checks.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--mission-log", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    with open(args.mission_log, encoding="utf-8") as f:
        events = json.load(f)["events"]
    rows = load_gt(args.gt)
    goals, checks, ok = analyze(rows, events)
    report = {"partition_x": 1.4, "goals": goals, "checks": checks, "ok": ok}
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
