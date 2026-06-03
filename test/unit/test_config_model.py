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
            "type": "custom.rule_based_converter:RuleBasedConverter",
            "inputs": ["/odom"],
            "source_match": "^/odom$",
            "field_map": {"v": "x"},
            "verdict": {
                "type": "custom.threshold_verdict:ThresholdVerdict",
                "property_id": "p",
                "field": "v",
                "op": ">",
                "threshold": 1,
                "exporters": [{"type": "stdout"}],
            },
        }],
    })

    assert cfg.output_dir == "/tmp/out"
    assert cfg.session_id_prefix == "robot1"
    assert cfg.topics[0].name == "/odom"
    assert cfg.topics[0].transformers[0].kwargs == {"max_rate_hz": 5.0}
    assert cfg.exporters[0].kwargs == {"broker": "localhost"}
    assert cfg.converters[0].inputs == ["/odom"]
    assert cfg.converters[0].verdict is not None
    assert cfg.converters[0].verdict.exporters[0].type == "stdout"


def test_runner_config_parses_source_spec():
    cfg = RunnerConfig.from_dict({
        "monitor": {"output_dir": "/tmp/out"},
        "verdict_runner": {
            "source": {
                "type": "mqtt",
                "broker": "localhost",
                "topic_filter": "monitor/#",
            },
        },
    })

    assert cfg.output_dir == "/tmp/out"
    assert cfg.source is not None
    assert cfg.source.type == "mqtt"
    assert cfg.source.kwargs == {
        "broker": "localhost",
        "topic_filter": "monitor/#",
    }
