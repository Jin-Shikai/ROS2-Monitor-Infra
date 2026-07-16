#!/usr/bin/env python3
"""Log simulator ground-truth robot poses to CSV.

Streams Gazebo's `/world/<world>/dynamic_pose/info` (gz.msgs.Pose_V) via the
`gz topic` CLI in JSON mode, extracts the two robots' world positions, and
writes wall-clock-stamped CSV rows, downsampled to at most `--rate` rows per
second. This is the reference for validating the fleet-separation verdicts
against physical truth rather than against AMCL estimates only (AMCL error
grows during robot-robot contact because wheel slip corrupts odometry).

    python3 eval/e4/gt_logger.py --out gt_poses.csv [--world default]
        [--robots robot1,robot2] [--rate 10]

Runs until SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--world", default="default")
    parser.add_argument("--robots", default="robot1,robot2")
    parser.add_argument("--rate", type=float, default=10.0)
    args = parser.parse_args()

    robots = [r.strip() for r in args.robots.split(",") if r.strip()]
    topic = f"/world/{args.world}/dynamic_pose/info"
    proc = subprocess.Popen(
        ["gz", "topic", "-e", "-t", topic, "--json-output"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    stop = False

    def handle(_sig, _frm):
        nonlocal stop
        stop = True
        proc.terminate()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    min_period = 1.0 / args.rate
    last_write = 0.0
    rows = 0
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("time," + ",".join(f"{r}_x,{r}_y" for r in robots) + "\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            if stop:
                break
            now = time.time()
            if now - last_write < min_period:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            poses = {p.get("name"): p.get("position", {})
                     for p in msg.get("pose", [])}
            if not all(r in poses for r in robots):
                continue
            values = []
            for r in robots:
                values.append(f"{poses[r].get('x', 0.0):.4f}")
                values.append(f"{poses[r].get('y', 0.0):.4f}")
            f.write(f"{now:.3f}," + ",".join(values) + "\n")
            f.flush()
            last_write = now
            rows += 1
    print(f"gt_logger: wrote {rows} rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
