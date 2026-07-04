"""Unit tests for monitor/config_gen.py — the generation-request projection.

The demo requests in ``demo/config_gen/`` are projected to runtime YAML and
checked structurally, plus behaviourally by feeding the generated dicts
through the *same* parsers and builders the real entrypoints use
(`MonitorConfig` / `RunnerConfig` + `pipeline.build_graph` / `node_runner.run`),
so the tests need no ROS2.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import pytest

from config_gen import GenerationRequest, project
from config_model import MonitorConfig, RunnerConfig
from data_record import DataRecord
from node_runner import run
from pipeline import build_graph

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo" / "config_gen"


@pytest.fixture
def logger():
    return logging.getLogger("test_config_gen")


def _load(name: str):
    return project(GenerationRequest.load(str(DEMO_DIR / name)))


# --- all-in-one ------------------------------------------------------------- #

def test_all_in_one_projects_single_monitor_node_file():
    generated = _load("all_in_one.json")
    assert set(generated) == {"robot"}
    gen = generated["robot"]
    assert gen.entrypoint == "monitor_node"

    cfg = MonitorConfig.from_dict(gen.config)
    assert cfg.topics[0].name == "/odom"
    assert cfg.topics[0].exporters[0].type == "file"
    assert cfg.converters[0].id == "speed_filter"
    assert cfg.verdict_services[0].id == "speed_verdict"
    assert {(l.from_ref, l.to_ref) for l in cfg.links} == {
        ("source:/odom", "converter:speed_filter"),
        ("converter:speed_filter", "verdict:speed_verdict"),
    }


def test_all_in_one_graph_behaves(logger, tmp_path):
    gen = _load("all_in_one.json")["robot"]
    cfg = MonitorConfig.from_dict(gen.config)
    rt = build_graph(
        cfg.converters, cfg.verdict_services, cfg.links, cfg.outputs,
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    rt.record_entry.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom", msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4, "twist.twist.linear.y": 0.0}, seq=1,
    ))
    rt.close()
    verdicts = (tmp_path / "verdicts_S.jsonl").read_text().strip().splitlines()
    assert len(verdicts) == 1
    assert '"result": false' in verdicts[0]


# --- three hosts: monitor -> converter -> verdict ---------------------------- #

def test_three_host_projects_node_runner_configs():
    generated = _load("three_host.json")
    assert set(generated) == {"robot", "converter_host", "verdict_host"}
    assert generated["robot"].entrypoint == "monitor_node"
    assert generated["converter_host"].entrypoint == "node_runner"
    assert generated["verdict_host"].entrypoint == "node_runner"

    conv_cfg = RunnerConfig.from_dict(generated["converter_host"].config)
    assert conv_cfg.inputs[0].payload == "records"
    assert conv_cfg.inputs[0].type == "mqtt"
    assert conv_cfg.outputs[0].payload == "dsl"
    assert conv_cfg.outputs[0].kwargs["topic"] == "dsl/odom_speed"

    verdict_cfg = RunnerConfig.from_dict(generated["verdict_host"].config)
    assert verdict_cfg.inputs[0].payload == "dsl"
    assert verdict_cfg.inputs[0].kwargs["topic"] == "dsl/odom_speed"
    assert verdict_cfg.links[0].from_ref == f"input:{verdict_cfg.inputs[0].id}"
    assert verdict_cfg.links[0].to_ref == "verdict:speed_verdict"


# --- converter chain across hosts -------------------------------------------- #

def test_converter_chain_republishes_records_between_hosts():
    generated = _load("converter_chain.json")
    filter_cfg = RunnerConfig.from_dict(generated["filter_host"].config)
    assert filter_cfg.outputs[0].payload == "records"
    assert filter_cfg.outputs[0].kwargs["topic_prefix"] == "filtered/"

    verdict_cfg = RunnerConfig.from_dict(generated["verdict_host"].config)
    assert verdict_cfg.inputs[0].kwargs["topic_filter"] == "filtered/#"
    # dsl converter and verdict co-located: in-process link, no dsl transport
    assert not verdict_cfg.outputs
    assert ("converter:speed_dsl", "verdict:speed_verdict") in {
        (l.from_ref, l.to_ref) for l in verdict_cfg.links
    }


# --- file transport ----------------------------------------------------------- #

def test_file_transport_link_agrees_on_both_ends():
    generated = _load("file_transport.json")
    monitor_exporter = generated["robot"].config["topics"][0]["exporters"][0]
    verifier_input = generated["verifier"].config["inputs"][0]
    assert monitor_exporter["type"] == "file"
    written = Path(monitor_exporter["output_dir"]) / f"{monitor_exporter['session_id']}.jsonl"
    assert written == Path(verifier_input["path"])
    assert verifier_input["follow"] is True


def test_file_transport_verifier_runs_end_to_end(tmp_path, logger):
    generated = _load("file_transport.json")
    config = json.loads(json.dumps(generated["verifier"].config))
    config["monitor"]["output_dir"] = str(tmp_path)

    records = tmp_path / "records.jsonl"
    record = DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom", msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4, "twist.twist.linear.y": 0.0}, seq=1,
    )
    records.write_text(record.to_json() + "\n")
    config["inputs"][0]["path"] = str(records)
    config["inputs"][0]["follow"] = False

    cfg = RunnerConfig.from_dict(config)
    stop = threading.Event()
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(run(cfg, stop, logger)))
    thread.start()
    verdict_file = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        matches = [p for p in tmp_path.glob("verdicts_*.jsonl") if p.read_text().strip()]
        if matches:
            verdict_file = matches[0]
            break
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5.0)
    assert result == [0]
    assert verdict_file is not None
    assert '"result": false' in verdict_file.read_text()


# --- two-robot fleet ----------------------------------------------------------- #

def test_two_robot_fleet_merges_same_transport_inputs():
    generated = _load("two_robot_fleet.json")
    assert set(generated) == {"robot1", "robot2", "converter_host", "verdict_host"}

    conv_cfg = RunnerConfig.from_dict(generated["converter_host"].config)
    # both robots publish to the same broker/prefix: one merged input
    assert len(conv_cfg.inputs) == 1
    assert conv_cfg.inputs[0].kwargs["topic_filter"] == "monitor/#"
    assert {(l.from_ref, l.to_ref) for l in conv_cfg.links} == {
        ("source:/robot1/odom", "converter:relative_speed"),
        ("source:/robot2/odom", "converter:relative_speed"),
        ("converter:relative_speed", "output:dsl_relative_speed"),
    }
    assert generated["verdict_host"].config["verdict_services"][0]["params"]["threshold"] == 0.5


def test_two_robot_fleet_distinct_transports_stay_separate():
    data = json.loads((DEMO_DIR / "two_robot_fleet.json").read_text())
    data["links"][1]["transport"]["topic_prefix"] = "monitor2/"
    generated = project(GenerationRequest.from_dict(data))
    conv_cfg = RunnerConfig.from_dict(generated["converter_host"].config)
    assert len(conv_cfg.inputs) == 2
    assert {i.kwargs["topic_filter"] for i in conv_cfg.inputs} == {"monitor/#", "monitor2/#"}


# --- mixed-role host ------------------------------------------------------------ #

def test_mixed_role_host_gets_single_runner_config():
    """One host runs a dsl-splitting converter AND a record filter AND a local
    verdict — previously three incompatible per-process roles."""
    data = {
        "hosts": [
            {"id": "hub", "runtimes": [
                {
                    "id": "local_chain", "kind": "converter",
                    "class_path": "custom.speed_aggregate_filter:SpeedAggregateFilter",
                    "input_from": [], "output_to": "local_dsl",
                },
                {
                    "id": "local_check", "kind": "verdict_service",
                    "class_path": "custom.threshold_verdict:ThresholdVerdict",
                    "input_from": ["local_dsl"],
                    "property_id": "p", "field": "speed", "op": ">", "threshold": 0.2,
                },
                {
                    "id": "remote_conv", "kind": "converter",
                    "class_path": "custom.speed_aggregate_filter:SpeedAggregateFilter",
                    "input_from": [], "output_to": "remote_dsl",
                },
                {
                    "id": "relay", "kind": "converter", "converter": "data_filter",
                    "class_path": "custom.odom_speed_filter:OdomSpeedFilter",
                    "input_from": [], "output_to": "relayed_records",
                },
            ]},
            {"id": "far", "runtimes": [
                {
                    "id": "far_check", "kind": "verdict_service",
                    "class_path": "custom.threshold_verdict:ThresholdVerdict",
                    "input_from": ["remote_dsl"],
                    "property_id": "p2", "field": "speed", "op": ">", "threshold": 0.2,
                },
                {
                    "id": "far_conv", "kind": "converter",
                    "class_path": "custom.rule_based_converter:RuleBasedConverter",
                    "input_from": ["relayed_records"], "output_to": "far_dsl",
                },
            ]},
        ],
        "links": [
            {
                "id": "dsl_out", "from_host": "hub", "to_host": "far",
                "from_runtime": "remote_conv", "to_runtime": "far_check",
                "payload": "dsl", "transport": {"kind": "mqtt"},
            },
            {
                "id": "records_out", "from_host": "hub", "to_host": "far",
                "from_runtime": "relay", "to_runtime": "far_conv",
                "payload": "records", "transport": {"kind": "mqtt", "topic_prefix": "relay/"},
            },
        ],
    }
    generated = project(GenerationRequest.from_dict(data))
    hub = RunnerConfig.from_dict(generated["hub"].config)
    assert generated["hub"].entrypoint == "node_runner"
    assert {o.id: o.payload for o in hub.outputs} == {
        "dsl_out": "dsl", "records_out": "records",
    }
    link_set = {(l.from_ref, l.to_ref) for l in hub.links}
    assert ("converter:local_chain", "verdict:local_check") in link_set
    assert ("converter:remote_conv", "output:dsl_out") in link_set
    assert ("converter:relay", "output:records_out") in link_set

    far = RunnerConfig.from_dict(generated["far"].config)
    assert {i.payload for i in far.inputs} == {"dsl", "records"}


# --- dsl link over file ----------------------------------------------------------- #

def test_dsl_link_supports_file_transport():
    data = json.loads((DEMO_DIR / "three_host.json").read_text())
    dsl_link = next(l for l in data["links"] if l["payload"] == "dsl")
    dsl_link["transport"] = {"kind": "file"}
    generated = project(GenerationRequest.from_dict(data))

    out = generated["converter_host"].config["outputs"][0]
    inp = generated["verdict_host"].config["inputs"][0]
    assert out["type"] == "file"
    assert inp["type"] == "file"
    assert out["path"] == inp["path"]
    assert inp["follow"] is True


def test_unsupported_transport_kind_raises():
    data = json.loads((DEMO_DIR / "three_host.json").read_text())
    data["links"][0]["transport"] = {"kind": "carrier-pigeon"}
    with pytest.raises(ValueError, match="carrier-pigeon"):
        project(GenerationRequest.from_dict(data))


# --- monitor-host constraints -------------------------------------------------------- #

def test_monitor_host_rejects_inbound_cross_host_dsl():
    data = {
        "hosts": [
            {"id": "a", "runtimes": [
                {"id": "conv_a", "kind": "converter",
                 "class_path": "x:Y", "input_from": [], "output_to": "r"},
            ]},
            {"id": "b", "runtimes": [
                {"id": "mon_b", "kind": "monitor", "subscribe": []},
                {"id": "check_b", "kind": "verdict_service",
                 "class_path": "x:Z", "input_from": ["r"]},
            ]},
        ],
        "links": [{
            "id": "l", "from_host": "a", "to_host": "b",
            "from_runtime": "conv_a", "to_runtime": "check_b",
            "payload": "dsl", "transport": {"kind": "mqtt"},
        }],
    }
    with pytest.raises(ValueError, match="host without a monitor"):
        project(GenerationRequest.from_dict(data))


def test_monitor_host_with_remote_verdict_uses_output_endpoint():
    data = {
        "hosts": [
            {"id": "robot", "runtimes": [
                {"id": "ros2_r", "kind": "ros2", "sources": [
                    {"id": "odom", "source_kind": "topic", "name": "/odom",
                     "interface": "nav_msgs/msg/Odometry"},
                ]},
                {"id": "mon", "kind": "monitor", "subscribe": ["odom"]},
                {"id": "conv", "kind": "converter",
                 "class_path": "custom.speed_aggregate_filter:SpeedAggregateFilter",
                 "input_from": ["odom"], "output_to": "speed"},
            ]},
            {"id": "far", "runtimes": [
                {"id": "check", "kind": "verdict_service",
                 "class_path": "custom.threshold_verdict:ThresholdVerdict",
                 "input_from": ["speed"],
                 "property_id": "p", "field": "speed", "op": ">", "threshold": 0.2},
            ]},
        ],
        "links": [{
            "id": "dsl_speed", "from_host": "robot", "to_host": "far",
            "from_runtime": "conv", "to_runtime": "check",
            "payload": "dsl", "transport": {"kind": "mqtt"},
        }],
    }
    generated = project(GenerationRequest.from_dict(data))
    robot = generated["robot"]
    assert robot.entrypoint == "monitor_node"
    assert robot.config["outputs"][0]["payload"] == "dsl"
    assert ("converter:conv", "output:dsl_speed") in {
        (l["from"], l["to"]) for l in robot.config["links"]
    }
