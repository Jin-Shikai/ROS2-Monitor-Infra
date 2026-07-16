#!/usr/bin/env python3
"""Portable ``ps``-based CPU/RSS sampler for Linux and macOS.

The CSV has the same four columns as ``proc_sampler.py``. With
``--include-children``, each row is keyed by the requested root PID but sums
the CPU and RSS of that root and all descendants visible in the current
process table. This is useful for a ``ros2 launch`` process tree on Linux; on
macOS it avoids the unavailable ``/proc`` filesystem.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import time


def process_table() -> dict[int, tuple[int, float, int]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,%cpu=,rss="],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    rows: dict[int, tuple[int, float, int]] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
            cpu, rss_kb = float(parts[2].replace(",", ".")), int(parts[3])
        except ValueError:
            continue
        rows[pid] = (ppid, cpu, rss_kb)
    return rows


def descendants(root: int, table: dict[int, tuple[int, float, int]]) -> set[int]:
    selected = {root} if root in table else set()
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _cpu, _rss) in table.items():
            if pid not in selected and ppid in selected:
                selected.add(pid)
                changed = True
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, action="append", required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-children", action="store_true")
    args = parser.parse_args()

    stop = False

    def on_signal(*_args) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    with open(args.out, "w", encoding="utf-8") as out:
        out.write("time,pid,cpu_percent,rss_mb\n")
        while not stop:
            try:
                table = process_table()
            except (OSError, subprocess.CalledProcessError):
                break
            alive = 0
            now = time.time()
            for root in args.pid:
                selected = (
                    descendants(root, table)
                    if args.include_children
                    else ({root} if root in table else set())
                )
                if not selected:
                    continue
                alive += 1
                cpu = sum(table[pid][1] for pid in selected)
                rss_mb = sum(table[pid][2] for pid in selected) / 1000.0
                out.write(f"{now:.3f},{root},{cpu:.2f},{rss_mb:.2f}\n")
            out.flush()
            if alive == 0:
                break
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

