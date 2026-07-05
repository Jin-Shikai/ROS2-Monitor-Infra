from pathlib import Path
import subprocess

import pytest
import yaml

from webui.server import (
    EventHub,
    RunState,
    _line_looks_like_verdict,
    build_generation_request,
    clear_verdicts,
    discover_graph,
    generate_configs,
    plugin_payload,
    recent_verdicts,
    start_generated_run,
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
            "converter_class": "custom.speed:CmdVelSpeedConverter",
            "verdict_class": "custom.threshold:ThresholdVerdict",
            "verdict_params": [
                {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
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
    assert runtimes[2]["class_path"] == "custom.speed:CmdVelSpeedConverter"
    assert runtimes[2]["input_from"] == ["cmd_vel", "odom"]
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
                    "class_path": "custom.speed:CmdVelSpeedConverter",
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
                    "class_path": "custom.threshold:ThresholdVerdict",
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
    assert [item["id"] for item in payload["plugins"]] == [
        "blank",
        "speed_check",
        "two_robot_relative_speed",
        "service_effect_consistency",
    ]

    speed = next(item for item in payload["plugins"] if item["id"] == "speed_check")
    assert speed["converter"] == "custom.speed:CmdVelSpeedConverter"
    assert speed["verdict"] == "custom.threshold:ThresholdVerdict"
    assert speed["converter_params"] == []
    assert [row["key"] for row in speed["verdict_params"]] == ["threshold"]

    fleet = next(
        item for item in payload["plugins"] if item["id"] == "two_robot_relative_speed"
    )
    assert fleet["hosts"] == ["robot1", "robot2", "converter_host", "verdict_host"]
    assert fleet["placement"] == {"converter": "converter_host", "verdict": "verdict_host"}
    assert fleet["converter"] == "custom.relative_speed:RelativeSpeedConverter"
    assert fleet["converter_params"] == []
    assert [row["key"] for row in fleet["verdict_params"]] == ["threshold"]

    reset = next(
        item for item in payload["plugins"] if item["id"] == "service_effect_consistency"
    )
    assert reset["converter"] == "custom.reset_pose_effect:ResetPoseEffectConverter"
    assert reset["verdict"] == "custom.reset_pose_effect:ResetPoseEffectVerdict"
    assert {source["source_kind"] for source in reset["sources"]} == {"service", "topic"}
    assert [row["key"] for row in reset["converter_params"]] == [
        "deadline_sec",
        "tolerance_m",
    ]
    assert reset["verdict_params"] == []


def test_showcase_discovery_falls_back_when_local_graph_is_empty(monkeypatch):
    import webui.server as server

    monkeypatch.setattr(
        server,
        "_discover_graph_locally",
        lambda: {"topics": [], "services": [], "actions": []},
    )
    monkeypatch.setattr(
        server,
        "_discover_graph_with_docker",
        lambda: {
            "topics": [
                {
                    "name": "/odom",
                    "interface": "nav_msgs/msg/Odometry",
                    "source_kind": "topic",
                }
            ],
            "services": [],
            "actions": [],
        },
    )

    result = discover_graph()

    assert result["available"] is True
    assert result["method"] == "docker"
    assert result["resource_count"] == 1
    assert result["warnings"] == [{"method": "local", "empty": True}]
    assert result["topics"][0]["name"] == "/odom"


def test_showcase_generation_uses_manifest_defaults_for_empty_preset_params():
    request = build_generation_request(
        {
            "sources": [
                {"name": "/robot1/odom", "interface": "nav_msgs/msg/Odometry", "host": "robot1"},
                {"name": "/robot2/odom", "interface": "nav_msgs/msg/Odometry", "host": "robot2"},
            ],
            "monitors": [
                {"id": "m1", "host": "robot1", "source_keys": ["topic:/robot1/odom"]},
                {"id": "m2", "host": "robot2", "source_keys": ["topic:/robot2/odom"]},
            ],
            "converters": [
                {
                    "id": "relative_speed",
                    "host": "converter_host",
                    "class_path": "custom.relative_speed:RelativeSpeedConverter",
                    "input_source_keys": ["topic:/robot1/odom", "topic:/robot2/odom"],
                    "verdict_service_ids": ["relative_speed_check"],
                }
            ],
            "verdict_services": [
                {
                    "id": "relative_speed_check",
                    "host": "verdict_host",
                    "class_path": "custom.threshold:ThresholdVerdict",
                }
            ],
        }
    )

    runtimes = [rt for host in request["hosts"] for rt in host["runtimes"]]
    converter = next(rt for rt in runtimes if rt["id"] == "relative_speed")
    verdict = next(rt for rt in runtimes if rt["id"] == "relative_speed_check")
    assert "robot_a" not in converter
    assert "robot_b" not in converter
    assert "field" not in verdict
    assert verdict["threshold"] == 0.3


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
            "converter_class": "custom.speed:CmdVelSpeedConverter",
            "verdict_class": "custom.threshold:ThresholdVerdict",
            "verdict_params": [
                {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
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
    assert parsed["verdict_services"][0]["type"] == "custom.threshold:ThresholdVerdict"
    assert parsed["links"][-1]["to"] == "verdict:showcase_verdict"
    compose = yaml.safe_load(Path(result["compose_path"]).read_text())
    service = compose["services"]["generated_robot"]
    assert service["network_mode"] == "host"
    assert service["ipc"] == "host"
    assert "../../demo/common:/demo/common:ro" not in service["volumes"]
    assert "topic_robot.py" not in service["command"][-1]
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
                    "class_path": "custom.reset_pose_effect:ResetPoseEffectConverter",
                    "input_source_keys": ["service:/reset"],
                }
            ],
            "verdict_params": [
                {"key": "property_id", "value": "reset_ok", "type": "string"},
                {"key": "threshold", "value": "0.3", "type": "number"},
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
                    "class_path": "custom.speed:CmdVelSpeedConverter",
                    "host": "verifier",
                    "verdict_service_ids": ["showcase_verdict"],
                }
            ],
            "verdict_services": [
                {
                    "id": "showcase_verdict",
                    "class_path": "custom.threshold:ThresholdVerdict",
                    "host": "verifier",
                    "params": [
                        {"key": "property_id", "value": "cmd_vel_limit", "type": "string"},
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
                        "class_path": "custom.threshold:ThresholdVerdict",
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
                        "class_path": "custom.speed:CmdVelSpeedConverter",
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


def test_showcase_start_run_adds_services_when_stack_is_active(tmp_path, monkeypatch):
    import webui.server as server

    class FakeProcess:
        stdout = None

        def __init__(self) -> None:
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.terminated = True

    commands = []
    previous = FakeProcess()

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server, "GENERATED_COMPOSE", tmp_path / "docker-compose.yml")
    server.GENERATED_COMPOSE.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(
        server,
        "generate_configs",
        lambda payload: {"compose_path": str(server.GENERATED_COMPOSE)},
    )
    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command)
        or subprocess.CompletedProcess(command, 0, "started\n"),
    )

    def fake_log_stream(target_id, command):
        return RunState(
            target_id=target_id,
            command=command,
            compose_path=server.GENERATED_COMPOSE,
            started_at=1.0,
            process=FakeProcess(),
        )

    monkeypatch.setattr(server, "_start_compose_log_stream", fake_log_stream)
    monkeypatch.setattr(
        server.STATE,
        "run",
        RunState(
            target_id="generated_host2",
            command=["old"],
            compose_path=server.GENERATED_COMPOSE,
            started_at=0.0,
            process=previous,
        ),
    )
    monkeypatch.setattr(server.STATE, "generated", {"compose_path": str(server.GENERATED_COMPOSE)})

    result = start_generated_run(
        {
            "target_services": ["mosquitto", "generated_host3", "generated_host4"],
        }
    )

    assert commands[-1][-3:] == ["mosquitto", "generated_host3", "generated_host4"]
    assert "-d" in commands[-1]
    assert previous.terminated is True
    assert result["running"] is True
    assert result["message"] == "Started mosquitto, generated_host3, generated_host4."


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
