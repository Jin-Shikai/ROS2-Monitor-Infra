#!/usr/bin/env python3
"""E4 fleet-separation correctness check: verdicts vs. an offline oracle.

The oracle replays the recorded AMCL pose records in collection order,
maintains each robot's latest map-frame position, recomputes the pairwise
distance after every update, and derives the expected edge-triggered
transition sequence for the predicate `distance >= min_distance` (initial
state: satisfied). The verdict stream produced online must match this
sequence one to one: same number of transitions, same polarity, same
triggering records (`input_record_ids`), same input timestamps, and a
recomputed distance identical to the reported one.

With --mission-log, additionally checks the mission-level expectation that
every patrol leg contains at least one separation violation (the crossing).

Usage:
    python3 eval/e4/check_separation.py --records e4mon_*.jsonl \
        --verdicts verdicts_separation_*.jsonl --min-distance 1.0 \
        [--mission-log mission_log.json] [--out separation.json]

Exit code 0 when everything matches.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

POSE_SUFFIX = "/amcl_pose"


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def oracle_transitions(
    records: list[dict[str, Any]], min_distance: float
) -> tuple[list[dict[str, Any]], float | None, int]:
    latest: dict[str, tuple[float, float, str, float]] = {}
    transitions: list[dict[str, Any]] = []
    violating = False
    min_seen: float | None = None
    samples = 0
    for rec in records:
        if rec.get("_type") != "data":
            continue
        source = rec.get("source_name", "")
        if not source.endswith(POSE_SUFFIX):
            continue
        robot = source[: -len(POSE_SUFFIX)]
        data = rec.get("data", {})
        x = data.get("pose.pose.position.x")
        y = data.get("pose.pose.position.y")
        if x is None or y is None:
            continue
        latest[robot] = (float(x), float(y), rec["record_id"], rec["timestamp"])
        if len(latest) < 2:
            continue
        (xa, ya, aid, ats), (xb, yb, bid, bts) = latest.values()
        distance = math.hypot(xa - xb, ya - yb)
        samples += 1
        min_seen = distance if min_seen is None else min(min_seen, distance)
        now_violating = distance < min_distance
        if now_violating != violating:
            violating = now_violating
            transitions.append(
                {
                    "result": not violating,
                    "separation_m": distance,
                    "timestamp": max(ats, bts),
                    "input_record_ids": sorted([aid, bid]),
                }
            )
    return transitions, min_seen, samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--min-distance", type=float, required=True)
    parser.add_argument("--mission-log", default=None)
    parser.add_argument(
        "--clock-offset",
        type=float,
        default=0.0,
        help="Seconds to subtract when the verdict host clock is ahead of "
        "the record host clock (distributed runs).",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    records = load_jsonl(args.records)
    verdicts = load_jsonl(args.verdicts)
    expected, min_seen, samples = oracle_transitions(records, args.min_distance)

    matches = []
    all_ok = len(expected) == len(verdicts)
    latencies = []
    for exp, verdict in zip(expected, verdicts):
        polarity = bool(verdict.get("result")) == exp["result"]
        distance_ok = (
            abs(verdict.get("details", {}).get("separation_m", 1e9)
                - exp["separation_m"]) < 1e-9
        )
        ids_ok = sorted(verdict.get("input_record_ids", [])) == exp["input_record_ids"]
        ts_ok = abs(verdict.get("timestamp", 0) - exp["timestamp"]) < 1e-6
        emitted_at = verdict.get("emitted_at")
        latency = None
        if emitted_at is not None:
            latency = emitted_at - exp["timestamp"] - args.clock_offset
            latencies.append(latency)
        entry_ok = polarity and distance_ok and ids_ok and ts_ok
        matches.append(
            {
                "expected_result": exp["result"],
                "verdict_result": bool(verdict.get("result")),
                "separation_m": round(exp["separation_m"], 4),
                "polarity_match": polarity,
                "distance_match": distance_ok,
                "record_ids_match": ids_ok,
                "timestamp_match": ts_ok,
                "detection_latency_ms": (
                    round(latency * 1000, 2) if latency is not None else None
                ),
            }
        )
        all_ok = all_ok and entry_ok

    legs = []
    if args.mission_log:
        with open(args.mission_log, encoding="utf-8") as f:
            events = json.load(f)["events"]
        violation_times = [
            e["timestamp"] for e in expected if not e["result"]
        ]
        for leg_id in ("1", "2"):
            sent = [e["t"] for e in events
                    if e["type"] == "goal_sent" and e["leg"] == leg_id]
            done = [e["t"] for e in events
                    if e["type"] == "leg_done" and e["leg"] == leg_id]
            if not sent or not done:
                legs.append({"leg": leg_id, "found": False, "violation_in_leg": False})
                all_ok = False
                continue
            start, end = min(sent), max(done)
            hit = any(start <= t <= end for t in violation_times)
            legs.append(
                {
                    "leg": leg_id,
                    "found": True,
                    "start": start,
                    "end": end,
                    "violation_in_leg": hit,
                }
            )
            all_ok = all_ok and hit

    report = {
        "min_distance_m": args.min_distance,
        "pose_pair_samples": samples,
        "min_separation_seen_m": round(min_seen, 4) if min_seen is not None else None,
        "expected_transitions": len(expected),
        "verdicts": len(verdicts),
        "matches": matches,
        "detection_latency_ms": (
            {
                "mean": round(sum(latencies) / len(latencies) * 1000, 2),
                "max": round(max(latencies) * 1000, 2),
            }
            if latencies
            else None
        ),
        "legs": legs,
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
