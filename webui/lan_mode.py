"""LAN mode support for the showcase server.

Hosts are machines reachable over SSH on the local network. A host is
created by validating an SSH connection (installing the local public key
first when a password is required), probing its OS/home/python, and
persisting it in a JSON registry. Deployment pushes a copy of the project
to `~/ROS2-Monitor-Infra` on the host with rsync and runs the generated
runtimes there natively under live SSH sessions (the machines run the
monitor stack directly — no Docker involved; this mirrors the thesis E5
deployment and macOS 15 additionally requires a live SSH session for LAN
TCP from remotely started processes)."""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "generated" / "lan_hosts.json"
REMOTE_PROJECT_DIR = "ROS2-Monitor-Infra"
LOCAL_HOST_ID = "local"

SSH_BATCH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "StrictHostKeyChecking=accept-new",
]
# Non-interactive SSH shells (notably zsh on macOS) miss Homebrew's PATH.
REMOTE_PATH_EXPORT = (
    'export PATH="/usr/local/bin:/opt/homebrew/bin:'
    '/usr/bin:/bin:/usr/sbin:/sbin:$PATH"'
)
SYNC_EXCLUDES = [
    ".git",
    ".venv",
    ".vscode",
    ".pytest_cache",
    ".claude",
    ".codex",
    ".agents",
    "__pycache__",
    "output",
    "Thesis",
    "*.cast",
    ".DS_Store",
]

_REGISTRY_LOCK = threading.Lock()
_ADDRESS_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+$")


def lan_ip() -> str:
    """Best-effort LAN address of this machine, for the shared MQTT broker."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def load_registry() -> dict[str, dict[str, Any]]:
    with _REGISTRY_LOCK:
        if not REGISTRY_PATH.exists():
            return {}
        try:
            data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): dict(v) for k, v in dict(data).items()}


def _save_registry(registry: dict[str, dict[str, Any]]) -> None:
    with _REGISTRY_LOCK:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def registry_payload() -> dict[str, Any]:
    return {"hosts": list(load_registry().values()), "lan_ip": lan_ip()}


def _host_id_for_address(address: str, registry: dict[str, dict[str, Any]]) -> str:
    hostname = address.split("@", 1)[-1]
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", hostname).strip("_").lower() or "lanhost"
    if base == LOCAL_HOST_ID:
        base = f"{base}_ssh"
    host_id = base
    suffix = 2
    while host_id in registry:
        host_id = f"{base}_{suffix}"
        suffix += 1
    return host_id


def ssh_run(
    address: str,
    command: str,
    timeout: int = 30,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", *SSH_BATCH_OPTS, address, command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        input=input_text,
        check=False,
    )


def _local_public_key() -> str:
    ssh_dir = Path.home() / ".ssh"
    for name in ("id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"):
        path = ssh_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    generated = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(ssh_dir / "id_ed25519")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    if generated.returncode != 0:
        raise RuntimeError(f"ssh-keygen failed: {generated.stdout.strip()}")
    return (ssh_dir / "id_ed25519.pub").read_text(encoding="utf-8").strip()


def _install_key_with_password(address: str, password: str) -> None:
    """Append the local public key to the host's authorized_keys.

    The password is fed to ssh through a one-shot SSH_ASKPASS helper so no
    extra dependency (sshpass/paramiko) is needed.
    """
    public_key = _local_public_key()
    fd, askpass_path = tempfile.mkstemp(prefix="lan_askpass_", suffix=".sh")
    try:
        os.write(fd, f"#!/bin/sh\nprintf '%s' {shlex.quote(password)}\n".encode("utf-8"))
        os.close(fd)
        os.chmod(askpass_path, 0o700)
        env = dict(os.environ)
        env["SSH_ASKPASS"] = askpass_path
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env.setdefault("DISPLAY", ":0")
        install_command = (
            'key="$(cat)"; mkdir -p ~/.ssh && chmod 700 ~/.ssh; '
            "touch ~/.ssh/authorized_keys; "
            'grep -qxF "$key" ~/.ssh/authorized_keys || '
            'printf "%s\\n" "$key" >> ~/.ssh/authorized_keys; '
            "chmod 600 ~/.ssh/authorized_keys"
        )
        completed = subprocess.run(
            [
                "ssh",
                "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "NumberOfPasswordPrompts=1",
                address,
                install_command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            input=public_key + "\n",
            env=env,
            start_new_session=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"SSH key install failed: {detail or 'unknown error'}")
    finally:
        try:
            os.unlink(askpass_path)
        except OSError:
            pass


def _probe_host(address: str) -> dict[str, Any]:
    # python3.12 first: on the prepared macOS host the Homebrew 3.12 carries
    # paho/PyYAML while the system python3 has neither.
    probe = ssh_run(
        address,
        f'{REMOTE_PATH_EXPORT}; uname -s; printf "%s\\n" "$HOME"; '
        "command -v python3.12 || command -v python3 || echo MISSING",
        timeout=20,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip()
        raise RuntimeError(f"SSH probe failed: {detail or 'unknown error'}")
    lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
    if len(lines) < 3:
        raise RuntimeError(f"SSH probe returned unexpected output: {probe.stdout!r}")
    os_name = {"linux": "linux", "darwin": "darwin"}.get(lines[0].lower(), lines[0].lower())
    home = lines[1]
    python = "" if lines[2] == "MISSING" else lines[2]
    return {"os": os_name, "home": home, "python": python}


def create_host(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate SSH access to `address` and register the host.

    Returns {"needs_password": True} when key auth fails and no password was
    supplied; otherwise the created host record (or an existing one for the
    same address, re-probed).
    """
    address = str(payload.get("address") or "").strip()
    password = str(payload.get("password") or "")
    if not address or not _ADDRESS_RE.match(address):
        raise ValueError("Provide an SSH address such as user@hostname.local.")

    key_check = ssh_run(address, "true", timeout=20)
    if key_check.returncode != 0:
        if not password:
            detail = (key_check.stderr or key_check.stdout).strip().splitlines()
            return {
                "needs_password": True,
                "detail": detail[-1] if detail else "Key authentication failed.",
            }
        _install_key_with_password(address, password)
        key_check = ssh_run(address, "true", timeout=20)
        if key_check.returncode != 0:
            detail = (key_check.stderr or key_check.stdout).strip()
            raise RuntimeError(
                f"SSH still fails after installing the key: {detail or 'unknown error'}"
            )

    probed = _probe_host(address)
    registry = load_registry()
    existing_id = next(
        (hid for hid, row in registry.items() if row.get("address") == address), None
    )
    host_id = existing_id or _host_id_for_address(address, registry)
    host = {
        "id": host_id,
        "address": address,
        "status": "ready" if probed["python"] else "no_python",
        "synced": bool(registry.get(host_id, {}).get("synced")),
        **probed,
    }
    registry[host_id] = host
    _save_registry(registry)
    return {"host": host}


def delete_host(host_id: str) -> dict[str, Any]:
    registry = load_registry()
    removed = registry.pop(str(host_id), None)
    _save_registry(registry)
    return {"removed": bool(removed), "hosts": list(registry.values())}


def _remote_project(host: dict[str, Any]) -> str:
    return f'{host["home"]}/{REMOTE_PROJECT_DIR}'


def sync_project(host: dict[str, Any], timeout: int = 300) -> None:
    """Push a copy of the project to `~/ROS2-Monitor-Infra` on the host."""
    excludes = [f"--exclude={pattern}" for pattern in SYNC_EXCLUDES]
    command = [
        "rsync",
        "-az",
        "--delete",
        *excludes,
        "-e", "ssh " + " ".join(SSH_BATCH_OPTS),
        f"{ROOT}/",
        f'{host["address"]}:{REMOTE_PROJECT_DIR}/',
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f'Project sync to {host["address"]} failed: '
            f"{completed.stdout.strip() or 'rsync error'}"
        )
    registry = load_registry()
    if host["id"] in registry:
        registry[host["id"]]["synced"] = True
        _save_registry(registry)


def pull_outputs(host: dict[str, Any], timeout: int = 60) -> None:
    """Pull verdict/output files back so the local watcher can stream them."""
    (ROOT / "output" / "showcase").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "rsync",
            "-az",
            "-e", "ssh " + " ".join(SSH_BATCH_OPTS),
            f'{host["address"]}:{REMOTE_PROJECT_DIR}/output/showcase/',
            str(ROOT / "output" / "showcase") + "/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def remote_native_process(
    host: dict[str, Any], command: str
) -> subprocess.Popen[str]:
    """Run `command` in the remote project root under a live SSH session.

    The runtime stays a child of this session: its output streams back as
    the session's stdout, macOS 15 Local Network privacy keeps allowing LAN
    TCP (it silently blocks orphaned detached processes), and `-tt` forces
    a TTY so the remote process group is hung up if the session dies.
    """
    project = _remote_project(host)
    full = f"{REMOTE_PATH_EXPORT}; cd {shlex.quote(project)} && {{ {command}; }}"
    return subprocess.Popen(
        ["ssh", "-tt", *SSH_BATCH_OPTS, host["address"], full],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def remote_signal(
    host: dict[str, Any], pattern: str, sig: str = "INT"
) -> subprocess.CompletedProcess[str]:
    """Signal remote processes whose command line matches `pattern`."""
    return ssh_run(
        host["address"], f"pkill -{sig} -f {shlex.quote(pattern)}", timeout=20
    )
