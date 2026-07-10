#!/usr/bin/env python3
"""E2-specific correctness checks for the service and action observables.

1. Reset-pose service-effect property: the fixture makes odd service calls
   effective and even calls ineffective, so the remote verdict stream must
   alternate true, false, true, ... and every verdict must be attributed to
   one /reset_pose service response record and one /odom topic record.

2. Fibonacci action: every goal of order N yields N-1 feedback records and
   one SUCCEEDED entry (status 4) on the status topic. Goals still in
   flight when the run stops are tolerated (counts may lag by one goal).

Usage:
    python3 eval/e2/check_extras.py --records <records.jsonl> \
        --reset-verdicts <verdicts_reset.jsonl> --action-log <action.log> \
        --order 6 [--out extras.json]

Exit code 0 when all checks pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SUCCEEDED = 4


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_reset(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    expected = True  # odd calls (first, third, ...) actually reset the pose
    alternating = True
    attribution_ok = True
    for v in verdicts:
        if bool(v.get("result")) != expected:
            alternating = False
        expected = not expected
        ids = v.get("input_record_ids") or []
        if not (
            any(":service:/reset_pose:" in i for i in ids)
            and any(":topic:/odom:" in i for i in ids)
        ):
            attribution_ok = False
    return {
        "verdicts": len(verdicts),
        "starts_with_effective": bool(verdicts[0]["result"]) if verdicts else None,
        "alternating": alternating,
        "attribution_ok": attribution_ok,
        "ok": bool(verdicts) and alternating and attribution_ok,
    }


def check_action(
    records: list[dict[str, Any]], goals_sent: int, order: int
) -> dict[str, Any]:
    action = [r for r in records if r.get("source_type") == "action"]
    feedback = [r for r in action if r.get("phase") == "feedback"]
    status = [r for r in action if r.get("phase") == "status"]

    succeeded_goal_ids = set()
    for r in status:
        for entry in r.get("data", {}).get("status_list", []):
            if entry.get("status") == SUCCEEDED:
                goal_id = json.dumps(
                    entry.get("goal_info", {}).get("goal_id"), sort_keys=True
                )
                succeeded_goal_ids.add(goal_id)

    succeeded = len(succeeded_goal_ids)
    # The last goal may still be executing at shutdown.
    complete_goals = min(goals_sent, succeeded + 1)
    ok = (
        goals_sent > 0
        and succeeded >= goals_sent - 1
        and len(feedback) >= (complete_goals - 1) * (order - 1)
    )
    return {
        "goals_sent": goals_sent,
        "feedback_records": len(feedback),
        "expected_feedback_per_goal": order - 1,
        "status_records": len(status),
        "succeeded_goals": succeeded,
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--reset-verdicts", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--order", type=int, default=6)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    records = [
        r for r in load_jsonl(args.records) if r.get("_type", "data") == "data"
    ]
    with open(args.action_log, encoding="utf-8") as f:
        goals_sent = sum(1 for line in f if "GOAL: sent" in line)

    report = {
        "reset": check_reset(load_jsonl(args.reset_verdicts)),
        "action": check_action(records, goals_sent, args.order),
    }
    report["ok"] = report["reset"]["ok"] and report["action"]["ok"]

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
