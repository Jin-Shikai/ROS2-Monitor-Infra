"""Integration tests for monitor/node_runner.py — the unified runner."""

from __future__ import annotations

import json
import logging
import threading
import time

from config_model import RunnerConfig
from data_record import DataRecord
from node_runner import run

logger = logging.getLogger("test_node_runner")


def _write_records(path, values):
    with open(path, "w", encoding="utf-8") as f:
        for seq, value in enumerate(values, start=1):
            record = DataRecord.from_topic_msg(
                session_id="S", topic_name="/odom",
                msg_type="nav_msgs/msg/Odometry",
                data={"twist.twist.linear.x": value}, seq=seq,
            )
            f.write(record.to_json() + "\n")


def _run_until(cfg, done, timeout=5.0):
    stop = threading.Event()
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(run(cfg, stop, logger)))
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not done():
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5.0)
    assert result == [0]


def test_full_chain_from_records_input(tmp_path):
    records = tmp_path / "records.jsonl"
    _write_records(records, [0.1, 0.4])
    verdict_file = tmp_path / "verdicts.jsonl"

    cfg = RunnerConfig.from_dict({
        "monitor": {"output_dir": str(tmp_path)},
        "inputs": [{"id": "replay", "type": "file", "path": str(records)}],
        "converters": [{
            "id": "c1",
            "type": "custom.rule_based:RuleBasedConverter",
            "params": {
                "source_match": "^/odom$",
                "field_map": {"speed": "twist.twist.linear.x"},
                "property_id": "p",
            },
        }],
        "verdict_services": [{
            "id": "v1",
            "type": "custom.threshold:ThresholdVerdict",
            "params": {"property_id": "p", "field": "speed", "op": ">",
                       "threshold": 0.2, "sustain_sec": 0.0},
            "exporters": [{"type": "file", "path": str(verdict_file)}],
        }],
        "links": [
            {"from": "source:/odom", "to": "converter:c1"},
            {"from": "converter:c1", "to": "verdict:v1"},
        ],
    })

    _run_until(cfg, lambda: verdict_file.exists() and verdict_file.read_text().strip())
    rows = [json.loads(l) for l in verdict_file.read_text().splitlines()]
    assert rows[0]["property_id"] == "p"
    assert rows[0]["result"] is False


def test_verdict_only_host_from_dsl_input(tmp_path):
    dsl_file = tmp_path / "dsl.jsonl"
    dsl_file.write_text(json.dumps({"speed": 0.9, "_property_id": "p"}) + "\n")
    verdict_file = tmp_path / "verdicts.jsonl"

    cfg = RunnerConfig.from_dict({
        "monitor": {"output_dir": str(tmp_path)},
        "inputs": [{
            "id": "dsl_in", "payload": "dsl", "type": "file", "path": str(dsl_file),
        }],
        "verdict_services": [{
            "id": "v1",
            "type": "custom.threshold:ThresholdVerdict",
            "params": {"property_id": "p", "field": "speed", "op": ">",
                       "threshold": 0.2, "sustain_sec": 0.0},
            "exporters": [{"type": "file", "path": str(verdict_file)}],
        }],
        "links": [{"from": "input:dsl_in", "to": "verdict:v1"}],
    })

    _run_until(cfg, lambda: verdict_file.exists() and verdict_file.read_text().strip())
    rows = [json.loads(l) for l in verdict_file.read_text().splitlines()]
    assert rows[0]["result"] is False


def test_runner_without_inputs_exits(tmp_path):
    cfg = RunnerConfig.from_dict({
        "monitor": {"output_dir": str(tmp_path)},
        "verdict_services": [{
            "id": "v1",
            "type": "custom.threshold:ThresholdVerdict",
            "params": {"property_id": "p", "field": "speed", "op": ">", "threshold": 0.2},
        }],
        "links": [{"from": "input:missing", "to": "verdict:v1"}],
    })
    assert run(cfg, threading.Event(), logger) == 1
