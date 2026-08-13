#!/usr/bin/env python3
"""Sample CPU % and RSS of processes from /proc into a CSV file.

Usage:
    python3 eval/common/proc_sampler.py --pid 1234 [--pid 5678] \
        --interval 1.0 --out samples.csv

Sampling stops when all watched PIDs have exited (or on SIGINT/SIGTERM).
CPU % is the utime+stime delta over the sampling interval, normalised to a
single core (values above 100 mean more than one core busy).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


def read_cpu_ticks(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            stat = f.read().decode("ascii", "replace")
    except OSError:
        return None
    # Fields 14 (utime) and 15 (stime), counted 1-based after the comm field,
    # which may contain spaces and is enclosed in parentheses.
    rest = stat.rsplit(")", 1)[-1].split()
    return int(rest[11]) + int(rest[12])


def read_rss_bytes(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/statm", "rb") as f:
            return int(f.read().split()[1]) * PAGE_SIZE
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, action="append", required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    stop = False

    def _on_signal(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    last_ticks: dict[int, int] = {}
    last_time: dict[int, float] = {}

    with open(args.out, "w", encoding="utf-8") as out:
        out.write("time,pid,cpu_percent,rss_mb\n")
        while not stop:
            alive = 0
            now = time.time()
            for pid in args.pid:
                ticks = read_cpu_ticks(pid)
                rss = read_rss_bytes(pid)
                if ticks is None or rss is None:
                    continue
                alive += 1
                if pid in last_ticks:
                    dt = now - last_time[pid]
                    if dt > 0:
                        cpu = (ticks - last_ticks[pid]) / CLK_TCK / dt * 100.0
                        out.write(
                            f"{now:.3f},{pid},{cpu:.2f},{rss / 1e6:.2f}\n"
                        )
                last_ticks[pid] = ticks
                last_time[pid] = now
            out.flush()
            if alive == 0:
                break
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
