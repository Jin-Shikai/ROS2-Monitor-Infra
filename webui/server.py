"""Small stdlib showcase server for ROS2-Monitor-Infra.

The server wraps the existing runtime:
  * discover the ROS graph;
  * collect user-selected monitor sources and plugin kwargs;
  * generate deployment JSON + runtime YAML via monitor/config_gen.py;
  * run the generated runtimes natively — locally as host processes, and in
    LAN mode on registered SSH hosts under live SSH sessions;
  * expose logs and verdict JSONL records to the static frontend.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shlex
import signal
import socket
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
PLUGIN_MANIFEST_DIR = ROOT / "custom" / "manifests"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "monitor"))
sys.path.insert(0, str(ROOT / "webui"))

from config_gen import GenerationRequest, project  # noqa: E402
import lan_mode  # noqa: E402


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
        "converter_manifest": "speed_converter",
        "verdict_manifest": "threshold_verdict",
        "hosts": ["robot"],
        "placement": {},
        "robot_command": (
            "source /opt/ros/kilted/setup.bash && "
            "python3 demo/common/topic_robot.py cmd-velocity-cycle "
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
            "converter": {},
            "verdict": {
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
            "python3 demo/common/topic_robot.py speed-limit-cycle "
            "--ros-args -r __node:=robot1 -r __ns:=/robot1 & "
            "python3 demo/common/topic_robot.py speed-limit-cycle "
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
            "python3 demo/common/reset_robot.py "
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
class RobotState:
    """The ROS application, always a native host process group (GUI/DDS)."""

    command: str
    started_at: float
    process: subprocess.Popen[str]


class ShowcaseState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.robot: RobotState | None = None
        self.logs: deque[dict[str, Any]] = deque(maxlen=3000)
        self.robot_logs: deque[dict[str, Any]] = deque(maxlen=1000)
        self.generated: dict[str, Any] | None = None
        # LAN mode bookkeeping: host_id -> config filename deployed there,
        # plus the live SSH session running that host's runtime, plus the
        # remotely started broker (when the links point at a LAN host).
        self.lan_deployed: dict[str, str] = {}
        self.lan_log_procs: dict[str, subprocess.Popen[str]] = {}
        self.lan_broker: dict[str, Any] | None = None
        # Native mode bookkeeping: service name -> host process running a
        # generated runtime (or the mosquitto broker) directly on this machine.
        self.native_procs: dict[str, subprocess.Popen[str]] = {}
        self.native_started_at: float | None = None
        # Ids grow monotonically for the server's lifetime, even across run
        # restarts and log clears: SSE clients drop rows with ids they have
        # already seen, so reused ids would make new logs invisible to them.
        self._next_log_id = 1
        self._next_robot_log_id = 1

    def append_log(self, line: str) -> dict[str, Any]:
        with self.lock:
            row = {"id": self._next_log_id, "ts": time.time(), "line": line.rstrip("\r\n")}
            self._next_log_id += 1
            self.logs.append(row)
            return row

    def snapshot_logs(self, limit: int = 400) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.logs)[-limit:]

    def append_robot_log(self, line: str) -> dict[str, Any]:
        with self.lock:
            row = {"id": self._next_robot_log_id, "ts": time.time(), "line": line.rstrip("\n")}
            self._next_robot_log_id += 1
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
_MODE_LOCK = threading.Lock()
_MODE = "local"
_LAN_PULL_STOP: threading.Event | None = None


def current_mode() -> str:
    with _MODE_LOCK:
        return _MODE


def mode_payload() -> dict[str, Any]:
    return {"mode": current_mode(), "lan_ip": lan_mode.lan_ip()}


def set_mode(payload: dict[str, Any]) -> dict[str, Any]:
    global _MODE
    mode = str(payload.get("mode") or "").strip()
    if mode not in {"local", "lan"}:
        raise ValueError("Mode must be 'local' or 'lan'.")
    with _MODE_LOCK:
        _MODE = mode
    result = mode_payload()
    EVENTS.publish("mode", result)
    return result
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


def current_robot_payload() -> dict[str, Any]:
    with STATE.lock:
        robot = STATE.robot
    if robot is None:
        return {"running": False}
    return {
        "running": robot.process.poll() is None,
        "pid": robot.process.pid,
        "command": robot.command,
        "started_at": robot.started_at,
    }


def _read_robot_log_stream(process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        row = STATE.append_robot_log(line)
        EVENTS.publish("robot_log", row)
    EVENTS.publish("robot_state", current_robot_payload())


def _restore_signal_defaults() -> None:
    """Reset inherited signal dispositions in spawned runtimes.

    A server started as a background job inherits SIGINT=SIG_IGN and passes
    it on; a child bash could then never trap INT and every UI stop would
    fall through to SIGTERM/SIGKILL instead of a clean shutdown.
    """
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)


def start_robot(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the ROS application as a host process group.

    The application always runs natively on this machine: GUI applications
    (Gazebo/RViz) need the real display, and under Docker Desktop a container
    cannot join the host DDS graph anyway.
    """
    command_text = str(payload.get("command") or "").strip()
    if not command_text:
        raise ValueError("Start command is required.")

    with STATE.lock:
        robot = STATE.robot
    if robot is not None and robot.process.poll() is None:
        raise RuntimeError("Robot application is already running.")

    process = subprocess.Popen(
        ["/bin/bash", "-lc", command_text],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        preexec_fn=_restore_signal_defaults,
    )
    STATE.clear_robot_logs()
    with STATE.lock:
        STATE.robot = RobotState(
            command=command_text, started_at=time.time(), process=process
        )
    threading.Thread(target=_read_robot_log_stream, args=(process,), daemon=True).start()
    result = current_robot_payload()
    EVENTS.publish("robot_state", result)
    return result


def stop_robot() -> dict[str, Any]:
    """Signal the whole application process group and escalate if it lingers."""
    with STATE.lock:
        robot = STATE.robot
    if robot is None:
        return {"running": False, "message": "No robot application is active."}
    process = robot.process
    message = "Robot application was not running."
    if process.poll() is None:
        group = process.pid
        for sig, grace in ((signal.SIGINT, 20.0), (signal.SIGTERM, 8.0)):
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                break
            try:
                process.wait(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.poll() is None:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        message = "Stopped robot application."
    with STATE.lock:
        STATE.robot = None
    result = {"running": False, "message": message}
    EVENTS.publish("robot_state", result)
    return result


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
    mode = current_mode()
    lan_registry = lan_mode.load_registry() if mode == "lan" else {}
    broker_raw = dict(payload.get("broker") or {})
    broker_host = str(broker_raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    if mode == "lan":
        broker_entry = lan_registry.get(broker_host)
        if broker_entry is not None:
            # A registered host id names where the broker runs. The links
            # carry its numeric LAN address when resolvable: macOS gates
            # mDNS per binary, so a .local name would not resolve for an
            # unapproved remote python.
            hostname = str(broker_entry.get("address", "")).split("@", 1)[-1]
            broker_host = _resolve_lan_address(hostname)
        elif broker_host in {"127.0.0.1", "localhost"}:
            # Remote runtimes cannot reach a loopback broker; use this
            # machine's LAN address instead.
            broker_host = lan_mode.lan_ip()
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
                or "custom.speed:CmdVelSpeedConverter"
            ),
            "input_from": converter_inputs,
            "output_to": converter_output[converter_id],
            **_params_to_kwargs(
                raw_converter.get("params"),
                raw_converter.get("class_path")
                or "custom.speed:CmdVelSpeedConverter",
            ),
        }
    _reject_chain_cycles(chain_inputs)

    verdict_inputs: dict[str, list[str]] = {}
    verdict_feeders: dict[str, list[str]] = {}
    for converter_id, raw_converter in converter_specs:
        output_id = converter_output[converter_id]
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

    if mode == "lan":
        for host_id, runtimes in runtimes_by_host.items():
            if not runtimes or host_id == lan_mode.LOCAL_HOST_ID:
                continue
            entry = lan_registry.get(host_id)
            if entry is None:
                raise ValueError(
                    f"LAN mode: host '{host_id}' is not a registered SSH host. "
                    "Add it via the LAN host dialog (or place the runtime on 'local')."
                )
            if entry.get("status") != "ready":
                raise ValueError(
                    f"LAN mode: host '{host_id}' has no usable python3 "
                    f"(status: {entry.get('status')}); re-add the host."
                )
            if entry.get("os") == "darwin" and any(
                runtime.get("kind") in {"ros2", "monitor"} for runtime in runtimes
            ):
                raise ValueError(
                    f"LAN mode: host '{host_id}' is a macOS machine without "
                    "ROS 2, so it cannot join the LAN ROS graph. Place ROS "
                    "sources and monitor runtimes on a Linux host; macOS "
                    "hosts can run converters and verdict services (MQTT "
                    "only)."
                )

    return {
        "hosts": [
            {"id": host_id, "runtimes": runtimes}
            for host_id, runtimes in runtimes_by_host.items()
            if runtimes
        ],
        "links": links,
    }


def _resolve_lan_address(hostname: str) -> str:
    try:
        return socket.gethostbyname(hostname)
    except OSError:
        return hostname


def _broker_endpoint(request_data: dict[str, Any]) -> tuple[str, int]:
    for link in list(request_data.get("links") or []):
        transport = dict(link.get("transport") or {})
        if transport.get("broker") or transport.get("port"):
            return (
                str(transport.get("broker") or "127.0.0.1"),
                int(transport.get("port") or 1883),
            )
    return "127.0.0.1", 1883


def _broker_is_local(broker_host: str) -> bool:
    return broker_host in {"127.0.0.1", "localhost", lan_mode.lan_ip()}


def _lan_placement(
    configs: list[dict[str, Any]], request_data: dict[str, Any]
) -> dict[str, Any]:
    """Decide where every generated runtime (and the broker) runs.

    Registered SSH hosts run their runtime natively there over a live SSH
    session; any other placement target runs natively on this machine. The
    broker runs on the registered host whose LAN hostname the links point
    at, otherwise locally.
    """
    registry = lan_mode.load_registry()
    local_services: list[str] = []
    remote: dict[str, dict[str, str]] = {}
    for config in configs:
        host_id = config["host_id"]
        if host_id in registry:
            remote[host_id] = {
                "filename": config["filename"],
                "entrypoint": config["entrypoint"],
            }
        else:
            local_services.append(_native_service_name(host_id))
    broker_host, _ = _broker_endpoint(request_data)

    def is_broker_host(row: dict[str, Any]) -> bool:
        hostname = str(row.get("address", "")).split("@", 1)[-1]
        return broker_host in {hostname, _resolve_lan_address(hostname)}

    broker_host_id = next(
        (hid for hid, row in registry.items() if is_broker_host(row)), None
    )
    if request_data.get("links") and broker_host_id is None:
        local_services.append("mosquitto")
    return {
        "mode": "lan",
        "local_services": sorted(local_services),
        "remote": remote,
        "broker_host_id": broker_host_id,
    }


def generate_configs(payload: dict[str, Any]) -> dict[str, Any]:
    # Every generated runtime runs natively: as a host process here, or as
    # a host process on a registered LAN machine over SSH. The ROS
    # application and DDS need real host networking, and the LAN machines
    # run the monitor stack directly (thesis E5 deployment).
    lan = current_mode() == "lan"
    lan_registry = lan_mode.load_registry() if lan else {}
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
        if lan and gen.host_id in lan_registry:
            # Remote runtimes start with cwd = remote project root.
            monitor["output_dir"] = f"output/showcase/{gen.host_id}"
        else:
            output_dir = ROOT / "output" / "showcase" / gen.host_id
            output_dir.mkdir(parents=True, exist_ok=True)
            monitor["output_dir"] = str(output_dir)
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

    lan_info = _lan_placement(configs, request_data) if lan else None
    payload_out = {
        "request": request_data,
        "request_path": str(request_path),
        "configs": configs,
        "lan": lan_info,
        "native": True,
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


def _graph_resource_count(graph: dict[str, Any]) -> int:
    return sum(len(list(graph.get(key) or [])) for key in ("topics", "services", "actions"))


def discover_graph() -> dict[str, Any]:
    methods: list[dict[str, Any]] = []
    try:
        graph = _discover_graph_locally()
        count = _graph_resource_count(graph)
        if count:
            return {"available": True, "method": "local", "resource_count": count, **graph}
        methods.append({"method": "local", "empty": True})
    except Exception as ex:
        methods.append({"method": "local", "error": str(ex)})

    try:
        graph = _discover_graph_with_docker()
        return {
            "available": True,
            "method": "docker",
            "warnings": methods,
            "resource_count": _graph_resource_count(graph),
            **graph,
        }
    except Exception as ex:
        methods.append({"method": "docker", "error": str(ex)})
        if methods and methods[0].get("empty"):
            return {
                "available": True,
                "method": "local",
                "warnings": methods,
                "resource_count": 0,
                "topics": [],
                "services": [],
                "actions": [],
            }
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
        generated = STATE.generated
        native_procs = dict(STATE.native_procs)
        native_started_at = STATE.native_started_at
        lan_procs = dict(STATE.lan_log_procs)
        lan_broker = dict(STATE.lan_broker) if STATE.lan_broker else None
    services = {
        name: "running" if proc.poll() is None else "exited"
        for name, proc in sorted(native_procs.items())
    }
    for host_id, proc in sorted(lan_procs.items()):
        services[_native_service_name(host_id)] = (
            "running" if proc.poll() is None else "exited"
        )
    if lan_broker is not None:
        proc = lan_broker.get("process")
        services.setdefault(
            "mosquitto",
            "running" if proc is None or proc.poll() is None else "exited",
        )
    if not services:
        return {"running": False, "generated": generated is not None}
    return {
        "running": any(state == "running" for state in services.values()),
        "native": True,
        "generated": generated is not None,
        "target_id": ",".join(services),
        "services": services,
        "started_at": native_started_at,
    }


def _stop_log_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _lan_log(line: str) -> None:
    EVENTS.publish("log", STATE.append_log(line))


def _ensure_lan_pull_thread() -> None:
    """Poll deployed SSH hosts and pull their output/showcase files back so
    the local verdict watcher streams remote verdicts too."""
    global _LAN_PULL_STOP
    if _LAN_PULL_STOP is not None and not _LAN_PULL_STOP.is_set():
        return
    stop = threading.Event()
    _LAN_PULL_STOP = stop

    def loop() -> None:
        while not stop.wait(2.0):
            with STATE.lock:
                deployed = list(STATE.lan_deployed)
            if not deployed:
                stop.set()
                return
            registry = lan_mode.load_registry()
            for host_id in deployed:
                host = registry.get(host_id)
                if not host:
                    continue
                try:
                    lan_mode.pull_outputs(host)
                except Exception:
                    pass

    threading.Thread(target=loop, daemon=True).start()


def _remote_runtime_command(host: dict[str, Any], info: dict[str, str]) -> str:
    """Shell command that runs one generated runtime natively on a LAN host.

    Sourcing ROS (when present) must come before extending PYTHONPATH:
    setup.bash resets it and would drop the project paths otherwise.
    """
    script = {
        "monitor_node": "monitor/monitor_node.py",
        "node_runner": "monitor/node_runner.py",
    }[info["entrypoint"]]
    python = host.get("python") or "python3"
    return (
        "mkdir -p output/showcase; "
        "[ -f /opt/ros/kilted/setup.bash ] && . /opt/ros/kilted/setup.bash; "
        'export PYTHONPATH="$PWD:$PWD/monitor:$PYTHONPATH"; '
        "export PYTHONUNBUFFERED=1 CONVERTER_IO_LOG=DEBUG; "
        f"exec {shlex.quote(python)} {script} -c generated/showcase/{info['filename']}"
    )


def _ensure_lan_broker(
    lan_info: dict[str, Any],
    request_data: dict[str, Any],
    synced: set[str],
) -> list[str]:
    """Start (or reuse) mosquitto on the registered LAN host the links point
    at. A locally placed broker is _start_native_run's job instead."""
    broker_host_id = lan_info.get("broker_host_id")
    if not broker_host_id or not request_data.get("links"):
        return []
    broker_host, broker_port = _broker_endpoint(request_data)
    with STATE.lock:
        existing = STATE.lan_broker
    proc = existing.get("process") if existing else None
    if proc is not None and proc.poll() is None:
        message = "mosquitto: already running"
        _lan_log(message)
        return [message]
    if _port_listening(broker_host, broker_port):
        message = (
            "mosquitto: reusing the broker already listening on "
            f"{broker_host}:{broker_port}"
        )
        _lan_log(message)
        return [message]
    registry = lan_mode.load_registry()
    host = registry.get(broker_host_id)
    if host is None:
        raise RuntimeError(
            f"Broker host '{broker_host_id}' is no longer registered."
        )
    conf_path = GENERATED_DIR / "mosquitto_native.conf"
    conf_path.write_text(
        f"listener {broker_port} 0.0.0.0\nallow_anonymous true\n",
        encoding="utf-8",
    )
    _lan_log(f"[lan] {broker_host_id}: syncing project to {host['address']}...")
    lan_mode.sync_project(host)
    synced.add(broker_host_id)
    proc = lan_mode.remote_native_process(
        host, "exec mosquitto -c generated/showcase/mosquitto_native.conf"
    )
    threading.Thread(
        target=_read_native_logs, args=("mosquitto", proc), daemon=True
    ).start()
    with STATE.lock:
        STATE.lan_broker = {"host_id": broker_host_id, "process": proc}
    for _ in range(20):
        if _port_listening(broker_host, broker_port):
            break
        time.sleep(0.5)
    message = f"mosquitto: started on {broker_host}:{broker_port}"
    _lan_log(message)
    return [message]


def _start_lan_run(
    generated: dict[str, Any],
    target_services: list[str],
    generated_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Native LAN start: broker first, then this machine's runtimes, then
    remote runtimes over live SSH sessions (runners before monitors so no
    early records are dropped)."""
    lan_info = dict(generated.get("lan") or {})
    request_data = dict(generated.get("request") or {})
    registry = lan_mode.load_registry()
    remote = dict(lan_info.get("remote") or {})
    messages: list[str] = []
    synced: set[str] = set()

    if target_services:
        remote_targets = [
            host_id for host_id in remote
            if _native_service_name(host_id) in target_services
        ]
    else:
        remote_targets = list(remote)
    remote_targets.sort(
        key=lambda hid: 0 if remote[hid]["entrypoint"] == "node_runner" else 1
    )

    messages.extend(_ensure_lan_broker(lan_info, request_data, synced))

    local_result = _start_native_run(generated, target_services)
    local_message = str(local_result.get("message") or "")
    if local_message and "nothing to start" not in local_message:
        messages.append(local_message.removeprefix("Native run: "))

    for host_id in remote_targets:
        host = registry.get(host_id)
        if host is None:
            raise RuntimeError(f"LAN host '{host_id}' is no longer registered.")
        with STATE.lock:
            existing = STATE.lan_log_procs.get(host_id)
        if existing is not None and existing.poll() is None:
            message = f"{host_id}: already running"
            messages.append(message)
            _lan_log(message)
            continue
        if host_id not in synced:
            _lan_log(f"[lan] {host_id}: syncing project to {host['address']}...")
            lan_mode.sync_project(host)
            synced.add(host_id)
        info = remote[host_id]
        proc = lan_mode.remote_native_process(
            host, _remote_runtime_command(host, info)
        )
        name = _native_service_name(host_id)
        threading.Thread(
            target=_read_native_logs, args=(name, proc), daemon=True
        ).start()
        with STATE.lock:
            STATE.lan_deployed[host_id] = info["filename"]
            STATE.lan_log_procs[host_id] = proc
        message = f"{host_id}: started {info['entrypoint']} on {host['address']}"
        messages.append(message)
        _lan_log(f"[lan] {message}")

    with STATE.lock:
        has_deployed = bool(STATE.lan_deployed)
    if has_deployed:
        _ensure_lan_pull_thread()

    result = current_run_payload()
    result["message"] = "Started " + (
        "; ".join(messages) if messages else "nothing (no matching services)."
    )
    result["lan"] = {"deployed": dict(STATE.lan_deployed)}
    if generated_payload is not None:
        result["generated_files"] = generated_payload
    EVENTS.publish("run_state", result)
    return result


def _port_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _native_service_name(host_id: str) -> str:
    return f"generated_{safe_slug(host_id)}"


def _read_native_logs(name: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        EVENTS.publish("log", STATE.append_log(f"{name}  | {line}"))
    code = process.wait()
    EVENTS.publish("log", STATE.append_log(f"{name}  | exited with code {code}"))
    EVENTS.publish("run_state", current_run_payload())


def _spawn_native_service(
    name: str, command: list[str], extra_env: dict[str, str] | None = None
) -> None:
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env={**os.environ, **extra_env} if extra_env else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        preexec_fn=_restore_signal_defaults,
    )
    with STATE.lock:
        STATE.native_procs[name] = process
        if STATE.native_started_at is None:
            STATE.native_started_at = time.time()
    threading.Thread(
        target=_read_native_logs, args=(name, process), daemon=True
    ).start()


def _start_native_run(
    generated: dict[str, Any], target_services: list[str]
) -> dict[str, Any]:
    """Run the generated runtimes as host processes instead of containers.

    Required when the ROS application runs natively on this machine: with
    Docker Desktop, containers live in a VM and cannot join the host DDS
    graph. Service names mirror the compose services so the frontend's
    per-block start/stop keeps working.
    """
    request_data = dict(generated.get("request") or {})
    configs = list(generated.get("configs") or [])
    # LAN placement: registered hosts run remotely (over SSH); this
    # function only owns the local remainder and a locally placed broker.
    remote_hosts = set(((generated.get("lan") or {}).get("remote") or {}))
    broker_host, broker_port = _broker_endpoint(request_data)
    targets = set(target_services)
    messages: list[str] = []

    # Lifecycle events also go to the live log stream: services without an
    # owned process (e.g. a reused external broker) would otherwise show no
    # output at all when selected.
    def note(message: str) -> None:
        messages.append(message)
        _lan_log(message)

    with STATE.lock:
        stale = [
            name for name, proc in STATE.native_procs.items()
            if proc.poll() is not None
        ]
        for name in stale:
            STATE.native_procs.pop(name, None)
        running = set(STATE.native_procs)

    if (
        bool(request_data.get("links"))
        and _broker_is_local(broker_host)
        and (not targets or "mosquitto" in targets)
    ):
        if "mosquitto" in running:
            note("mosquitto: already running")
        elif _port_listening("127.0.0.1", broker_port):
            note(
                "mosquitto: reusing the external broker already listening on "
                f"127.0.0.1:{broker_port} (its logs are not captured here)"
            )
        else:
            conf_path = GENERATED_DIR / "mosquitto_native.conf"
            conf_path.write_text(
                f"listener {broker_port} 0.0.0.0\nallow_anonymous true\n",
                encoding="utf-8",
            )
            _spawn_native_service("mosquitto", ["mosquitto", "-c", str(conf_path)])
            note(f"mosquitto: started on {broker_port}")

    entrypoint_scripts = {
        "monitor_node": "monitor/monitor_node.py",
        "node_runner": "monitor/node_runner.py",
    }
    for config in configs:
        if config["host_id"] in remote_hosts:
            continue
        name = _native_service_name(config["host_id"])
        if targets and name not in targets:
            continue
        if name in running:
            note(f"{name}: already running")
            continue
        script = entrypoint_scripts.get(config["entrypoint"])
        if script is None:
            raise RuntimeError(f"Unknown entrypoint: {config['entrypoint']}")
        _spawn_native_service(
            name,
            [sys.executable, script, "-c", config["path"]],
            {"CONVERTER_IO_LOG": "DEBUG"},
        )
        note(f"{name}: started ({config['entrypoint']})")

    result = current_run_payload()
    result["message"] = "Native run: " + "; ".join(messages or ["nothing to start"])
    EVENTS.publish("run_state", result)
    return result


def _stop_native_run(target_services: list[str]) -> dict[str, Any]:
    with STATE.lock:
        procs = dict(STATE.native_procs)
        generated = STATE.generated
    entrypoints: dict[str, str] = {}
    for config in list((generated or {}).get("configs") or []):
        entrypoints[_native_service_name(config["host_id"])] = config["entrypoint"]

    targets = [
        name for name in procs
        if not target_services or name in target_services
    ]
    # Ordered shutdown: monitors stop publishing first so runners can drain
    # in-flight records; the broker goes down last.
    order = {"monitor_node": 0, "node_runner": 1}
    targets.sort(key=lambda name: (2 if name == "mosquitto" else order.get(entrypoints.get(name, ""), 1), name))

    messages: list[str] = []
    for name in targets:
        process = procs[name]
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        with STATE.lock:
            STATE.native_procs.pop(name, None)
        messages.append(f"{name}: stopped")
        _lan_log(f"{name}: stopped")
    if "mosquitto" in target_services and "mosquitto" not in procs:
        message = "mosquitto: external broker, not managed by the WebUI; left running"
        messages.append(message)
        _lan_log(message)
    with STATE.lock:
        if not STATE.native_procs:
            STATE.native_started_at = None
    result = current_run_payload()
    result["message"] = "; ".join(messages) if messages else "No native runtime matched."
    EVENTS.publish("run_state", result)
    return result


def start_generated_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    target_services = [str(item) for item in list(payload.get("target_services") or [])]
    generated_payload = None
    if payload:
        generated_payload = generate_configs(payload)
    with STATE.lock:
        generated = STATE.generated
    if generated is None:
        raise RuntimeError("Configure monitor sources before starting the monitor.")

    if generated.get("lan"):
        return _start_lan_run(generated, target_services, generated_payload)

    result = _start_native_run(generated, target_services)
    if generated_payload is not None:
        result["generated_files"] = generated_payload
    return result


def _stop_lan_remote(target_services: list[str]) -> list[str]:
    registry = lan_mode.load_registry()
    with STATE.lock:
        deployed = dict(STATE.lan_deployed)
        generated = STATE.generated
    remote_info = dict(((generated or {}).get("lan") or {}).get("remote") or {})
    if target_services:
        targets = [
            host_id for host_id in deployed
            if _native_service_name(host_id) in target_services
        ]
    else:
        targets = list(deployed)
    # Monitors stop first so runners can drain in-flight records.
    targets.sort(
        key=lambda hid: 0
        if remote_info.get(hid, {}).get("entrypoint") == "monitor_node"
        else 1
    )
    messages: list[str] = []
    for host_id in targets:
        with STATE.lock:
            proc = STATE.lan_log_procs.pop(host_id, None)
        host = registry.get(host_id)
        pattern = f"generated/showcase/{deployed[host_id]}"
        if host is not None:
            try:
                lan_mode.remote_signal(host, pattern, "INT")
                if proc is not None:
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        lan_mode.remote_signal(host, pattern, "KILL")
                # Final pull so verdicts emitted just before shutdown survive.
                lan_mode.pull_outputs(host)
            except Exception as ex:
                messages.append(f"{host_id}: stop failed ({ex})")
                if proc is not None:
                    _stop_log_process(proc)
                with STATE.lock:
                    STATE.lan_deployed.pop(host_id, None)
                continue
        if proc is not None:
            _stop_log_process(proc)
        with STATE.lock:
            STATE.lan_deployed.pop(host_id, None)
        messages.append(f"{host_id}: stopped")
        _lan_log(f"[lan] {host_id}: stopped")
    with STATE.lock:
        none_left = not STATE.lan_deployed
    if none_left and _LAN_PULL_STOP is not None:
        _LAN_PULL_STOP.set()
    return messages


def _stop_lan_broker() -> list[str]:
    with STATE.lock:
        broker = STATE.lan_broker
        STATE.lan_broker = None
    if not broker:
        return []
    host = lan_mode.load_registry().get(str(broker.get("host_id")))
    if host is not None:
        try:
            lan_mode.remote_signal(host, "mosquitto_native.conf", "TERM")
        except Exception:
            pass
    proc = broker.get("process")
    if proc is not None:
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            pass
        _stop_log_process(proc)
    message = f"mosquitto: stopped on {broker.get('host_id')}"
    _lan_log(message)
    return [message]


def stop_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    target_services = [str(item) for item in list(payload.get("target_services") or [])]
    with STATE.lock:
        has_lan = bool(STATE.lan_deployed)
        has_native = bool(STATE.native_procs)
        has_lan_broker = STATE.lan_broker is not None
    messages: list[str] = []
    # Remote monitors first, then the local runtimes (their own order ends
    # with a local broker), then a remotely started broker last of all.
    if has_lan:
        messages.extend(_stop_lan_remote(target_services))
    if has_native:
        native_result = _stop_native_run(target_services)
        message = str(native_result.get("message") or "")
        if message and "No native runtime matched" not in message:
            messages.append(message)
    if has_lan_broker and (not target_services or "mosquitto" in target_services):
        messages.extend(_stop_lan_broker())
    if not messages:
        return {"running": False, "message": "No monitor run is active."}
    result = current_run_payload()
    result["message"] = "; ".join(part for part in messages if part)
    EVENTS.publish("run_state", result)
    return result


def recent_verdicts(limit: int = 50) -> list[dict[str, Any]]:
    verdicts: list[dict[str, Any]] = []
    for path in _verdict_jsonl_paths():
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
            EVENTS.publish("verdicts", {"verdicts": recent_verdicts(limit=50)})


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
            self._write_sse("mode", mode_payload())
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
            if parsed.path == "/api/runs/current":
                return self._send_json(current_run_payload())
            if parsed.path == "/api/verdicts":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                return self._send_json({"verdicts": recent_verdicts(limit=limit)})
            if parsed.path == "/api/plugins":
                return self._send_json(plugin_payload())
            if parsed.path == "/api/mode":
                return self._send_json(mode_payload())
            if parsed.path == "/api/lan/hosts":
                return self._send_json(lan_mode.registry_payload())
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
            if self.path == "/api/mode":
                return self._send_json(set_mode(payload))
            if self.path == "/api/lan/hosts":
                return self._send_json(lan_mode.create_host(payload))
            if self.path == "/api/lan/hosts/delete":
                return self._send_json(lan_mode.delete_host(str(payload.get("id") or "")))
            if self.path == "/api/lan/hosts/sync":
                host = lan_mode.load_registry().get(str(payload.get("id") or ""))
                if host is None:
                    raise ValueError("Unknown LAN host.")
                lan_mode.sync_project(host)
                return self._send_json({"synced": True, "id": host["id"]})
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
