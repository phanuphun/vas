from __future__ import annotations

import json
import subprocess

from fastmcp import FastMCP

mcp = FastMCP("vas-docker")


@mcp.tool()
def get_docker_status(include_logs: bool = False, log_lines: int = 50) -> dict:
    """สถานะ Docker daemon และ containers ทั้งหมด"""
    try:
        log_lines = min(max(1, log_lines), 500)
        daemon_running = _check_daemon()
        if not daemon_running:
            return {"daemon_running": False, "containers": []}

        containers = _list_containers(include_logs=include_logs, log_lines=log_lines)
        return {"daemon_running": True, "containers": containers}
    except Exception as e:
        return {"error": str(e)}


def _check_daemon() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _list_containers(include_logs: bool, log_lines: int) -> list[dict]:
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue

        container_id = raw.get("ID", "")
        restart_count = _get_restart_count(container_id)
        logs = _get_logs(container_id, log_lines) if include_logs else None

        entry: dict = {
            "id": container_id,
            "name": raw.get("Names", ""),
            "image": raw.get("Image", ""),
            "status": raw.get("Status", ""),
            "running": (raw.get("State", "") == "running"),
            "restart_count": restart_count,
            "ports": [p.strip() for p in raw.get("Ports", "").split(",") if p.strip()],
        }
        if include_logs:
            entry["logs"] = logs
        containers.append(entry)

    return containers


def _get_restart_count(container_id: str) -> int:
    if not container_id:
        return 0
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.RestartCount}}", container_id],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return int(result.stdout.strip()) if result.returncode == 0 else 0
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return 0


def _get_logs(container_id: str, tail: int) -> str | None:
    if not container_id:
        return None
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), container_id],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return (result.stdout + result.stderr).strip() or None
    except (subprocess.TimeoutExpired, OSError):
        return None
