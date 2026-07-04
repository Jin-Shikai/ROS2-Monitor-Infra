"""Unit tests for typed YAML config models."""

from __future__ import annotations

from config_model import MonitorConfig, RunnerConfig


def test_monitor_config_parses_typed_specs():
    cfg = MonitorConfig.from_dict({
        "monitor": {"output_dir": "/tmp/out", "session_id_prefix": "robot1"},
        "topics": [{
            "name": "/odom",
            "type": "nav_msgs/msg/Odometry",
            "transformers": [{"type": "RateThrottler", "max_rate_hz": 5.0}],
            "exporters": [{"type": "file"}],
        }],
        "exporters": [{"type": "mqtt", "broker": "localhost"}],
        "converters": [{
            "id": "c1",
            "type": "custom.rule_based_converter:RuleBasedConverter",
            "params": {"source_match": "^/odom$", "field_map": {"v": "x"}},
        }],
        "verdict_services": [{
            "id": "v1",
            "type": "custom.threshold_verdict:ThresholdVerdict",
            "params": {"property_id": "p", "field": "v", "op": ">", "threshold": 1},
            "exporters": [{"type": "stdout"}],
        }],
        "outputs": [{
            "id": "dsl_out",
            "payload": "dsl",
            "type": "mqtt",
            "topic": "dsl/x",
        }],
        "links": [
            {"from": "source:/odom", "to": "converter:c1"},
            {"from": "converter:c1", "to": "verdict:v1"},
            {"from": "converter:c1", "to": "output:dsl_out"},
        ],
    })

    assert cfg.output_dir == "/tmp/out"
    assert cfg.session_id_prefix == "robot1"
    assert cfg.topics[0].name == "/odom"
    assert cfg.topics[0].transformers[0].kwargs == {"max_rate_hz": 5.0}
    assert cfg.exporters[0].kwargs == {"broker": "localhost"}
    assert cfg.converters[0].id == "c1"
    assert cfg.converters[0].kwargs["source_match"] == "^/odom$"
    assert cfg.verdict_services[0].exporters[0].type == "stdout"
    assert cfg.outputs[0].payload == "dsl"
    assert cfg.outputs[0].kwargs == {"topic": "dsl/x"}
    assert [l.to_ref for l in cfg.links] == ["converter:c1", "verdict:v1", "output:dsl_out"]


def test_runner_config_parses_inputs_and_outputs():
    cfg = RunnerConfig.from_dict({
        "monitor": {"output_dir": "/tmp/out"},
        "inputs": [
            {
                "id": "robot_feed",
                "type": "mqtt",
                "broker": "localhost",
                "topic_filter": "monitor/#",
            },
            {
                "id": "fleet_dsl",
                "payload": "dsl",
                "type": "file",
                "path": "x.jsonl",
                "follow": True,
            },
        ],
        "outputs": [
            {"id": "relay", "payload": "records", "type": "mqtt", "topic_prefix": "filtered/"},
        ],
    })

    assert cfg.output_dir == "/tmp/out"
    assert cfg.inputs[0].payload == "records"
    assert cfg.inputs[0].kwargs == {"broker": "localhost", "topic_filter": "monitor/#"}
    assert cfg.inputs[1].payload == "dsl"
    assert cfg.inputs[1].kwargs == {"path": "x.jsonl", "follow": True}
    assert cfg.outputs[0].kwargs == {"topic_prefix": "filtered/"}


def test_endpoint_default_ids_are_positional():
    cfg = RunnerConfig.from_dict({
        "inputs": [{"type": "mqtt"}, {"type": "file", "path": "a.jsonl"}],
    })
    assert [i.id for i in cfg.inputs] == ["endpoint_1", "endpoint_2"]
