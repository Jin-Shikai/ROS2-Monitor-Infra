#!/usr/bin/env python3
"""Aggregate E5 clocks, hop latency, transparency, traffic, loss and resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from collections import defaultdict
from typing import Any


PROPERTIES = ("speed_r1", "speed_r2", "separation")


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentage / 100)
    return ordered[max(0, min(index, len(ordered) - 1))]


def stats_ms(seconds: list[float]) -> dict[str, float] | None:
    if not seconds:
        return None
    return {
        "count": len(seconds),
        "min_ms": round(min(seconds) * 1000, 3),
        "mean_ms": round(statistics.fmean(seconds) * 1000, 3),
        "median_ms": round(statistics.median(seconds) * 1000, 3),
        "p95_ms": round(percentile(seconds, 95) * 1000, 3),
        "max_ms": round(max(seconds) * 1000, 3),
    }


def clock_offset(path: str) -> tuple[float, float]:
    estimate = load_json(path)["estimate"]
    return float(estimate["offset_seconds"]), float(estimate["uncertainty_ms"])


def seq_of(record_id: str) -> int | None:
    try:
        return int(record_id.rsplit(":", 1)[-1])
    except (AttributeError, ValueError):
        return None


def record_summary(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_rows = []
    fleet_payload_bytes = 0
    probe_payload_bytes = 0
    bookend_payload_bytes = 0
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            all_rows.append(row)
            size = len(line.encode("utf-8"))
            if row.get("_type", "data") != "data":
                bookend_payload_bytes += size
            elif row.get("source_name") == "/e5/dds_probe":
                probe_payload_bytes += size
            else:
                fleet_payload_bytes += size
    rows = [row for row in all_rows if row.get("_type", "data") == "data"]
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[row.get("source_name", "?")].append(row)

    sources = {}
    for source, source_rows in sorted(by_source.items()):
        seqs = [
            seq for seq in (seq_of(row.get("record_id", "")) for row in source_rows)
            if seq is not None
        ]
        timestamps = [float(row["timestamp"]) for row in source_rows]
        expected = max(seqs) - min(seqs) + 1 if seqs else None
        sources[source] = {
            "records": len(source_rows),
            "seq_gaps": expected - len(seqs) if expected is not None else None,
            "duration_s": round(max(timestamps) - min(timestamps), 3)
            if len(timestamps) > 1 else 0.0,
        }
    timestamps = [float(row["timestamp"]) for row in rows]
    duration = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0
    payload_bytes = os.path.getsize(path)
    summary = {
        "records_total": len(rows),
        "duration_s": round(duration, 3),
        "sources": sources,
        "mqtt_application_payload_bytes": payload_bytes,
        "mqtt_application_payload_mbit": round(payload_bytes * 8 / 1e6, 3),
        "mqtt_application_payload_kbit_s": round(payload_bytes * 8 / duration / 1000, 3)
        if duration else None,
        "fleet_payload_excluding_probe_bytes": fleet_payload_bytes,
        "fleet_payload_excluding_probe_mbit": round(fleet_payload_bytes * 8 / 1e6, 3),
        "fleet_payload_excluding_probe_kbit_s": round(
            fleet_payload_bytes * 8 / duration / 1000, 3
        ) if duration else None,
        "dds_probe_payload_bytes": probe_payload_bytes,
        "session_bookend_payload_bytes": bookend_payload_bytes,
        "payload_scope": "serialized DataRecord JSONL bytes; MQTT/TCP headers excluded",
    }
    return rows, summary


def ros_stamp(row: dict[str, Any]) -> float | None:
    stamp = row.get("ros_timestamp")
    if not isinstance(stamp, dict):
        return None
    return float(stamp.get("sec", 0)) + float(stamp.get("nanosec", 0)) / 1e9


def compare_streams(reference: str, remote: str) -> dict[str, Any]:
    ref_rows = load_jsonl(reference)
    remote_rows = load_jsonl(remote)
    keys = ("property_id", "result", "input_record_ids")
    mismatches = 0
    for ref, actual in zip(ref_rows, remote_rows):
        if any(ref.get(key) != actual.get(key) for key in keys):
            mismatches += 1
    return {
        "reference_count": len(ref_rows),
        "remote_count": len(remote_rows),
        "matched": min(len(ref_rows), len(remote_rows)) - mismatches,
        "mismatches": mismatches,
        "identical": len(ref_rows) == len(remote_rows) and mismatches == 0,
    }


def verdict_latencies(path: str, offset: float) -> list[float]:
    values = []
    for verdict in load_jsonl(path):
        if verdict.get("emitted_at") is not None and verdict.get("timestamp") is not None:
            values.append(
                float(verdict["emitted_at"]) - float(verdict["timestamp"]) - offset
            )
    return values


def process_summary(path: str) -> dict[str, Any] | None:
    by_time: dict[str, list[tuple[float, float]]] = defaultdict(list)
    by_pid: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with open(path, encoding="utf-8") as stream:
        next(stream, None)
        for line in stream:
            parts = line.strip().split(",")
            if len(parts) != 4:
                continue
            timestamp, pid, cpu, rss = parts
            sample = (float(cpu), float(rss))
            by_time[timestamp].append(sample)
            by_pid[pid].append(sample)
    if not by_time:
        return None
    aggregate_cpu = [sum(sample[0] for sample in values) for values in by_time.values()]
    aggregate_rss = [sum(sample[1] for sample in values) for values in by_time.values()]
    return {
        "cpu_percent_mean": round(statistics.fmean(aggregate_cpu), 2),
        "cpu_percent_max": round(max(aggregate_cpu), 2),
        "rss_mb_max": round(max(aggregate_rss), 2),
        "samples": len(by_time),
        "processes": {
            pid: {
                "cpu_percent_mean": round(statistics.fmean(v[0] for v in values), 2),
                "cpu_percent_max": round(max(v[0] for v in values), 2),
                "rss_mb_max": round(max(v[1] for v in values), 2),
            }
            for pid, values in by_pid.items()
        },
    }


def mqtt_source_count(path: str) -> dict[str, int] | None:
    pattern = re.compile(
        r"MQTTSource stopped: received=(\d+) data=(\d+) bookends=(\d+)"
    )
    with open(path, encoding="utf-8") as stream:
        matches = [pattern.search(line) for line in stream]
    found = [match for match in matches if match is not None]
    if not found:
        return None
    match = found[-1]
    return {
        "received": int(match.group(1)),
        "data": int(match.group(2)),
        "bookends": int(match.group(3)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    for location in ("remote", "reference"):
        for prop in PROPERTIES:
            parser.add_argument(f"--{location}-{prop.replace('_', '-')}", required=True)
    parser.add_argument("--clock-pi-start", required=True)
    parser.add_argument("--clock-pi-end", required=True)
    parser.add_argument("--clock-mac-start", required=True)
    parser.add_argument("--clock-mac-end", required=True)
    parser.add_argument("--proc-pc", required=True)
    parser.add_argument("--proc-pi", required=True)
    parser.add_argument("--proc-mac", required=True)
    parser.add_argument("--runner-pi-log", required=True)
    parser.add_argument("--runner-mac-log", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    pi_start, pi_start_u = clock_offset(args.clock_pi_start)
    pi_end, pi_end_u = clock_offset(args.clock_pi_end)
    mac_start, mac_start_u = clock_offset(args.clock_mac_start)
    mac_end, mac_end_u = clock_offset(args.clock_mac_end)
    pi_pc = statistics.fmean((pi_start, pi_end))
    mac_pc = statistics.fmean((mac_start, mac_end))
    mac_pi = mac_pc - pi_pc

    rows, records = record_summary(args.records)
    pi_received = mqtt_source_count(args.runner_pi_log)
    mac_received = mqtt_source_count(args.runner_mac_log)
    probe_delays = []
    for row in rows:
        if row.get("source_name") != "/e5/dds_probe":
            continue
        stamp = ros_stamp(row)
        if stamp is not None:
            probe_delays.append(float(row["timestamp"]) - stamp - pi_pc)

    remote_paths = {prop: getattr(args, f"remote_{prop}") for prop in PROPERTIES}
    reference_paths = {
        prop: getattr(args, f"reference_{prop}") for prop in PROPERTIES
    }
    transparency = {
        prop: compare_streams(reference_paths[prop], remote_paths[prop])
        for prop in PROPERTIES
    }
    reference_latency = {
        prop: stats_ms(verdict_latencies(reference_paths[prop], 0.0))
        for prop in PROPERTIES
    }
    remote_latency = {
        prop: stats_ms(verdict_latencies(remote_paths[prop], mac_pi))
        for prop in PROPERTIES
    }
    extra = {}
    for prop in PROPERTIES:
        ref = reference_latency[prop]
        remote = remote_latency[prop]
        extra[prop] = (
            round(remote["mean_ms"] - ref["mean_ms"], 3)
            if ref is not None and remote is not None else None
        )

    report = {
        "clock_sync": {
            "offset_definition": "named_host_clock_minus_pc_clock",
            "pi_minus_pc_ms": {
                "start": round(pi_start * 1000, 3),
                "end": round(pi_end * 1000, 3),
                "mean_used": round(pi_pc * 1000, 3),
            },
            "mac_minus_pc_ms": {
                "start": round(mac_start * 1000, 3),
                "end": round(mac_end * 1000, 3),
                "mean_used": round(mac_pc * 1000, 3),
            },
            "mac_minus_pi_ms": round(mac_pi * 1000, 3),
            "maximum_endpoint_uncertainty_ms": round(
                max(pi_start_u, pi_end_u, mac_start_u, mac_end_u), 3
            ),
            "pi_endpoint_uncertainty_max_ms": round(max(pi_start_u, pi_end_u), 3),
            "mac_endpoint_uncertainty_max_ms": round(max(mac_start_u, mac_end_u), 3),
            "mac_minus_pi_uncertainty_bound_ms": round(
                max(pi_start_u, pi_end_u) + max(mac_start_u, mac_end_u), 3
            ),
            "drift_during_run_ms": {
                "pi_vs_pc": round((pi_end - pi_start) * 1000, 3),
                "mac_vs_pc": round((mac_end - mac_start) * 1000, 3),
            },
        },
        "records_and_transport": records,
        "mqtt_delivery": {
            "published_data_records": len(rows),
            "pi_reference_source": pi_received,
            "mac_source": mac_received,
            "pi_data_loss": len(rows) - pi_received["data"]
            if pi_received is not None else None,
            "mac_data_loss": len(rows) - mac_received["data"]
            if mac_received is not None else None,
        },
        "latency": {
            "dds_pc_publish_to_pi_collect": stats_ms(probe_delays),
            "mqtt_pi_collect_to_pi_reference_verdict": reference_latency,
            "mqtt_pi_collect_to_mac_verdict_clock_corrected": remote_latency,
            "mac_path_minus_pi_reference_mean_ms": extra,
            "interpretation": (
                "DDS uses the wall-clock probe. MQTT starts at Pi collection; "
                "remote values subtract the measured Mac-minus-Pi offset."
            ),
        },
        "distribution_transparency": transparency,
        "resources": {
            "pc_nav2_gazebo_process_tree": process_summary(args.proc_pc),
            "pi_monitor_and_reference_runner": process_summary(args.proc_pi),
            "mac_verdict_runner": process_summary(args.proc_mac),
            "cpu_scope": "single-core percentages; PC ps sample includes launch descendants",
        },
        "ok": all(item["identical"] for item in transparency.values())
        and bool(probe_delays)
        and pi_received is not None
        and mac_received is not None
        and pi_received["data"] == len(rows)
        and mac_received["data"] == len(rows),
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
