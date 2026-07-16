#!/usr/bin/env python3
"""Estimate a remote-minus-local wall-clock offset over one SSH session.

Each sample brackets a remote ``time.time_ns()`` reply with two local reads.
The midpoint estimate is the usual NTP-style approximation. The reported
offset is the median of the five lowest-RTT samples, and its uncertainty is
bounded by half of the largest RTT in that selected set.
"""

from __future__ import annotations

import argparse
import json
import shlex
import socket
import statistics
import subprocess
import time


REMOTE_CODE = (
    "import sys,time; "
    "[(print(time.time_ns(), flush=True)) for _line in sys.stdin]"
)


def measure(host: str, remote_python: str, count: int) -> dict:
    remote_command = (
        f"{shlex.quote(remote_python)} -u -c {shlex.quote(REMOTE_CODE)}"
    )
    proc = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host,
         remote_command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None
    samples = []
    try:
        for _ in range(count):
            before = time.time_ns()
            proc.stdin.write("probe\n")
            proc.stdin.flush()
            reply = proc.stdout.readline()
            after = time.time_ns()
            if not reply:
                stderr = proc.stderr.read() if proc.stderr is not None else ""
                raise RuntimeError(f"SSH clock probe ended early: {stderr.strip()}")
            remote = int(reply.strip())
            midpoint = (before + after) / 2
            samples.append(
                {
                    "offset_seconds": (remote - midpoint) / 1e9,
                    "rtt_ms": (after - before) / 1e6,
                }
            )
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)

    selected = sorted(samples, key=lambda item: item["rtt_ms"])[: min(5, count)]
    estimate = statistics.median(item["offset_seconds"] for item in selected)
    uncertainty = max(item["rtt_ms"] for item in selected) / 2
    return {
        "local_host": socket.gethostname(),
        "remote_host": host,
        "offset_definition": "remote_clock_minus_local_clock",
        "samples": samples,
        "estimate": {
            "offset_seconds": estimate,
            "offset_ms": estimate * 1000,
            "uncertainty_ms": uncertainty,
            "selected_samples": len(selected),
            "minimum_rtt_ms": min(item["rtt_ms"] for item in samples),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--remote-python", default="python3")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")
    report = measure(args.host, args.remote_python, args.count)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as out:
            out.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

