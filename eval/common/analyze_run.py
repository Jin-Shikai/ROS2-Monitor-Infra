#!/usr/bin/env python3
"""Analyze one monitoring run: records + verdicts JSONL -> metrics.json.

Computes, for a threshold property re-evaluated offline (the oracle):

- record throughput (total / per source) and record-id sequence gaps;
- verdict correctness: online verdicts matched 1:1 against oracle
  state transitions (matched / missed / spurious, precision / recall);
- detection latency: `emitted_at` (written by TimestampedVerdictFileExporter)
  minus the triggering record's collection timestamp;
- optional process-resource summary from a proc_sampler.py CSV.

Usage:
    python3 eval/common/analyze_run.py \
        --records run_dir/e1_*.jsonl --verdicts run_dir/verdicts_*.jsonl \
        --field linear.x --threshold 0.5 [--source /cmd_vel] \
        [--proc run_dir/monitor_proc.csv] [--clock-offset 0.0] \
        [--out run_dir/metrics.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
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


def field_value(data: dict[str, Any], path: str) -> Any:
    if path in data:
        return data[path]
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def seq_of(record_id: str) -> int | None:
    try:
        return int(record_id.rsplit(":", 1)[-1])
    except (ValueError, AttributeError):
        return None


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[k]


def latency_stats(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "min_ms": min(values) * 1000,
        "mean_ms": statistics.fmean(values) * 1000,
        "median_ms": statistics.median(values) * 1000,
        "p95_ms": percentile(values, 95) * 1000,
        "max_ms": max(values) * 1000,
    }


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in args.records:
        records.extend(
            r for r in load_jsonl(path) if r.get("_type", "data") == "data"
        )
    verdict_rows = []
    for path in args.verdicts:
        verdict_rows.extend(load_jsonl(path))

    # --- throughput and loss, over all data records -----------------------
    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_source.setdefault(r.get("source_name", "?"), []).append(r)

    source_stats = {}
    for source, rows in sorted(by_source.items()):
        ts = [r["timestamp"] for r in rows]
        seqs = [s for s in (seq_of(r.get("record_id", "")) for r in rows) if s is not None]
        span = max(ts) - min(ts) if len(ts) > 1 else 0.0
        expected = (max(seqs) - min(seqs) + 1) if seqs else 0
        source_stats[source] = {
            "records": len(rows),
            "duration_s": round(span, 3),
            "rate_hz": round(len(rows) / span, 3) if span > 0 else None,
            "seq_gaps": expected - len(seqs) if seqs else None,
        }

    # --- offline oracle on the property source ----------------------------
    oracle_rows = [
        r
        for r in records
        if (args.source is None or r.get("source_name") == args.source)
        and field_value(r.get("data", {}), args.field) is not None
    ]
    oracle_rows.sort(key=lambda r: (seq_of(r.get("record_id", "")) or 0))

    expected_events = []  # (record_id, timestamp, violating)
    state = False
    for r in oracle_rows:
        violating = float(field_value(r["data"], args.field)) > args.threshold
        if violating != state:
            state = violating
            expected_events.append(
                {
                    "record_id": r["record_id"],
                    "timestamp": r["timestamp"],
                    "violating": violating,
                }
            )

    # --- verdict correctness (1:1 in-order match) --------------------------
    actual_events = []
    for row in verdict_rows:
        ids = row.get("input_record_ids") or []
        actual_events.append(
            {
                "record_id": ids[0] if ids else None,
                "violating": not row.get("result", True),
                "emitted_at": row.get("emitted_at"),
            }
        )

    matched = 0
    for exp, act in zip(expected_events, actual_events):
        if exp["violating"] == act["violating"] and exp["record_id"] == act["record_id"]:
            matched += 1
    missed = len(expected_events) - matched
    spurious = len(actual_events) - matched
    precision = matched / len(actual_events) if actual_events else None
    recall = matched / len(expected_events) if expected_events else None

    # --- detection latency --------------------------------------------------
    ts_by_id = {r["record_id"]: r["timestamp"] for r in records}
    latencies = [
        act["emitted_at"] - ts_by_id[act["record_id"]] - args.clock_offset
        for act in actual_events
        if act["emitted_at"] is not None and act["record_id"] in ts_by_id
    ]

    metrics: dict[str, Any] = {
        "records_total": len(records),
        "sources": source_stats,
        "property": {
            "field": args.field,
            "threshold": args.threshold,
            "source": args.source,
        },
        "oracle_transitions": len(expected_events),
        "verdicts": len(actual_events),
        "correctness": {
            "matched": matched,
            "missed": missed,
            "spurious": spurious,
            "precision": precision,
            "recall": recall,
        },
        "detection_latency": latency_stats(latencies) if latencies else None,
    }

    # --- optional resource samples -----------------------------------------
    if args.proc:
        cpu, rss = [], []
        with open(args.proc, encoding="utf-8") as f:
            next(f, None)
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 4:
                    cpu.append(float(parts[2]))
                    rss.append(float(parts[3]))
        if cpu:
            metrics["monitor_process"] = {
                "cpu_percent_mean": round(statistics.fmean(cpu), 2),
                "cpu_percent_max": round(max(cpu), 2),
                "rss_mb_max": round(max(rss), 2),
                "samples": len(cpu),
            }

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--verdicts", nargs="+", required=True)
    parser.add_argument("--field", default="linear.x")
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--source", default=None)
    parser.add_argument("--proc", default=None)
    parser.add_argument(
        "--clock-offset",
        type=float,
        default=0.0,
        help="Seconds to subtract from emitted_at when the verdict host clock "
        "differs from the record host clock (distributed runs).",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    metrics = analyze(args)
    text = json.dumps(metrics, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
