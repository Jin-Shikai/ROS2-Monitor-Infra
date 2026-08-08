from pathlib import Path
import subprocess

import pytest
import yaml

from webui.server import (
    EventHub,
    ShowcaseState,
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


def test_showcase_log_ids_stay_monotonic_across_clears():
    state = ShowcaseState()
    first = state.append_log("first run")
    state.logs.clear()
    second = state.append_log("second run")

    assert second["id"] > first["id"]
    assert state.snapshot_logs() == [second]

    robot_first = state.append_robot_log("robot up")
    state.clear_robot_logs()
    robot_second = state.append_robot_log("robot again")

    assert robot_second["id"] > robot_first["id"]


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
    assert [row["key"] for row in speed["converter_params"]] == ["speed_path"]
    assert [row["key"] for row in speed["verdict_params"]] == [
        "threshold",
        "property_id",
    ]

    fleet = next(
        item for item in payload["plugins"] if item["id"] == "two_robot_relative_speed"
    )
    assert fleet["hosts"] == ["robot1", "robot2", "converter_host", "verdict_host"]
    assert fleet["placement"] == {"converter": "converter_host", "verdict": "verdict_host"}
    assert fleet["converter"] == "custom.relative_speed:RelativeSpeedConverter"
    assert fleet["converter_params"] == []
    assert [row["key"] for row in fleet["verdict_params"]] == [
        "threshold",
        "property_id",
    ]

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
    assert parsed["monitor"]["output_dir"] == str(
        server.ROOT / "output" / "showcase" / "robot"
    )
    assert parsed["converters"][0]["id"] == "showcase_converter"
    assert parsed["verdict_services"][0]["type"] == "custom.threshold:ThresholdVerdict"
    assert parsed["links"][-1]["to"] == "verdict:showcase_verdict"
    # Local mode always runs runtimes natively: no compose file is written.
    assert result["native"] is True
    assert result["configs"][0]["entrypoint"] == "monitor_node"
    assert not (tmp_path / "docker-compose.yml").exists()


def test_showcase_generate_configs_writes_service_action_sections(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
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


def test_showcase_multi_host_placement_generates_split_native_configs(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
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
    assert result["native"] is True
    assert not (tmp_path / "docker-compose.yml").exists()
    entrypoints = {config["host_id"]: config["entrypoint"] for config in result["configs"]}
    assert entrypoints == {"robot": "monitor_node", "verifier": "node_runner"}
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


def test_showcase_connects_verdicts_for_unnamed_converters():
    request = build_generation_request(
        {
            "sources": [{"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}],
            "monitors": [
                {"id": "monitor_robot", "source_keys": ["topic:/cmd_vel"]}
            ],
            "converters": [
                {
                    "class_path": "custom.speed:CmdVelSpeedConverter",
                    "verdict_service_ids": ["shared_verdict"],
                },
                {
                    "class_path": "custom.speed:CmdVelSpeedConverter",
                    "verdict_service_ids": ["shared_verdict"],
                },
            ],
            "verdict_services": [
                {
                    "id": "shared_verdict",
                    "class_path": "custom.threshold:ThresholdVerdict",
                }
            ],
        }
    )

    runtimes = request["hosts"][0]["runtimes"]
    verdict = next(rt for rt in runtimes if rt["kind"] == "verdict_service")
    assert sorted(verdict["input_from"]) == [
        "showcase_converter_1_dsl_record",
        "showcase_converter_2_dsl_record",
    ]


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


def test_showcase_robot_start_spawns_native_process_group(monkeypatch):
    import webui.server as server

    spawned = []

    class FakeProcess:
        pid = 4242
        stdout = None

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        spawned.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        server.threading, "Thread",
        lambda *args, **kwargs: type("T", (), {"start": lambda self: None})(),
    )
    monkeypatch.setattr(server.STATE, "robot", None)

    result = start_robot(
        {"command": "source /opt/ros/kilted/setup.bash && ros2 topic list"}
    )

    command, kwargs = spawned[0]
    assert result["running"] is True
    assert result["pid"] == 4242
    assert command == [
        "/bin/bash", "-lc",
        "source /opt/ros/kilted/setup.bash && ros2 topic list",
    ]
    assert kwargs["start_new_session"] is True

    with pytest.raises(RuntimeError, match="already running"):
        start_robot({"command": "echo again"})
    monkeypatch.setattr(server.STATE, "robot", None)


def test_showcase_start_run_native_starts_selected_services(tmp_path, monkeypatch):
    import webui.server as server

    class FakeProcess:
        pid = 999
        stdout = None

        def poll(self):
            return None

    generated = {
        "native": True,
        "request": {"links": [{"transport": {"kind": "mqtt", "port": 1884}}]},
        "configs": [
            {"host_id": "host2", "entrypoint": "monitor_node", "path": "/tmp/host2.yaml"},
            {"host_id": "host3", "entrypoint": "node_runner", "path": "/tmp/host3.yaml"},
            {"host_id": "host4", "entrypoint": "node_runner", "path": "/tmp/host4.yaml"},
        ],
    }

    spawned = []

    def fake_spawn(name, command, extra_env=None):
        spawned.append((name, command, extra_env))
        server.STATE.native_procs[name] = FakeProcess()

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server, "_spawn_native_service", fake_spawn)
    monkeypatch.setattr(server, "_port_listening", lambda host, port: False)
    monkeypatch.setattr(server, "generate_configs", lambda payload: generated)
    monkeypatch.setattr(server.STATE, "native_procs", {"generated_host2": FakeProcess()})
    monkeypatch.setattr(server.STATE, "native_started_at", 1.0)
    monkeypatch.setattr(server.STATE, "generated", generated)

    result = start_generated_run(
        {
            "target_services": ["mosquitto", "generated_host3", "generated_host4"],
        }
    )

    names = [name for name, _, _ in spawned]
    assert names[0] == "mosquitto"
    assert set(names[1:]) == {"generated_host3", "generated_host4"}
    assert "generated_host2" not in names
    envs = {name: extra_env for name, _, extra_env in spawned}
    assert envs["generated_host3"] == {"CONVERTER_IO_LOG": "DEBUG"}
    assert envs["generated_host4"] == {"CONVERTER_IO_LOG": "DEBUG"}
    assert result["running"] is True
    assert "generated_host3: started (node_runner)" in result["message"]
    assert "mosquitto: started on 1884" in result["message"]


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


def _lan_registry_e5():
    return {
        "shikai-pi_local": {
            "id": "shikai-pi_local",
            "address": "shikai@shikai-pi.local",
            "os": "linux",
            "home": "/home/shikai",
            "python": "/usr/bin/python3",
            "status": "ready",
        },
        "shikais-mbp_local": {
            "id": "shikais-mbp_local",
            "address": "alex@Shikais-MBP.local",
            "os": "darwin",
            "home": "/Users/alex",
            "python": "/opt/homebrew/bin/python3.12",
            "status": "ready",
        },
    }


def test_showcase_lan_generation_places_runtimes_natively(tmp_path, monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server.lan_mode, "load_registry", _lan_registry_e5)
    monkeypatch.setattr(server, "current_mode", lambda: "lan")
    monkeypatch.setattr(
        server, "_resolve_lan_address",
        lambda hostname: "192.168.2.18" if hostname == "shikai-pi.local" else hostname,
    )
    result = generate_configs(
        {
            "broker": {"host": "shikai-pi_local", "port": 1884},
            "hosts": ["shikai-pi_local", "shikais-mbp_local"],
            "sources": [
                {
                    "name": "/robot1/amcl_pose",
                    "interface": "geometry_msgs/msg/PoseWithCovarianceStamped",
                    "host": "shikai-pi_local",
                },
                {
                    "name": "/robot2/amcl_pose",
                    "interface": "geometry_msgs/msg/PoseWithCovarianceStamped",
                    "host": "shikai-pi_local",
                },
            ],
            "monitors": [
                {
                    "id": "monitor_e5",
                    "host": "shikai-pi_local",
                    "source_keys": ["topic:/robot1/amcl_pose", "topic:/robot2/amcl_pose"],
                }
            ],
            "converters": [
                {
                    "id": "separation",
                    "class_path": "custom.separation_converter:SeparationDistanceConverter",
                    "host": "shikais-mbp_local",
                    "verdict_service_ids": ["separation_check"],
                }
            ],
            "verdict_services": [
                {
                    "id": "separation_check",
                    "class_path": "custom.separation_verdict:SeparationDistanceVerdict",
                    "host": "shikais-mbp_local",
                }
            ],
        }
    )

    # Links carry the broker host's numeric LAN address, resolved from
    # its registry id (macOS gates mDNS per binary, so .local names are
    # not reliable on the checker).
    assert all(
        link["transport"]["broker"] == "192.168.2.18"
        and link["transport"]["port"] == 1884
        for link in result["request"]["links"]
    )
    assert result["native"] is True
    lan = result["lan"]
    assert lan["broker_host_id"] == "shikai-pi_local"
    assert lan["local_services"] == []
    assert lan["remote"] == {
        "shikai-pi_local": {"filename": "shikai-pi_local.yaml", "entrypoint": "monitor_node"},
        "shikais-mbp_local": {"filename": "shikais-mbp_local.yaml", "entrypoint": "node_runner"},
    }
    # Remote runtimes write into the remote project copy (cwd-relative).
    outputs = {
        config["host_id"]: yaml.safe_load(config["yaml"])["monitor"]["output_dir"]
        for config in result["configs"]
    }
    assert outputs == {
        "shikai-pi_local": "output/showcase/shikai-pi_local",
        "shikais-mbp_local": "output/showcase/shikais-mbp_local",
    }


def test_showcase_lan_rejects_monitor_on_macos_host(monkeypatch):
    import webui.server as server

    monkeypatch.setattr(server.lan_mode, "load_registry", _lan_registry_e5)
    monkeypatch.setattr(server, "current_mode", lambda: "lan")
    with pytest.raises(ValueError, match="macOS machine without"):
        build_generation_request(
            {
                "hosts": ["shikais-mbp_local"],
                "sources": [
                    {
                        "name": "/cmd_vel",
                        "interface": "geometry_msgs/msg/Twist",
                        "host": "shikais-mbp_local",
                    }
                ],
                "monitors": [
                    {
                        "id": "monitor_mac",
                        "host": "shikais-mbp_local",
                        "source_keys": ["topic:/cmd_vel"],
                    }
                ],
                "converters": [],
                "verdict_services": [],
            }
        )


def test_showcase_lan_start_runs_runtimes_over_ssh(tmp_path, monkeypatch):
    import webui.server as server

    class FakeProcess:
        pid = 999
        stdout = None

        def poll(self):
            return None

    generated = {
        "native": True,
        "request": {
            "links": [
                {"transport": {"kind": "mqtt", "broker": "shikai-pi.local", "port": 1884}}
            ]
        },
        "configs": [
            {"host_id": "shikai-pi_local", "entrypoint": "monitor_node",
             "filename": "shikai-pi_local.yaml", "path": "/tmp/pi.yaml"},
            {"host_id": "shikais-mbp_local", "entrypoint": "node_runner",
             "filename": "shikais-mbp_local.yaml", "path": "/tmp/mac.yaml"},
        ],
        "lan": {
            "mode": "lan",
            "local_services": [],
            "remote": {
                "shikai-pi_local": {"filename": "shikai-pi_local.yaml", "entrypoint": "monitor_node"},
                "shikais-mbp_local": {"filename": "shikais-mbp_local.yaml", "entrypoint": "node_runner"},
            },
            "broker_host_id": "shikai-pi_local",
        },
    }

    synced = []
    remote_commands = []

    def fake_remote_native_process(host, command):
        remote_commands.append((host["id"], command))
        return FakeProcess()

    monkeypatch.setattr(server, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(server.lan_mode, "load_registry", _lan_registry_e5)
    monkeypatch.setattr(server.lan_mode, "sync_project", lambda host: synced.append(host["id"]))
    monkeypatch.setattr(server.lan_mode, "remote_native_process", fake_remote_native_process)
    monkeypatch.setattr(server, "_port_listening", lambda host, port: False)
    monkeypatch.setattr(server.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(server, "_read_native_logs", lambda name, proc: None)
    monkeypatch.setattr(server, "_ensure_lan_pull_thread", lambda: None)
    monkeypatch.setattr(server, "current_mode", lambda: "lan")
    monkeypatch.setattr(server.STATE, "lan_deployed", {})
    monkeypatch.setattr(server.STATE, "lan_log_procs", {})
    monkeypatch.setattr(server.STATE, "lan_broker", None)
    monkeypatch.setattr(server.STATE, "native_procs", {})
    monkeypatch.setattr(server.STATE, "generated", generated)

    result = server._start_lan_run(generated, [], None)

    # Broker first (on the Pi), then the runner (Mac), then the monitor (Pi).
    assert [host_id for host_id, _ in remote_commands] == [
        "shikai-pi_local", "shikais-mbp_local", "shikai-pi_local",
    ]
    assert remote_commands[0][1] == "exec mosquitto -c generated/showcase/mosquitto_native.conf"
    mac_command = remote_commands[1][1]
    assert "monitor/node_runner.py -c generated/showcase/shikais-mbp_local.yaml" in mac_command
    assert "/opt/homebrew/bin/python3.12" in mac_command
    assert "CONVERTER_IO_LOG=DEBUG" in mac_command
    pi_command = remote_commands[2][1]
    assert "monitor/monitor_node.py -c generated/showcase/shikai-pi_local.yaml" in pi_command
    assert ". /opt/ros/kilted/setup.bash" in pi_command
    # The broker conf was written locally so rsync ships it to the Pi.
    assert (tmp_path / "mosquitto_native.conf").read_text(encoding="utf-8") == (
        "listener 1884 0.0.0.0\nallow_anonymous true\n"
    )
    assert synced == ["shikai-pi_local", "shikais-mbp_local"]
    assert result["running"] is True
    assert server.STATE.lan_broker["host_id"] == "shikai-pi_local"
    assert set(server.STATE.lan_deployed) == {"shikai-pi_local", "shikais-mbp_local"}
