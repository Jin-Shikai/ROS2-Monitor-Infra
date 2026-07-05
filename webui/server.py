"""Small stdlib showcase server for ROS2-Monitor-Infra.

The server wraps the existing runtime:
  * discover the ROS graph;
  * collect user-selected monitor sources and plugin kwargs;
  * generate deployment JSON + runtime YAML via monitor/config_gen.py;
  * generate and run an all-in-one Docker Compose monitor for that YAML;
  * expose logs and verdict JSONL records to the static frontend.
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
GENERATED_DIR = ROOT / "generated" / "showcase"
GENERATED_COMPOSE = GENERATED_DIR / "docker-compose.yml"
PLUGIN_MANIFEST_DIR = ROOT / "custom" / "manifests"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "monitor"))

from config_gen import GenerationRequest, project  # noqa: E402


class EventHub:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.next_id = 1
        self.subscribers: set[queue.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self.lock:
            self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self.lock:
            self.subscribers.discard(subscriber)

    def publish(self, event_type: str, payload: Any) -> dict[str, Any]:
        with self.lock:
            event = {"id": self.next_id, "type": event_type, "payload": payload}
            self.next_id += 1
            subscribers = list(self.subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass
        return event


PLUGIN_PRESETS: list[dict[str, Any]] = [
    {
        "id": "blank",
        "name": "New",
        "summary": "Start from an empty topology.",
        "converter_manifest": "",
        "verdict_manifest": "",
        "hosts": [],
        "placement": {},
        "sources": [],
        "overrides": {"converter": {}, "verdict": {}},
    },
    {
        "id": "speed_check",
        "name": "Demo preset: speed check",
        "summary": "Checks /cmd_vel.linear.x against a speed threshold.",
        "converter_manifest": "rule_based_converter",
        "verdict_manifest": "threshold_verdict",
        "hosts": ["robot"],
        "placement": {},
        "robot_command": (
            "source /opt/ros/kilted/setup.bash && "
            "python3 /demo/common/topic_robot.py cmd-velocity-cycle "
            "--ros-args -r __node:=speed_check_robot"
        ),
        "sources": [
            {
                "name": "/cmd_vel",
                "interface": "geometry_msgs/msg/Twist",
                "source_kind": "topic",
            }
        ],
        "overrides": {
            "converter": {
                "source_match": "^/cmd_vel$",
                "field_map": {"speed": "linear.x"},
                "property_id": "speed_check",
            },
            "verdict": {
                "property_id": "speed_check",
                "field": "speed",
                "op": ">",
                "threshold": 0.3,
            },
        },
    },
    {
        "id": "two_robot_relative_speed",
        "name": "Demo preset: two-robot relative speed",
        "summary": "Two monitored robots; converter and verdict on their own hosts; checks relative speed against 0.5 m/s.",
        "converter_manifest": "relative_speed_converter",
        "verdict_manifest": "threshold_verdict",
        "hosts": ["robot1", "robot2", "converter_host", "verdict_host"],
        "placement": {"converter": "converter_host", "verdict": "verdict_host"},
        "robot_command": (
            "source /opt/ros/kilted/setup.bash && "
            "python3 /demo/common/topic_robot.py speed-limit-cycle "
            "--ros-args -r __node:=robot1 -r __ns:=/robot1 & "
            "python3 /demo/common/topic_robot.py speed-limit-cycle "
            "--ros-args -r __node:=robot2 -r __ns:=/robot2"
        ),
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
        "overrides": {
            "converter": {},
            "verdict": {
                "property_id": "fleet_relative_speed",
                "field": "relative_speed",
                "threshold": 0.5,
            },
        },
    },
    {
        "id": "service_effect_consistency",
        "name": "Demo preset: reset service effect",
        "summary": "A successful /reset_pose response must be followed by /odom returning near the origin.",
        "converter_manifest": "reset_pose_effect_converter",
        "verdict_manifest": "reset_pose_effect_verdict",
        "hosts": ["robot"],
        "placement": {},
        "robot_command": (
            "source /opt/ros/kilted/setup.bash && "
            "python3 /demo/common/reset_robot.py "
            "--ros-args -r __node:=reset_pose_robot"
        ),
        "sources": [
            {
                "name": "/reset_pose",
                "interface": "std_srvs/srv/Trigger",
                "source_kind": "service",
            },
            {
                "name": "/odom",
                "interface": "nav_msgs/msg/Odometry",
                "source_kind": "topic",
            },
        ],
        "overrides": {"converter": {}, "verdict": {}},
    },
]


@dataclass
class RunState:
    target_id: str
    command: list[str]
    compose_path: Path
    started_at: float
    process: subprocess.Popen[str]
    next_log_id: int = 1


@dataclass
class RobotState:
    container_id: str
    container_name: str
    dockerfile: Path
    command: str
    image_tag: str
    started_at: float
    log_process: subprocess.Popen[str] | None = None


class ShowcaseState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.run: RunState | None = None
        self.robot: RobotState | None = None
        self.logs: deque[dict[str, Any]] = deque(maxlen=3000)
        self.robot_logs: deque[dict[str, Any]] = deque(maxlen=1000)
        self.generated: dict[str, Any] | None = None

    def append_log(self, line: str) -> None:
        with self.lock:
            log_id = self.run.next_log_id if self.run else len(self.logs) + 1
            if self.run:
                self.run.next_log_id += 1
            self.logs.append(
                {"id": log_id, "ts": time.time(), "line": line.rstrip("\n")}
            )

    def snapshot_logs(self, since: int = 0, limit: int = 400) -> list[dict[str, Any]]:
        with self.lock:
            rows = [row for row in self.logs if int(row["id"]) > since]
        return rows[-limit:]

    def append_robot_log(self, line: str) -> dict[str, Any]:
        with self.lock:
            log_id = len(self.robot_logs) + 1
            if self.robot_logs:
                log_id = int(self.robot_logs[-1]["id"]) + 1
            row = {"id": log_id, "ts": time.time(), "line": line.rstrip("\n")}
            self.robot_logs.append(row)
            return row

    def snapshot_robot_logs(self, limit: int = 120) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.robot_logs)[-limit:]

    def clear_robot_logs(self) -> None:
        with self.lock:
            self.robot_logs.clear()


STATE = ShowcaseState()
EVENTS = EventHub()
_VERDICT_WATCHER_STARTED = False
_VERDICT_WATCHER_LOCK = threading.Lock()
ROBOT_CONTAINER_NAME = "ros2_monitor_ipc_robot"
ROBOT_IMAGE_TAG = "ros2-monitor-infra-dashboard-robot"
DEFAULT_ROBOT_COMMAND = (
    "source /opt/ros/kilted/setup.bash && "
    "python3 /demo/common/topic_robot.py cmd-velocity-cycle "
    "--ros-args -r __node:=showcase_robot"
)


def _resolve_workspace_path(value: str | None, default: str) -> Path:
    raw = (value or default).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as ex:
        raise ValueError("Dockerfile must be inside the project workspace.") from ex
    if not path.exists() or not path.is_file():
        raise ValueError(f"Dockerfile not found: {path}")
    return path


def _resolve_editable_path(value: str | None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("File path is required.")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    try:
        relative = path.relative_to(ROOT)
    except ValueError as ex:
        raise ValueError("Editable files must be inside the project workspace.") from ex
    blocked_parts = {".git", ".venv", "__pycache__"}
    if any(part in blocked_parts for part in relative.parts):
        raise ValueError("This workspace path is not editable from the dashboard.")
    return path


def read_workspace_file(path_value: str | None) -> dict[str, Any]:
    path = _resolve_editable_path(path_value)
    if not path.exists() or not path.is_file():
        raise ValueError(f"File not found: {path.relative_to(ROOT)}")
    return {
        "path": str(path.relative_to(ROOT)),
        "content": path.read_text(encoding="utf-8"),
    }


def write_workspace_file(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_editable_path(str(payload.get("path") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(payload.get("content") or ""), encoding="utf-8")
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size}


def _json_default_to_form_value(value: Any, type_name: str) -> str:
    if type_name == "json":
        return json.dumps(value, ensure_ascii=False)
    if type_name == "bool":
        return "true" if bool(value) else "false"
    if value is None:
        return ""
    return str(value)


def load_plugin_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    if not PLUGIN_MANIFEST_DIR.exists():
        return manifests
    for path in sorted(PLUGIN_MANIFEST_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest_id = str(data.get("id") or path.stem)
        params = []
        for param in list(data.get("params") or []):
            row = dict(param)
            row.setdefault("type", "string")
            row.setdefault("required", False)
            params.append(row)
        data["id"] = manifest_id
        data["params"] = params
        manifests[manifest_id] = data
    return manifests


def _manifest_param_rows(
    manifest: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    overrides = overrides or {}
    rows: list[dict[str, Any]] = []
    for param in list(manifest.get("params") or []):
        key = str(param.get("key") or "")
        type_name = str(param.get("type") or "string")
        value = overrides.get(key, param.get("default", ""))
        rows.append(
            {
                "key": key,
                "label": param.get("label") or key,
                "value": _json_default_to_form_value(value, type_name),
                "type": type_name,
                "required": bool(param.get("required", False)),
                "options": list(param.get("options") or []),
                "schema": True,
            }
        )
    return rows


def plugin_payload() -> dict[str, Any]:
    manifests = load_plugin_manifests()
    plugins: list[dict[str, Any]] = []
    for preset in PLUGIN_PRESETS:
        converter = manifests.get(str(preset.get("converter_manifest")), {})
        verdict = manifests.get(str(preset.get("verdict_manifest")), {})
        overrides = dict(preset.get("overrides") or {})
        plugins.append(
            {
                **preset,
                "converter": converter.get("class_path", ""),
                "verdict": verdict.get("class_path", ""),
                "converter_schema": converter,
                "verdict_schema": verdict,
                "converter_params": _manifest_param_rows(
                    converter, dict(overrides.get("converter") or {})
                ),
                "verdict_params": _manifest_param_rows(
                    verdict, dict(overrides.get("verdict") or {})
                ),
            }
        )
    return {"plugins": plugins, "manifests": list(manifests.values())}


def _run_completed(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def _robot_container_running(container_id: str | None) -> bool:
    if not container_id:
        return False
    completed = _run_completed(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
        timeout=10,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def _container_id_by_name(container_name: str) -> str | None:
    completed = _run_completed(
        ["docker", "ps", "-aq", "--filter", f"name=^/{container_name}$"], timeout=10
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def current_robot_payload() -> dict[str, Any]:
    with STATE.lock:
        robot = STATE.robot
    container_id = robot.container_id if robot else _container_id_by_name(ROBOT_CONTAINER_NAME)
    if not container_id:
        return {"running": False}
    running = _robot_container_running(container_id)
    return {
        "running": running,
        "container_id": container_id,
        "container_name": robot.container_name if robot else ROBOT_CONTAINER_NAME,
        "dockerfile": str(robot.dockerfile) if robot else "",
        "command": robot.command if robot else "",
        "image_tag": robot.image_tag if robot else ROBOT_IMAGE_TAG,
        "started_at": robot.started_at if robot else None,
    }


def _stop_robot_log_stream() -> None:
    with STATE.lock:
        robot = STATE.robot
        process = robot.log_process if robot else None
        if robot:
            robot.log_process = None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _read_robot_log_stream(process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        row = STATE.append_robot_log(line)
        EVENTS.publish("robot_log", row)
    EVENTS.publish("robot_state", current_robot_payload())


def _start_robot_log_stream(robot: RobotState) -> None:
    _stop_robot_log_stream()
    STATE.clear_robot_logs()
    process = subprocess.Popen(
        ["docker", "logs", "-f", "--tail", "120", robot.container_id],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    with STATE.lock:
        if STATE.robot and STATE.robot.container_id == robot.container_id:
            STATE.robot.log_process = process
    threading.Thread(target=_read_robot_log_stream, args=(process,), daemon=True).start()


def start_robot(payload: dict[str, Any]) -> dict[str, Any]:
    with STATE.lock:
        state_container_id = STATE.robot.container_id if STATE.robot else None
        existing_container_id = state_container_id or _container_id_by_name(ROBOT_CONTAINER_NAME)
        if _robot_container_running(existing_container_id):
            raise RuntimeError("Robot container is already running.")

    dockerfile = _resolve_workspace_path(payload.get("dockerfile"), "Dockerfile")
    command_text = str(payload.get("command") or DEFAULT_ROBOT_COMMAND).strip()
    if not command_text:
        raise ValueError("Start command is required.")

    build = _run_completed(
        ["docker", "build", "-f", str(dockerfile), "-t", ROBOT_IMAGE_TAG, str(ROOT)]
    )
    if build.returncode != 0:
        raise RuntimeError(build.stdout.strip() or "Docker build failed.")

    _run_completed(["docker", "stop", ROBOT_CONTAINER_NAME], timeout=20)
    _run_completed(["docker", "rm", ROBOT_CONTAINER_NAME], timeout=20)
    run_command = [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        ROBOT_CONTAINER_NAME,
        "--network",
        "host",
        "--ipc",
        "host",
        "-e",
        "ROS_DOMAIN_ID=0",
        "-v",
        f"{ROOT / 'demo' / 'common'}:/demo/common:ro",
        ROBOT_IMAGE_TAG,
        "/bin/bash",
        "-lc",
        command_text,
    ]
    started = _run_completed(run_command, timeout=60)
    if started.returncode != 0:
        raise RuntimeError(started.stdout.strip() or "Docker run failed.")

    robot = RobotState(
        container_id=started.stdout.strip(),
        container_name=ROBOT_CONTAINER_NAME,
        dockerfile=dockerfile,
        command=command_text,
        image_tag=ROBOT_IMAGE_TAG,
        started_at=time.time(),
    )
    _stop_robot_log_stream()
    with STATE.lock:
        STATE.robot = robot
    _start_robot_log_stream(robot)
    result = current_robot_payload()
    EVENTS.publish("robot_state", result)
    return result


def stop_robot() -> dict[str, Any]:
    with STATE.lock:
        robot = STATE.robot
    container_id = robot.container_id if robot else _container_id_by_name(ROBOT_CONTAINER_NAME)
    if not container_id:
        return {"running": False, "message": "No robot container is active."}
    _stop_robot_log_stream()
    completed = _run_completed(["docker", "stop", container_id], timeout=30)
    with STATE.lock:
        STATE.robot = None
    result = {
        "running": False,
        "message": completed.stdout.strip() or f"Stopped {ROBOT_CONTAINER_NAME}",
    }
    EVENTS.publish("robot_state", result)
    return result


def robot_logs(limit: int = 120) -> dict[str, Any]:
    with STATE.lock:
        robot = STATE.robot
    container_id = robot.container_id if robot else _container_id_by_name(ROBOT_CONTAINER_NAME)
    if not container_id:
        return {"logs": []}
    completed = _run_completed(
        ["docker", "logs", "--tail", str(limit), container_id], timeout=20
    )
    if completed.returncode != 0:
        return {"logs": [completed.stdout.strip()]}
    return {"logs": completed.stdout.splitlines()}


def safe_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return cleaned.strip("_") or "source"


def _coerce_param(value: Any, type_name: str | None = None) -> Any:
    if not isinstance(value, str):
        return value
    type_name = type_name or "auto"
    text = value.strip()
    if type_name == "string":
        return value
    if type_name == "number":
        return float(text)
    if type_name == "int":
        return int(text)
    if type_name == "bool":
        return text.lower() in {"1", "true", "yes", "on"}
    if type_name == "enum":
        return value
    if type_name == "json":
        return json.loads(text)
    if type_name == "auto":
        if text.lower() in {"true", "false"}:
            return text.lower() == "true"
        if text.lower() in {"null", "none"}:
            return None
        if text.startswith(("{", "[", '"')):
            return json.loads(text)
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return value
    return value


def _manifest_defaults_for_class(class_path: Any) -> dict[str, Any]:
    for manifest in load_plugin_manifests().values():
        if manifest.get("class_path") == class_path:
            return {
                str(p["key"]): _coerce_param(p.get("default"), p.get("type"))
                for p in list(manifest.get("params") or [])
                if p.get("key") and "default" in p
            }
    return {}


def _params_to_kwargs(rows: list[dict[str, Any]] | None, class_path: Any = None) -> dict[str, Any]:
    kwargs = _manifest_defaults_for_class(class_path)
    for row in rows or []:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        kwargs[key] = _coerce_param(row.get("value", ""), row.get("type"))
    return kwargs


def _node_id(value: Any, fallback: str) -> str:
    raw = safe_slug(str(value or fallback))
    return raw or fallback


SUPPORTED_SOURCE_KINDS = {"topic", "service", "action"}


def _source_key(source_kind: str, name: str) -> str:
    return f"{source_kind}:{name}"


def _sources_from_payload(
    payload: dict[str, Any],
    default_host: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Parse the monitored sources; each carries a `host` placement."""
    raw_sources = list(payload.get("sources") or [])
    if not raw_sources:
        raise ValueError("Add at least one monitored source before generating.")

    sources: list[dict[str, str]] = []
    id_by_key: dict[str, str] = {}
    used_ids: set[str] = set()
    for raw in raw_sources:
        name = str(raw.get("name") or "").strip()
        interface = str(raw.get("interface") or raw.get("type") or "").strip()
        source_kind = str(raw.get("source_kind") or "topic").strip()
        if source_kind not in SUPPORTED_SOURCE_KINDS:
            raise ValueError(
                "Source kind must be one of: topic, service, action."
            )
        if not name or not interface:
            raise ValueError("Every source needs a name and interface.")
        default_id = name if source_kind == "topic" else f"{source_kind}_{name}"
        base_id = safe_slug(raw.get("id") or default_id)
        source_id = base_id
        suffix = 2
        while source_id in used_ids:
            source_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(source_id)
        id_by_key[_source_key(source_kind, name)] = source_id
        sources.append(
            {
                "id": source_id,
                "source_kind": source_kind,
                "name": name,
                "interface": interface,
                "host": safe_slug(str(raw.get("host") or default_host)),
            }
        )
    return sources, id_by_key


def _reject_chain_cycles(chain_inputs: dict[str, list[str]]) -> None:
    DONE, IN_PROGRESS = 2, 1
    state: dict[str, int] = {}

    def visit(converter_id: str, path: list[str]) -> None:
        if state.get(converter_id) == DONE:
            return
        if state.get(converter_id) == IN_PROGRESS:
            cycle = path[path.index(converter_id):] + [converter_id]
            raise ValueError(
                "converter chain contains a cycle: " + " -> ".join(cycle)
            )
        state[converter_id] = IN_PROGRESS
        for upstream_id in chain_inputs.get(converter_id, []):
            visit(upstream_id, path + [converter_id])
        state[converter_id] = DONE

    for converter_id in chain_inputs:
        visit(converter_id, [])


def build_generation_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a config_gen request from the dashboard's placement form.

    Every source, converter, and verdict service carries a `host`; links are
    derived wherever a dataflow edge crosses a host boundary (records for
    monitor->converter, dsl for converter->verdict), using the shared MQTT
    broker from `payload["broker"]`.
    """
    broker_raw = dict(payload.get("broker") or {})
    broker_host = str(broker_raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    broker_port = int(broker_raw.get("port") or 1883)
    transport = {"kind": "mqtt", "broker": broker_host, "port": broker_port, "qos": 1}

    host_ids: list[str] = []

    def add_host(value: Any, fallback: str = "robot") -> str:
        host_id = safe_slug(str(value or fallback)) or fallback
        if host_id not in host_ids:
            host_ids.append(host_id)
        return host_id

    for host in list(payload.get("hosts") or []):
        add_host(host)
    if not host_ids:
        add_host("robot")
    default_host = host_ids[0]

    sources, id_by_key = _sources_from_payload(payload, default_host)
    source_ids = [source["id"] for source in sources]
    source_host = {source["id"]: add_host(source["host"]) for source in sources}
    monitor_payloads = list(payload.get("monitors") or [])
    monitor_runtimes: dict[str, dict[str, Any]] = {}
    monitor_host: dict[str, str] = {}
    monitors_by_source: dict[str, list[str]] = {sid: [] for sid in source_ids}
    if monitor_payloads:
        for index, raw_monitor in enumerate(monitor_payloads, start=1):
            monitor_id = _node_id(raw_monitor.get("id"), f"monitor_{index}")
            selected_keys = list(raw_monitor.get("source_keys") or [])
            subscribe = [id_by_key[key] for key in selected_keys if key in id_by_key]
            monitor_host[monitor_id] = add_host(raw_monitor.get("host"), default_host)
            monitor_runtimes[monitor_id] = {
                "id": monitor_id,
                "kind": "monitor",
                "subscribe": subscribe,
            }
            for sid in subscribe:
                monitors_by_source.setdefault(sid, []).append(monitor_id)

    # A missing key means a legacy single-pipeline request, so synthesize the
    # default pair; an explicit (possibly empty) list is honoured as-is.
    converter_payloads = list(payload.get("converters") or [])
    verdict_payloads = list(payload.get("verdict_services") or [])
    if not converter_payloads and "converters" not in payload:
        converter_payloads = [{
            "id": "showcase_converter",
            "class_path": payload.get("converter_class"),
            "verdict_service_ids": ["showcase_verdict"],
            "params": payload.get("converter_params"),
        }]
    if not verdict_payloads and "verdict_services" not in payload:
        verdict_payloads = [{
            "id": "showcase_verdict",
            "class_path": payload.get("verdict_class"),
            "params": payload.get("verdict_params"),
        }]

    # First pass assigns every converter its id, host, and output record id so
    # chain references (input_converter_ids) can point forward or backward.
    converter_specs: list[tuple[str, dict[str, Any]]] = []
    converter_host: dict[str, str] = {}
    converter_output: dict[str, str] = {}
    for index, raw_converter in enumerate(converter_payloads, start=1):
        converter_id = _node_id(raw_converter.get("id"), f"showcase_converter_{index}")
        converter_specs.append((converter_id, raw_converter))
        converter_output[converter_id] = _node_id(
            raw_converter.get("output_id"), f"{converter_id}_dsl_record"
        )
        converter_host[converter_id] = add_host(raw_converter.get("host"), default_host)

    converter_runtimes: dict[str, dict[str, Any]] = {}
    chain_inputs: dict[str, list[str]] = {}
    for converter_id, raw_converter in converter_specs:
        selected_keys = list(raw_converter.get("input_source_keys") or [])
        converter_inputs = [id_by_key[key] for key in selected_keys if key in id_by_key]
        if not converter_inputs and "input_source_keys" not in raw_converter:
            converter_inputs = list(source_ids)
        upstream_ids = [
            _node_id(item, str(item))
            for item in list(raw_converter.get("input_converter_ids") or [])
        ]
        upstream_ids = [
            uid for uid in upstream_ids
            if uid in converter_output and uid != converter_id
        ]
        chain_inputs[converter_id] = upstream_ids
        for upstream_id in upstream_ids:
            if converter_host[upstream_id] != converter_host[converter_id]:
                raise ValueError(
                    f"chained converters '{upstream_id}' -> '{converter_id}' must "
                    f"share a host ('{converter_host[upstream_id]}' vs "
                    f"'{converter_host[converter_id]}'); converter chaining is "
                    "in-process."
                )
            converter_inputs.append(converter_output[upstream_id])
        converter_runtimes[converter_id] = {
            "id": converter_id,
            "kind": "converter",
            "converter": raw_converter.get("converter") or "dsl_converter",
            "class_path": str(
                raw_converter.get("class_path")
                or "custom.rule_based:RuleBasedConverter"
            ),
            "input_from": converter_inputs,
            "output_to": converter_output[converter_id],
            **_params_to_kwargs(
                raw_converter.get("params"),
                raw_converter.get("class_path")
                or "custom.rule_based:RuleBasedConverter",
            ),
        }
    _reject_chain_cycles(chain_inputs)

    verdict_inputs: dict[str, list[str]] = {}
    verdict_feeders: dict[str, list[str]] = {}
    for raw_converter in converter_payloads:
        converter_id = _node_id(raw_converter.get("id"), "showcase_converter")
        output_id = converter_output.get(converter_id)
        if output_id is None:
            continue
        verdict_ids = [
            _node_id(item, str(item))
            for item in list(raw_converter.get("verdict_service_ids") or [])
        ]
        if (
            not verdict_ids
            and "verdict_service_ids" not in raw_converter
            and verdict_payloads
        ):
            verdict_ids = [_node_id(verdict_payloads[0].get("id"), "showcase_verdict")]
        for verdict_id in verdict_ids:
            verdict_inputs.setdefault(verdict_id, []).append(output_id)
            verdict_feeders.setdefault(verdict_id, []).append(converter_id)

    verdict_runtimes: dict[str, dict[str, Any]] = {}
    verdict_host: dict[str, str] = {}
    for index, raw_verdict in enumerate(verdict_payloads, start=1):
        verdict_id = _node_id(raw_verdict.get("id"), f"showcase_verdict_{index}")
        inputs = verdict_inputs.get(verdict_id)
        if not inputs:
            raise ValueError(
                f"verdict service '{verdict_id}' has no feeding converter; "
                "connect a converter to this verdict service."
            )
        verdict_host[verdict_id] = add_host(raw_verdict.get("host"), default_host)
        verdict_runtimes[verdict_id] = {
            "id": verdict_id,
            "kind": "verdict_service",
            "class_path": str(
                raw_verdict.get("class_path")
                or "custom.threshold:ThresholdVerdict"
            ),
            "input_from": inputs,
            "output_to": raw_verdict.get("output_to") or [
                {"kind": "stdout"},
                {"kind": "file", "path": "verdicts_{session_id}.jsonl"},
            ],
            **_params_to_kwargs(
                raw_verdict.get("params"),
                raw_verdict.get("class_path")
                or "custom.threshold:ThresholdVerdict",
            ),
        }

    runtimes_by_host: dict[str, list[dict[str, Any]]] = {h: [] for h in host_ids}
    for host_id in host_ids:
        host_sources = [
            {k: v for k, v in s.items() if k != "host"}
            for s in sources if source_host[s["id"]] == host_id
        ]
        if host_sources:
            runtimes_by_host[host_id].append(
                {"id": f"ros2_{host_id}", "kind": "ros2", "sources": host_sources}
            )
    for monitor_id, runtime in monitor_runtimes.items():
        runtimes_by_host[monitor_host[monitor_id]].append(runtime)
    for converter_id, runtime in converter_runtimes.items():
        runtimes_by_host[converter_host[converter_id]].append(runtime)
    for verdict_id, runtime in verdict_runtimes.items():
        runtimes_by_host[verdict_host[verdict_id]].append(runtime)

    links: list[dict[str, Any]] = []
    for converter_id, runtime in converter_runtimes.items():
        to_host = converter_host[converter_id]
        feeding_monitors = sorted({
            monitor_id
            for sid in runtime["input_from"]
            for monitor_id in monitors_by_source.get(sid, [])
            if monitor_host.get(monitor_id) != to_host
        })
        missing_monitors = [
            sid for sid in runtime["input_from"]
            if sid in source_host and not monitors_by_source.get(sid)
        ]
        if missing_monitors:
            raise ValueError(
                f"converter '{converter_id}' consumes source(s) without a monitor runtime: "
                + ", ".join(missing_monitors)
            )
        for monitor_id in feeding_monitors:
            from_host = monitor_host[monitor_id]
            links.append({
                "id": f"records_{monitor_id}_{converter_id}",
                "from_host": from_host,
                "to_host": to_host,
                "from_runtime": monitor_id,
                "to_runtime": converter_id,
                "payload": "records",
                "transport": dict(transport),
            })
    for verdict_id, feeders in verdict_feeders.items():
        to_host = verdict_host.get(verdict_id)
        if to_host is None:
            continue
        for converter_id in feeders:
            from_host = converter_host[converter_id]
            if from_host == to_host:
                continue
            links.append({
                "id": f"dsl_{converter_id}_{verdict_id}",
                "from_host": from_host,
                "to_host": to_host,
                "from_runtime": converter_id,
                "to_runtime": verdict_id,
                "payload": "dsl",
                "transport": dict(transport),
            })

    return {
        "hosts": [
            {"id": host_id, "runtimes": runtimes}
            for host_id, runtimes in runtimes_by_host.items()
            if runtimes
        ],
        "links": links,
    }


def _compose_command(config: dict[str, Any]) -> str:
    config_path = f"/generated/{config['filename']}"
    if config["entrypoint"] == "monitor_node":
        return (
            "set -e; "
            "source /opt/ros/kilted/setup.bash; "
            f"python3 /monitor/monitor_node.py --config {config_path}"
        )
    return f"set -e; python3 /monitor/node_runner.py --config {config_path}"


def _write_generated_compose(
    configs: list[dict[str, Any]], request_data: dict[str, Any]
) -> None:
    needs_broker = bool(request_data.get("links"))
    services: dict[str, Any] = {}
    if needs_broker:
        mosquitto_conf = GENERATED_DIR / "mosquitto.conf"
        mosquitto_conf.write_text(
            "listener 1883 0.0.0.0\nallow_anonymous true\n",
            encoding="utf-8",
        )
        services["mosquitto"] = {
            "image": "eclipse-mosquitto:2",
            "network_mode": "host",
            "volumes": ["./mosquitto.conf:/mosquitto/config/mosquitto.conf:ro"],
        }

    for config in configs:
        service_name = f"generated_{safe_slug(config['host_id'])}"
        service: dict[str, Any] = {
                "build": {"context": "../..", "dockerfile": "Dockerfile"},
                "network_mode": "host",
                "ipc": "host",
                "environment": [
                    "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}",
                    "ROS_DISTRO=kilted",
                    "PYTHONUNBUFFERED=1",
                    f"MONITOR_CONFIG=/generated/{config['filename']}",
                ],
                "volumes": [
                    "../../monitor:/monitor",
                    "../../custom:/monitor/custom",
                    ".:/generated:ro",
                    "../../output/showcase:/output/showcase",
                ],
                "command": ["/bin/bash", "-lc", _compose_command(config)],
                "stdin_open": True,
                "tty": True,
        }
        if needs_broker:
            service["depends_on"] = ["mosquitto"]
        services[service_name] = service

    compose = {"services": services}
    GENERATED_COMPOSE.write_text(
        yaml.safe_dump(compose, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def generate_configs(payload: dict[str, Any]) -> dict[str, Any]:
    request_data = build_generation_request(payload)
    request = GenerationRequest.from_dict(request_data)
    generated = project(request)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    request_path = GENERATED_DIR / "request.json"
    request_path.write_text(json.dumps(request_data, indent=2), encoding="utf-8")

    configs = []
    for gen in generated.values():
        config = dict(gen.config)
        monitor = dict(config.get("monitor") or {})
        monitor["output_dir"] = f"/output/showcase/{gen.host_id}"
        config["monitor"] = monitor
        path = GENERATED_DIR / gen.filename
        path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        configs.append(
            {
                "host_id": gen.host_id,
                "entrypoint": gen.entrypoint,
                "filename": gen.filename,
                "path": str(path),
                "run_command": gen.run_command().replace("<outdir>", str(GENERATED_DIR)),
                "yaml": path.read_text(encoding="utf-8"),
            }
        )

    _write_generated_compose(configs, request_data)
    payload_out = {
        "request": request_data,
        "request_path": str(request_path),
        "compose_path": str(GENERATED_COMPOSE),
        "configs": configs,
    }
    with STATE.lock:
        STATE.generated = payload_out
    EVENTS.publish("generated", payload_out)
    return payload_out


def _discover_graph_locally() -> dict[str, Any]:
    from graph_discovery import discover

    return discover()


def _discover_graph_with_docker() -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--build",
        "--no-deps",
        "monitor",
        "/bin/bash",
        "-lc",
        "source /opt/ros/kilted/setup.bash && python3 /monitor/graph_discovery.py --json",
    ]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or "Docker discovery failed.")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Docker discovery returned no JSON.")
    return json.loads(lines[-1])


def discover_graph() -> dict[str, Any]:
    methods: list[dict[str, str]] = []
    try:
        graph = _discover_graph_locally()
        return {"available": True, "method": "local", **graph}
    except Exception as ex:
        methods.append({"method": "local", "error": str(ex)})

    try:
        graph = _discover_graph_with_docker()
        return {"available": True, "method": "docker", "warnings": methods, **graph}
    except Exception as ex:
        methods.append({"method": "docker", "error": str(ex)})
        return {
            "available": False,
            "error": "ROS graph discovery failed.",
            "attempts": methods,
            "topics": [],
            "services": [],
            "actions": [],
        }


def current_run_payload() -> dict[str, Any]:
    with STATE.lock:
        run = STATE.run
        generated = STATE.generated
        if run is None:
            return {"running": False, "generated": generated is not None}
        poll = run.process.poll()
        if poll is not None:
            return {
                "running": False,
                "generated": generated is not None,
                "target_id": run.target_id,
                "exit_code": poll,
                "started_at": run.started_at,
            }
        return {
            "running": True,
            "generated": generated is not None,
            "target_id": run.target_id,
            "started_at": run.started_at,
            "command": run.command,
        }


def _read_process_logs(process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        STATE.append_log(line)
        with STATE.lock:
            log = STATE.logs[-1] if STATE.logs else None
        if log is not None:
            EVENTS.publish("log", log)
            if _line_looks_like_verdict(line):
                publish_recent_verdicts(delay=0.2)
    EVENTS.publish("run_state", current_run_payload())


def _line_looks_like_verdict(line: str) -> bool:
    return "Verdict(" in line or '"property_id"' in line or "verdicts_" in line


def publish_recent_verdicts(delay: float = 0.0) -> None:
    def _publish() -> None:
        EVENTS.publish("verdicts", {"verdicts": recent_verdicts(limit=50)})

    if delay <= 0:
        _publish()
        return
    threading.Timer(delay, _publish).start()


def start_generated_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    target_services = [str(item) for item in list(payload.get("target_services") or [])]
    with STATE.lock:
        if STATE.run is not None and STATE.run.process.poll() is None:
            result = current_run_payload()
            result["message"] = "Runtime stack is already active."
            return result
    generated_payload = None
    if payload:
        generated_payload = generate_configs(payload)
    with STATE.lock:
        if STATE.generated is None or not GENERATED_COMPOSE.exists():
            raise RuntimeError("Configure monitor sources before starting the monitor.")

    command = ["docker", "compose", "-f", str(GENERATED_COMPOSE), "up", "--build", *target_services]
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    with STATE.lock:
        STATE.logs.clear()
        STATE.run = RunState(
            target_id="generated_stack" if not target_services else ",".join(target_services),
            command=command,
            compose_path=GENERATED_COMPOSE,
            started_at=time.time(),
            process=process,
        )
    threading.Thread(target=_read_process_logs, args=(process,), daemon=True).start()
    result = current_run_payload()
    if generated_payload is not None:
        result["generated_files"] = generated_payload
    EVENTS.publish("run_state", result)
    return result


def stop_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    target_services = [str(item) for item in list(payload.get("target_services") or [])]
    with STATE.lock:
        run = STATE.run
    if run is None:
        return {"running": False, "message": "No monitor run is active."}

    stop_command = ["docker", "compose", "-f", str(run.compose_path), "stop", *target_services]
    down_command = ["docker", "compose", "-f", str(run.compose_path), "down"]
    subprocess.run(
        stop_command if target_services else down_command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    if target_services:
        result = current_run_payload()
        result["message"] = f"Stopped {', '.join(target_services)}"
        EVENTS.publish("run_state", result)
        return result

    if run.process.poll() is None:
        run.process.terminate()
    try:
        run.process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        run.process.kill()
    with STATE.lock:
        STATE.run = None
    result = {"running": False, "message": f"Stopped {run.target_id}"}
    EVENTS.publish("run_state", result)
    return result


def recent_verdicts(limit: int = 50) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    roots = [ROOT / "output" / "showcase", GENERATED_DIR]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if "verdict" not in path.name:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines[-limit:]:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "property_id" in row and "result" in row:
                    row["_file"] = str(path.relative_to(ROOT))
                    verdicts.append(row)
    verdicts.sort(key=lambda row: float(row.get("timestamp") or 0.0), reverse=True)
    return verdicts[:limit]


def _verdict_file_signature() -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for path in _verdict_jsonl_paths():
        try:
            stat = path.stat()
            label = str(path.relative_to(ROOT))
            signature.append((label, stat.st_size, stat.st_mtime_ns))
        except OSError:
            continue
    return tuple(sorted(signature))


def _watch_verdict_files(interval: float = 1.0) -> None:
    last_signature = _verdict_file_signature()
    while True:
        time.sleep(interval)
        signature = _verdict_file_signature()
        if signature != last_signature:
            last_signature = signature
            publish_recent_verdicts()


def ensure_verdict_watcher() -> None:
    global _VERDICT_WATCHER_STARTED
    with _VERDICT_WATCHER_LOCK:
        if _VERDICT_WATCHER_STARTED:
            return
        thread = threading.Thread(target=_watch_verdict_files, daemon=True)
        thread.start()
        _VERDICT_WATCHER_STARTED = True


def _verdict_jsonl_paths() -> list[Path]:
    paths: list[Path] = []
    roots = [ROOT / "output" / "showcase", GENERATED_DIR]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if "verdict" in path.name:
                paths.append(path)
    return paths


def clear_verdicts() -> dict[str, Any]:
    paths = _verdict_jsonl_paths()
    cleared = 0
    for path in paths:
        try:
            path.write_text("", encoding="utf-8")
            cleared += 1
        except OSError:
            continue
    result = {
        "cleared_files": cleared,
        "paths": [str(path.relative_to(ROOT)) for path in paths],
    }
    EVENTS.publish("verdicts", {"verdicts": []})
    return result


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[showcase] {self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("cache-control", "no-store, max-age=0")
        self.send_header("pragma", "no-cache")
        self.send_header("expires", "0")
        super().end_headers()

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, ex: Exception, status: int = 400) -> None:
        self._send_json({"error": str(ex)}, status=status)

    def _write_sse(self, event_type: str, payload: Any, event_id: int | None = None) -> None:
        if event_id is not None:
            self.wfile.write(f"id: {event_id}\n".encode("utf-8"))
        self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
        data = json.dumps(payload, default=str, ensure_ascii=False)
        for line in data.splitlines() or [""]:
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def _send_event_stream(self) -> None:
        ensure_verdict_watcher()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "keep-alive")
        self.send_header("x-accel-buffering", "no")
        self.end_headers()

        subscriber = EVENTS.subscribe()
        try:
            self._write_sse("robot_state", current_robot_payload())
            self._write_sse("robot_logs", {"logs": STATE.snapshot_robot_logs(limit=120)})
            self._write_sse("run_state", current_run_payload())
            self._write_sse("logs", {"logs": STATE.snapshot_logs(limit=400)})
            self._write_sse("verdicts", {"verdicts": recent_verdicts(limit=50)})
            with STATE.lock:
                generated = STATE.generated
            if generated is not None:
                self._write_sse("generated", generated)

            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    continue
                self._write_sse(event["type"], event["payload"], event_id=event["id"])
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            EVENTS.unsubscribe(subscriber)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                return self._send_json({"ok": True, "root": str(ROOT)})
            if parsed.path == "/api/events":
                return self._send_event_stream()
            if parsed.path == "/api/robots/current":
                return self._send_json(current_robot_payload())
            if parsed.path == "/api/robots/logs":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["120"])[0])
                return self._send_json(robot_logs(limit=limit))
            if parsed.path == "/api/runs/current":
                return self._send_json(current_run_payload())
            if parsed.path == "/api/runs/logs":
                qs = parse_qs(parsed.query)
                since = int((qs.get("since") or ["0"])[0])
                return self._send_json({"logs": STATE.snapshot_logs(since=since)})
            if parsed.path == "/api/verdicts":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                return self._send_json({"verdicts": recent_verdicts(limit=limit)})
            if parsed.path == "/api/plugins":
                return self._send_json(plugin_payload())
            if parsed.path == "/api/files":
                qs = parse_qs(parsed.query)
                return self._send_json(read_workspace_file((qs.get("path") or [""])[0]))
            if parsed.path in {"/api/discovery/graph", "/api/discovery/topics"}:
                return self._send_json(discover_graph())
            return super().do_GET()
        except ValueError as ex:
            return self._send_error_json(ex, status=HTTPStatus.BAD_REQUEST)
        except RuntimeError as ex:
            return self._send_error_json(ex, status=HTTPStatus.CONFLICT)

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/api/generate":
                return self._send_json(generate_configs(payload))
            if self.path == "/api/robots/start":
                return self._send_json(start_robot(payload))
            if self.path == "/api/robots/stop":
                return self._send_json(stop_robot())
            if self.path == "/api/runs/start":
                return self._send_json(start_generated_run(payload))
            if self.path == "/api/runs/stop":
                return self._send_json(stop_run(payload))
            if self.path == "/api/verdicts/clear":
                return self._send_json(clear_verdicts())
            if self.path == "/api/files":
                return self._send_json(write_workspace_file(payload))
        except ValueError as ex:
            return self._send_error_json(ex, status=HTTPStatus.BAD_REQUEST)
        except RuntimeError as ex:
            return self._send_error_json(ex, status=HTTPStatus.CONFLICT)
        except Exception as ex:
            return self._send_error_json(ex, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local showcase UI server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args(argv)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Showcase UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop_run()
        except Exception:
            pass
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
