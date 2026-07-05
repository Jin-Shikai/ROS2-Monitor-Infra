from pathlib import Path
import subprocess

import pytest
import yaml

from webui.server import (
    EventHub,
    _line_looks_like_verdict,
    build_generation_request,
    clear_verdicts,
    generate_configs,
    plugin_payload,
    recent_verdicts,
    start_robot,
)


def test_showcase_event_hub_broadcasts_to_subscribers():
    hub = EventHub()
    first = hub.subscribe()
    second = hub.subscribe()

    event = hub.publish("log", {"line": "hello"})

    assert event["id"] == 1
    assert first.get_nowait() == event
    assert second.get_nowait() == event

    hub.unsubscribe(first)
    next_event = hub.publish("run_state", {"running": False})

    assert first.empty()
    assert second.get_nowait() == next_event


def test_showcase_detects_verdict_log_lines():
    assert _line_looks_like_verdict('Verdict(timestamp=1.0, property_id="p")')
    assert _line_looks_like_verdict('{"property_id": "p", "result": false}')
    assert not _line_looks_like_verdict("Service: /reset_pose [std_srvs/srv/Trigger]")


def test_showcase_builds_single_host_generation_request():
    request = build_generation_request(
        {
            "sources": [
                {
                    "name": "/cmd_vel",
                    "interface": "geometry_msgs/msg/Twist",
                    "source_kind": "topic",
                },
                {
                    "name": "/odom",
                    "interface": "nav_msgs/msg/Odometry",
                    "source_kind": "topic",
                },
            ],
            "monitors": [
                {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel", "topic:/odom"]}
            ],
            "converter_class": "custom.rule_based_converter:RuleBasedConverter",
            "verdict_class": "custom.threshold_verdict:ThresholdVerdict",
            "converter_params": [
                {"key": "source_match", "value": "^/cmd_vel$", "type": "string"},
                {"key": "field_map", "value": '{"speed": "linear.x"}', "type": "json"},
            ],
            "verdict_params": [
                {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
                {"key": "field", "value": "speed", "type": "string"},
                {"key": "op", "value": ">", "type": "string"},
                {"key": "threshold", "value": "0.3", "type": "number"},
            ],
        }
    )

    assert len(request["hosts"]) == 1
    assert request["links"] == []
    runtimes = request["hosts"][0]["runtimes"]
    assert [runtime["kind"] for runtime in runtimes] == [
        "ros2",
        "monitor",
        "converter",
        "verdict_service",
    ]
    assert len(runtimes[0]["sources"]) == 2
    assert runtimes[1]["subscribe"] == ["cmd_vel", "odom"]
    assert runtimes[2]["class_path"] == "custom.rule_based_converter:RuleBasedConverter"
    assert runtimes[2]["input_from"] == ["cmd_vel", "odom"]
    assert runtimes[2]["field_map"] == {"speed": "linear.x"}
    assert runtimes[3]["property_id"] == "cmd_vel_limit"
    assert runtimes[3]["threshold"] == 0.3


def test_showcase_builds_service_and_action_sources():
    request = build_generation_request(
        {
            "sources": [
                {
                    "name": "/reset",
                    "interface": "std_srvs/srv/Empty",
                    "source_kind": "service",
                },
                {
                    "name": "/navigate_to_pose",
                    "interface": "nav2_msgs/action/NavigateToPose",
                    "source_kind": "action",
                },
            ],
            "monitors": [
                {
                    "id": "monitor_robot",
                    "source_keys": ["service:/reset", "action:/navigate_to_pose"],
                }
            ],
            "converters": [
                {
                    "id": "action_converter",
                    "class_path": "custom.rule_based_converter:RuleBasedConverter",
                    "input_source_keys": ["action:/navigate_to_pose"],
                }
            ],
        }
    )

    runtimes = request["hosts"][0]["runtimes"]
    assert runtimes[0]["sources"] == [
        {
            "id": "service__reset",
            "source_kind": "service",
            "name": "/reset",
            "interface": "std_srvs/srv/Empty",
        },
        {
            "id": "action__navigate_to_pose",
            "source_kind": "action",
            "name": "/navigate_to_pose",
            "interface": "nav2_msgs/action/NavigateToPose",
        },
    ]
    assert runtimes[1]["subscribe"] == ["service__reset", "action__navigate_to_pose"]
    assert runtimes[2]["input_from"] == ["action__navigate_to_pose"]


def test_showcase_builds_graph_payload_with_shared_verdict_service():
    request = build_generation_request(
        {
            "sources": [
                {
                    "name": "/cmd_vel",
                    "interface": "geometry_msgs/msg/Twist",
                    "source_kind": "topic",
                },
                {
                    "name": "/odom",
                    "interface": "nav_msgs/msg/Odometry",
                    "source_kind": "topic",
                },
            ],
            "monitors": [
                {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel", "topic:/odom"]}
            ],
            "converters": [
                {
                    "id": "cmd-velocity-converter",
                    "class_path": "custom.demo1_velocity_converter:Demo1VelocityConverter",
                    "input_source_keys": ["topic:/cmd_vel"],
                    "verdict_service_ids": ["shared-speeding-check"],
                    "params": [
                        {"key": "speed_path", "value": "linear.x", "type": "string"}
                    ],
                },
                {
                    "id": "odom-velocity-converter",
                    "class_path": "custom.speed_aggregate_filter:SpeedAggregateFilter",
                    "input_source_keys": ["topic:/odom"],
                    "verdict_service_ids": ["shared-speeding-check"],
                    "params": [
                        {
                            "key": "components",
                            "value": '["twist.twist.linear.x"]',
                            "type": "json",
                        }
                    ],
                },
            ],
            "verdict_services": [
                {
                    "id": "shared-speeding-check",
                    "class_path": "custom.demo1_speeding_check:Demo1SpeedingCheck",
                    "params": [
                        {"key": "check", "value": "speed", "type": "string"},
                        {"key": "op", "value": ">", "type": "string"},
                        {"key": "value", "value": "0.5", "type": "number"},
                    ],
                }
            ],
        }
    )

    runtimes = request["hosts"][0]["runtimes"]
    converters = [runtime for runtime in runtimes if runtime["kind"] == "converter"]
    verdicts = [runtime for runtime in runtimes if runtime["kind"] == "verdict_service"]
    assert [converter["input_from"] for converter in converters] == [["cmd_vel"], ["odom"]]
    assert verdicts[0]["input_from"] == [
        "cmd-velocity-converter_dsl_record",
        "odom-velocity-converter_dsl_record",
    ]
    assert verdicts[0]["value"] == 0.5


def test_showcase_placement_derives_cross_host_links():
    request = build_generation_request(
        {
            "broker": {"host": "10.0.0.5", "port": 1884},
            "hosts": ["robot1", "robot2", "converter_host", "verdict_host"],
            "sources": [
                {
                    "name": "/robot1/odom",
                    "interface": "nav_msgs/msg/Odometry",
                    "source_kind": "topic",
                    "host": "robot1",
                },
                {
                    "name": "/robot2/odom",
                    "interface": "nav_msgs/msg/Odometry",
                    "source_kind": "topic",
                    "host": "robot2",
                },
            ],
            "monitors": [
                {
                    "id": "monitor_robot1",
                    "host": "robot1",
                    "source_keys": ["topic:/robot1/odom"],
                },
                {
                    "id": "monitor_robot2",
                    "host": "robot2",
                    "source_keys": ["topic:/robot2/odom"],
                },
            ],
            "converters": [
                {
                    "id": "relative_speed",
                    "class_path": "custom.relative_speed:RelativeSpeedConverter",
                    "host": "converter_host",
                    "verdict_service_ids": ["relative_speed_check"],
                }
            ],
            "verdict_services": [
                {
                    "id": "relative_speed_check",
                    "class_path": "custom.threshold_verdict:ThresholdVerdict",
                    "host": "verdict_host",
                }
            ],
        }
    )

    assert [host["id"] for host in request["hosts"]] == [
        "robot1", "robot2", "converter_host", "verdict_host",
    ]
    payloads = [(link["payload"], link["from_host"], link["to_host"]) for link in request["links"]]
    assert payloads == [
        ("records", "robot1", "converter_host"),
        ("records", "robot2", "converter_host"),
        ("dsl", "converter_host", "verdict_host"),
    ]
    assert all(link["transport"]["broker"] == "10.0.0.5" for link in request["links"])
    assert all(link["transport"]["port"] == 1884 for link in request["links"])


def test_showcase_rejects_unknown_source_kind():
    with pytest.raises(ValueError, match="topic, service, action"):
        build_generation_request(
            {
                "sources": [
                    {
                        "name": "/reset",
                        "interface": "std_srvs/srv/Empty",
                        "source_kind": "timer",
                    }
                ],
            }
        )


def test_showcase_plugin_payload_expands_manifest_schema():
    payload = plugin_payload()
    cmd_vel = next(item for item in payload["plugins"] if item["id"] == "cmd_vel_threshold")

    assert cmd_vel["converter"] == "custom.demo1_velocity_converter:Demo1VelocityConverter"
    assert cmd_vel["verdict"] == "custom.demo1_speeding_check:Demo1SpeedingCheck"
    assert cmd_vel["converter_schema"]["id"] == "demo1-velocity-converter"
    assert cmd_vel["verdict_schema"]["id"] == "demo1-speeding-check"
    assert any(row["key"] == "speed_path" for row in cmd_vel["converter_params"])
    assert any(row["key"] == "check" for row in cmd_vel["verdict_params"])

    fleet = next(
        item for item in payload["plugins"] if item["id"] == "two_robot_relative_speed"
    )
    assert fleet["hosts"] == ["robot1", "robot2", "converter_host", "verdict_host"]
    assert fleet["placement"] == {"converter": "converter_host", "verdict": "verdict_host"}
    assert fleet["converter"] == "custom.relative_speed:RelativeSpeedConverter"


def test_showcase_generate_configs_writes_yaml(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server, "GENERATED_COMPOSE", tmp_path / "docker-compose.yml")
    result = generate_configs(
        {
            "sources": [{"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}],
            "monitors": [
                {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel"]}
            ],
            "converter_class": "custom.rule_based_converter:RuleBasedConverter",
            "verdict_class": "custom.threshold_verdict:ThresholdVerdict",
            "converter_params": [
                {"key": "source_match", "value": "^/cmd_vel$", "type": "string"},
                {"key": "field_map", "value": '{"speed": "linear.x"}', "type": "json"},
            ],
            "verdict_params": [
                {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
                {"key": "field", "value": "speed", "type": "string"},
                {"key": "op", "value": ">", "type": "string"},
                {"key": "threshold", "value": "0.3", "type": "number"},
            ],
        }
    )

    assert Path(result["request_path"]).exists()
    assert len(result["configs"]) == 1
    config_path = Path(result["configs"][0]["path"])
    assert config_path.exists()
    parsed = yaml.safe_load(config_path.read_text())
    assert parsed["topics"][0]["name"] == "/cmd_vel"
    assert parsed["monitor"]["output_dir"] == "/output/showcase/robot"
    assert parsed["converters"][0]["id"] == "showcase_converter"
    assert parsed["verdict_services"][0]["type"] == "custom.threshold_verdict:ThresholdVerdict"
    assert parsed["links"][-1]["to"] == "verdict:showcase_verdict"
    compose = yaml.safe_load(Path(result["compose_path"]).read_text())
    service = compose["services"]["generated_robot"]
    assert service["network_mode"] == "host"
    assert service["ipc"] == "host"
    assert "../../demo/common:/demo/common:ro" not in service["volumes"]
    assert "robot_simulator.py" not in service["command"][-1]
    assert "monitor_node.py --config /generated/robot.yaml" in service["command"][-1]


def test_showcase_generate_configs_writes_service_action_sections(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server, "GENERATED_COMPOSE", tmp_path / "docker-compose.yml")
    result = generate_configs(
        {
            "sources": [
                {
                    "name": "/reset",
                    "interface": "std_srvs/srv/Empty",
                    "source_kind": "service",
                },
                {
                    "name": "/navigate_to_pose",
                    "interface": "nav2_msgs/action/NavigateToPose",
                    "source_kind": "action",
                },
            ],
            "monitors": [
                {
                    "id": "monitor_robot",
                    "source_keys": ["service:/reset", "action:/navigate_to_pose"],
                }
            ],
            "converters": [
                {
                    "id": "showcase_converter",
                    "class_path": "custom.rule_based_converter:RuleBasedConverter",
                    "input_source_keys": ["service:/reset"],
                    "params": [
                        {"key": "source_match", "value": "^/reset$", "type": "string"},
                        {"key": "field_map", "value": '{"ok": "success"}', "type": "json"},
                    ],
                }
            ],
            "verdict_params": [
                {"key": "property_id", "value": "reset_ok", "type": "string"},
                {"key": "field", "value": "ok", "type": "string"},
                {"key": "op", "value": "==", "type": "string"},
                {"key": "threshold", "value": "true", "type": "auto"},
            ],
        }
    )

    parsed = yaml.safe_load(Path(result["configs"][0]["path"]).read_text())
    assert "topics" not in parsed
    assert parsed["services"][0]["name"] == "/reset"
    assert parsed["services"][0]["type"] == "std_srvs/srv/Empty"
    assert parsed["actions"][0]["name"] == "/navigate_to_pose"
    assert parsed["actions"][0]["type"] == "nav2_msgs/action/NavigateToPose"
    assert {"from": "source:/reset", "to": "converter:showcase_converter"} in [
        {"from": link["from"], "to": link["to"]} for link in parsed["links"]
    ]


def test_showcase_multi_host_placement_generates_split_compose(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server, "GENERATED_COMPOSE", tmp_path / "docker-compose.yml")
    result = generate_configs(
        {
            "hosts": ["robot", "verifier"],
            "sources": [{"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}],
            "monitors": [
                {
                    "id": "monitor_robot",
                    "host": "robot",
                    "source_keys": ["topic:/cmd_vel"],
                }
            ],
            "converters": [
                {
                    "id": "showcase_converter",
                    "class_path": "custom.rule_based_converter:RuleBasedConverter",
                    "host": "verifier",
                    "verdict_service_ids": ["showcase_verdict"],
                    "params": [
                        {"key": "source_match", "value": "^/cmd_vel$", "type": "string"},
                        {"key": "field_map", "value": '{"speed": "linear.x"}', "type": "json"},
                    ],
                }
            ],
            "verdict_services": [
                {
                    "id": "showcase_verdict",
                    "class_path": "custom.threshold_verdict:ThresholdVerdict",
                    "host": "verifier",
                    "params": [
                        {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
                        {"key": "field", "value": "speed", "type": "string"},
                        {"key": "op", "value": ">", "type": "string"},
                        {"key": "threshold", "value": "0.3", "type": "number"},
                    ],
                }
            ],
        }
    )

    assert {config["host_id"] for config in result["configs"]} == {"robot", "verifier"}
    assert result["request"]["links"][0]["payload"] == "records"
    compose = yaml.safe_load(Path(result["compose_path"]).read_text())
    assert set(compose["services"]) == {"mosquitto", "generated_robot", "generated_verifier"}
    assert "monitor_node.py --config /generated/robot.yaml" in (
        compose["services"]["generated_robot"]["command"][-1]
    )
    assert "node_runner.py --config /generated/verifier.yaml" in (
        compose["services"]["generated_verifier"]["command"][-1]
    )
    verifier = yaml.safe_load(
        next(c for c in result["configs"] if c["host_id"] == "verifier")["yaml"]
    )
    assert verifier["inputs"][0]["type"] == "mqtt"
    assert verifier["inputs"][0]["payload"] == "records"


def _chain_payload(**converter_overrides):
    converters = [
        {
            "id": "stage_filter",
            "class_path": "custom.odom_speed_filter:OdomSpeedFilter",
            "input_source_keys": ["topic:/odom"],
            "verdict_service_ids": [],
        },
        {
            "id": "stage_aggregate",
            "class_path": "custom.speed_aggregate_filter:SpeedAggregateFilter",
            "input_source_keys": [],
            "input_converter_ids": ["stage_filter"],
            "verdict_service_ids": ["speed_check"],
        },
    ]
    for key, value in converter_overrides.items():
        index, field = key
        converters[index][field] = value
    return {
        "sources": [{"name": "/odom", "interface": "nav_msgs/msg/Odometry"}],
        "monitors": [{"id": "monitor_robot", "source_keys": ["topic:/odom"]}],
        "converters": converters,
        "verdict_services": [
            {
                "id": "speed_check",
                "class_path": "custom.threshold_verdict:ThresholdVerdict",
            }
        ],
    }


def test_showcase_builds_converter_chain_on_shared_host():
    request = build_generation_request(_chain_payload())

    runtimes = {
        runtime["id"]: runtime
        for host in request["hosts"]
        for runtime in host["runtimes"]
    }
    assert runtimes["stage_filter"]["input_from"] == ["odom"]
    assert runtimes["stage_aggregate"]["input_from"] == ["stage_filter_dsl_record"]
    assert runtimes["speed_check"]["input_from"] == ["stage_aggregate_dsl_record"]
    assert request["links"] == []


def test_showcase_rejects_cross_host_converter_chain():
    payload = _chain_payload()
    payload["hosts"] = ["robot", "other"]
    payload["converters"][1]["host"] = "other"
    with pytest.raises(ValueError, match="must share a host"):
        build_generation_request(payload)


def test_showcase_rejects_converter_chain_cycle():
    payload = _chain_payload()
    payload["converters"][0]["input_converter_ids"] = ["stage_aggregate"]
    with pytest.raises(ValueError, match="cycle"):
        build_generation_request(payload)


def test_showcase_honours_explicit_empty_pipeline_lists():
    request = build_generation_request(
        {
            "sources": [{"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}],
            "monitors": [
                {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel"]}
            ],
            "converters": [],
            "verdict_services": [],
        }
    )

    kinds = [runtime["kind"] for runtime in request["hosts"][0]["runtimes"]]
    assert kinds == ["ros2", "monitor"]
    assert request["links"] == []


def test_showcase_rejects_verdict_service_without_feeding_converter():
    with pytest.raises(ValueError, match="no feeding converter"):
        build_generation_request(
            {
                "sources": [
                    {"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}
                ],
                "monitors": [
                    {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel"]}
                ],
                "converters": [],
                "verdict_services": [
                    {
                        "id": "orphan_verdict",
                        "class_path": "custom.threshold_verdict:ThresholdVerdict",
                    }
                ],
            }
        )


def test_showcase_rejects_converter_input_without_monitor():
    with pytest.raises(ValueError, match="without a monitor runtime"):
        build_generation_request(
            {
                "sources": [
                    {"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}
                ],
                "monitors": [],
                "converters": [
                    {
                        "id": "showcase_converter",
                        "class_path": "custom.rule_based_converter:RuleBasedConverter",
                        "input_source_keys": ["topic:/cmd_vel"],
                        "verdict_service_ids": [],
                    }
                ],
                "verdict_services": [],
            }
        )


def test_showcase_requires_at_least_one_source():
    with pytest.raises(ValueError, match="at least one"):
        build_generation_request({"sources": []})


def test_showcase_robot_start_uses_host_network_and_ipc(monkeypatch):
    import webui.server as server

    commands = []

    def fake_run_completed(command, timeout=120):
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(command, 0, "robot-container-id\n")
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "true\n")
        return subprocess.CompletedProcess(command, 0, "")

    started_log_streams = []

    monkeypatch.setattr(server, "_run_completed", fake_run_completed)
    monkeypatch.setattr(
        server,
        "_start_robot_log_stream",
        lambda robot: started_log_streams.append(robot.container_id),
    )
    monkeypatch.setattr(server.STATE, "robot", None)

    result = start_robot(
        {
            "dockerfile": "Dockerfile",
            "command": "source /opt/ros/kilted/setup.bash && ros2 topic list",
        }
    )

    run_command = next(command for command in commands if command[:2] == ["docker", "run"])
    assert result["running"] is True
    assert "--network" in run_command
    assert run_command[run_command.index("--network") + 1] == "host"
    assert "--ipc" in run_command
    assert run_command[run_command.index("--ipc") + 1] == "host"
    assert "source /opt/ros/kilted/setup.bash && ros2 topic list" in run_command
    assert started_log_streams == ["robot-container-id"]


def test_showcase_clear_verdicts_truncates_showcase_jsonl(tmp_path, monkeypatch):
    import webui.server as server

    output_root = tmp_path / "output"
    generated_root = tmp_path / "generated"
    verdict_path = output_root / "showcase" / "robot" / "verdicts_robot.jsonl"
    generated_verdict_path = generated_root / "verdicts_generated.jsonl"
    other_path = output_root / "mode1" / "verdicts_mode1.jsonl"
    verdict_path.parent.mkdir(parents=True)
    generated_verdict_path.parent.mkdir(parents=True)
    other_path.parent.mkdir(parents=True)
    verdict_path.write_text(
        '{"timestamp": 1.0, "property_id": "p", "result": false}\n',
        encoding="utf-8",
    )
    generated_verdict_path.write_text(
        '{"timestamp": 2.0, "property_id": "p", "result": true}\n',
        encoding="utf-8",
    )
    other_path.write_text("keep me\n", encoding="utf-8")

    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(server, "GENERATED_DIR", generated_root)

    assert len(recent_verdicts()) == 2
    result = clear_verdicts()

    assert result["cleared_files"] == 2
    assert verdict_path.read_text(encoding="utf-8") == ""
    assert generated_verdict_path.read_text(encoding="utf-8") == ""
    assert other_path.read_text(encoding="utf-8") == "keep me\n"
    assert recent_verdicts() == []
