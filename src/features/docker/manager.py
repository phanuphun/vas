"""
VAS — Docker Engine management (containers, images, networks, volumes, compose, swarm)

สถาปัตยกรรมตาม pattern เดียวกับ features/wireguard/manager.py และ features/remote/anydesk.py:
- Read-only "collect_*" queries ใช้ subprocess ตรง (มี timeout กันค้าง ไม่ผ่าน CommandRunner
  เพราะ CommandRunner.run() ไม่รองรับ timeout — สำคัญมากสำหรับ query ที่รันตอนโหลดหน้าเว็บ)
- "Action" (start/stop/remove/prune/swarm ฯลฯ) ใช้ CommandRunner ตาม convention เดิม
  (print_operation/dry_run) เหมือน WireGuardManager/anydesk.service_action
- dev_fake_installed() ใช้จำลองผล "สำเร็จ" บนเครื่อง dev ที่ไม่มี docker daemon จริง
  (ตาม pattern เดียวกับ anydesk.service_action)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.runner import CommandResult, CommandRunner
from system.utils import dev_fake_installed

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows dev hosts
    pwd_module = None  # type: ignore[assignment]

DAEMON_JSON_PATH = Path("/etc/docker/daemon.json")
_TIMEOUT = 10  # วินาที — กัน request ค้างถ้า docker daemon ไม่ตอบสนอง

VALID_CONTAINER_ACTIONS = ("start", "stop", "restart", "pause", "unpause")
VALID_NODE_AVAILABILITY = ("active", "pause", "drain")


# ══════════════════════════════════════════════════════════════════
#  Low-level subprocess helpers (read-only, timeout-bound)
# ══════════════════════════════════════════════════════════════════

def is_docker_installed() -> bool:
    return dev_fake_installed() or shutil.which("docker") is not None


def _run_text(args: list[str], timeout: int = _TIMEOUT) -> str | None:
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _run_json(args: list[str], timeout: int = _TIMEOUT) -> Any | None:
    out = _run_text(args, timeout=timeout)
    if out is None or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _run_json_lines(args: list[str], timeout: int = _TIMEOUT) -> list[dict[str, Any]]:
    """รันคำสั่งที่ใช้ --format '{{json .}}' (หนึ่ง JSON object ต่อบรรทัด) คืน [] ถ้า error/timeout"""
    out = _run_text(args, timeout=timeout)
    if out is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _parse_size_to_bytes(size: str) -> float:
    """แปลง docker size string เช่น '6.4GB', '890MB', '0B' เป็น bytes (best-effort)"""
    size = (size or "").strip()
    if not size:
        return 0.0
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for unit in ("TB", "GB", "MB", "KB", "B"):
        if size.upper().endswith(unit):
            num = size[: -len(unit)].strip()
            try:
                return float(num) * units[unit]
            except ValueError:
                return 0.0
    return 0.0


# ══════════════════════════════════════════════════════════════════
#  Status collection (ใช้โดย GET /docker route)
# ══════════════════════════════════════════════════════════════════

def _empty_status(installed: bool, daemon_running: bool = False) -> dict[str, Any]:
    return {
        "is_mock": False,
        "docker": {
            "daemon_running": daemon_running,
            "installed": installed,
            "version": None, "api_version": None, "os_arch": None, "kernel": None,
            "storage_driver": None, "logging_driver": None, "cgroup_driver": None,
            "root_dir": None, "containers_running": 0, "containers_total": 0,
            "disk": {
                "images": {"count": 0, "size": "0 B", "pct": 0},
                "containers": {"count": 0, "size": "0 B", "pct": 0},
                "volumes": {"count": 0, "size": "0 B", "pct": 0},
                "build_cache": {"size": "0 B", "pct": 0},
            },
        },
        "containers": [], "images": [], "networks": [], "volumes": [], "compose_projects": [],
        "swarm": {"active": False, "role": None},
        "daemon_json_exists": DAEMON_JSON_PATH.exists(),
        "daemon_json_content": _read_daemon_json_text(),
        "daemon_flags": _collect_daemon_flags(None),
    }


def collect_docker_status() -> dict[str, Any]:
    """รวบรวมสถานะ Docker Engine ทั้งหมดสำหรับหน้า /docker — คืนโครงสร้าง dict เดียวกับที่
    docker.html คาดหวัง (เดิมมาจาก _collect_docker_status_mock ใน server.py)"""
    if not is_docker_installed():
        return _empty_status(installed=False)

    info = _run_json(["docker", "info", "--format", "{{json .}}"])
    if info is None:
        return _empty_status(installed=True, daemon_running=False)

    version = _run_json(["docker", "version", "--format", "{{json .}}"]) or {}
    server_version_info = (version.get("Server") or {}) if isinstance(version, dict) else {}

    docker_info = {
        "daemon_running": True,
        "installed": True,
        "version": info.get("ServerVersion") or server_version_info.get("Version"),
        "api_version": server_version_info.get("ApiVersion"),
        "os_arch": f"{info.get('OSType', 'linux')}/{info.get('Architecture', '')} · {info.get('OperatingSystem', '')}".strip(" ·"),
        "kernel": info.get("KernelVersion"),
        "storage_driver": info.get("Driver"),
        "logging_driver": info.get("LoggingDriver"),
        "cgroup_driver": info.get("CgroupDriver"),
        "root_dir": info.get("DockerRootDir"),
        "containers_running": info.get("ContainersRunning", 0),
        "containers_total": info.get("Containers", 0),
        "disk": _collect_disk_usage(),
    }

    return {
        "is_mock": False,
        "docker": docker_info,
        "containers": _collect_containers(),
        "images": _collect_images(),
        "networks": _collect_networks(),
        "volumes": _collect_volumes(),
        "compose_projects": _collect_compose_projects(),
        "swarm": _collect_swarm(info),
        "daemon_json_exists": DAEMON_JSON_PATH.exists(),
        "daemon_json_content": _read_daemon_json_text(),
        "daemon_flags": _collect_daemon_flags(info),
    }


def _collect_disk_usage() -> dict[str, Any]:
    # `docker system df` (ไม่ใส่ -v) พิมพ์ 1 JSON object ต่อบรรทัดต่อ Type (Images/Containers/
    # Local Volumes/Build Cache) — ไม่ใช่ JSON object เดียว จึงใช้ _run_json_lines แทน _run_json
    rows = _run_json_lines(["docker", "system", "df", "--format", "{{json .}}"])
    by_type: dict[str, dict[str, Any]] = {row.get("Type", ""): row for row in rows}

    def _entry(type_name: str) -> dict[str, Any]:
        row = by_type.get(type_name, {})
        size_str = row.get("Size", "0B") or "0B"
        count_raw = row.get("TotalCount") or row.get("Total") or "0"
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            count = 0
        return {"count": count, "size": size_str, "_bytes": _parse_size_to_bytes(size_str)}

    images = _entry("Images")
    containers = _entry("Containers")
    volumes = _entry("Local Volumes")
    build_cache = _entry("Build Cache")

    total_bytes = images["_bytes"] + containers["_bytes"] + volumes["_bytes"] + build_cache["_bytes"]

    def _pct(entry: dict[str, Any]) -> int:
        if total_bytes <= 0:
            return 0
        return round(entry["_bytes"] / total_bytes * 100)

    for entry in (images, containers, volumes, build_cache):
        entry["pct"] = _pct(entry)
        entry.pop("_bytes", None)
    build_cache.pop("count", None)

    return {"images": images, "containers": containers, "volumes": volumes, "build_cache": build_cache}


def _collect_containers() -> list[dict[str, Any]]:
    rows = _run_json_lines(["docker", "ps", "-a", "--format", "{{json .}}"])
    if not rows:
        return []

    ids = [r.get("ID", "") for r in rows if r.get("ID")]
    inspects = _run_json(["docker", "inspect", *ids]) if ids else []
    inspect_by_id = {i.get("Id", "")[:12]: i for i in (inspects or [])}

    running_ids = [r.get("ID", "") for r in rows if r.get("State") == "running"]
    stats_rows = _run_json_lines(["docker", "stats", "--no-stream", "--format", "{{json .}}", *running_ids]) if running_ids else []
    stats_by_id = {s.get("ID", ""): s for s in stats_rows}

    containers: list[dict[str, Any]] = []
    for row in rows:
        cid = row.get("ID", "")
        state = row.get("State", "")
        inspect = inspect_by_id.get(cid, {})
        host_config = inspect.get("HostConfig", {}) or {}
        restart_policy = (host_config.get("RestartPolicy") or {}).get("Name") or "no"
        networks = (inspect.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
        network_label = ", ".join(networks.keys()) or "—"
        mounts = inspect.get("Mounts", []) or []
        volumes_label = ", ".join(
            f"{m.get('Name') or m.get('Source', '')}:{m.get('Destination', '')}" for m in mounts
        )
        stat = stats_by_id.get(cid, {})

        status_raw = row.get("Status", "")
        status_label = status_raw.upper() if state != "running" else "RUNNING"
        if state == "restarting":
            status_label = "RESTARTING"

        containers.append({
            "id": cid,
            "name": row.get("Names", ""),
            "image": row.get("Image", ""),
            "state": state,
            "status_label": status_label,
            "uptime": status_raw,
            "cpu_pct": (stat.get("CPUPerc") or "0%").rstrip("%"),
            "mem_used": (stat.get("MemUsage") or "— / —").split(" / ")[0].strip(),
            "mem_limit": (stat.get("MemUsage") or "— / —").split(" / ")[-1].strip(),
            "ports": row.get("Ports", ""),
            "network": network_label,
            "volumes": volumes_label,
            "restart_policy": restart_policy,
            "restart_count": inspect.get("RestartCount", 0),
        })
    return containers


def _collect_images() -> list[dict[str, Any]]:
    rows = _run_json_lines(["docker", "image", "ls", "--format", "{{json .}}"])
    containers = _run_json_lines(["docker", "ps", "-a", "--format", "{{json .}}"])
    used_images = {c.get("Image", "") for c in containers}

    images: list[dict[str, Any]] = []
    for row in rows:
        repo = row.get("Repository", "<none>")
        tag = row.get("Tag", "<none>")
        ref = f"{repo}:{tag}"
        images.append({
            "repo": repo,
            "tag": tag,
            "id": row.get("ID", ""),
            "size": row.get("Size", ""),
            "created": row.get("CreatedSince", ""),
            "used": ref in used_images or row.get("ID", "") in used_images,
            "dangling": repo == "<none>",
        })
    return images


def _collect_networks() -> list[dict[str, Any]]:
    rows = _run_json_lines(["docker", "network", "ls", "--format", "{{json .}}"])
    networks: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("Name", "")
        detail_inspect = _run_json(["docker", "network", "inspect", name]) or []
        info = detail_inspect[0] if detail_inspect else {}
        ipam_configs = ((info.get("IPAM") or {}).get("Config") or [])
        subnet = ipam_configs[0].get("Subnet") if ipam_configs else None
        container_count = len(info.get("Containers") or {})
        detail_parts = []
        if subnet:
            detail_parts.append(f"Subnet {subnet}")
        detail_parts.append(f"{container_count} containers เชื่อมต่อ")
        networks.append({
            "name": name,
            "driver": row.get("Driver", ""),
            "scope": row.get("Scope", ""),
            "attachable": bool(info.get("Attachable", False)),
            "detail": " · ".join(detail_parts),
        })
    return networks


def _collect_volumes() -> list[dict[str, Any]]:
    rows = _run_json_lines(["docker", "volume", "ls", "--format", "{{json .}}"])
    df_v = _run_json(["docker", "system", "df", "-v", "--format", "{{json .}}"])
    size_by_name: dict[str, str] = {}
    if isinstance(df_v, dict):
        for v in (df_v.get("Volumes") or []):
            if v.get("Name"):
                size_by_name[v["Name"]] = v.get("Size", "—")

    volumes: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("Name", "")
        inspect = _run_json(["docker", "volume", "inspect", name]) or []
        info = inspect[0] if inspect else {}
        containers_using = _run_json_lines([
            "docker", "ps", "-a", "--filter", f"volume={name}", "--format", "{{json .}}",
        ])
        used_by = f"{len(containers_using)} container" if containers_using else None
        volumes.append({
            "name": name,
            "mountpoint": info.get("Mountpoint", ""),
            "size": size_by_name.get(name, "—"),
            "used_by": used_by,
        })
    return volumes


def default_compose_root() -> Path:
    """~/.config/vending-auto-setup/docker/compose/<project>/compose.yaml — เก็บ compose
    projects ที่ VAS จัดการ (ตาม pattern เดียวกับ wireguard.manager.default_store_dir())"""
    home = _sudo_user_home() or Path.home()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else home / ".config"
    return root / "vending-auto-setup" / "docker" / "compose"


def _sudo_user_home() -> Path | None:
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user or sudo_user == "root" or pwd_module is None:
        return None
    try:
        return Path(pwd_module.getpwnam(sudo_user).pw_dir)
    except KeyError:
        return None


def compose_project_path(name: str) -> Path:
    safe = _sanitize_name(name)
    return default_compose_root() / safe / "compose.yaml"


def _collect_compose_projects() -> list[dict[str, Any]]:
    root = default_compose_root()
    # หมายเหตุ: `docker compose ls --format json` (compose v2 plugin) คืน JSON array เดียว
    # ไม่ใช่ newline-delimited JSON เหมือน `docker ps/images --format '{{json .}}'` (go-template
    # ของ core CLI) — ต้อง parse ด้วย _run_json ไม่ใช่ _run_json_lines
    running_raw = _run_json(["docker", "compose", "ls", "--format", "json"])
    running_list = running_raw if isinstance(running_raw, list) else []
    running = {row.get("Name", ""): row for row in running_list if isinstance(row, dict)}

    projects: list[dict[str, Any]] = []
    if root.exists():
        for project_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            compose_file = project_dir / "compose.yaml"
            if not compose_file.exists():
                continue
            name = project_dir.name
            run_info = running.get(name, {})
            status = run_info.get("Status", "")
            services_running = 0
            services_total = 0
            if "/" in status:
                try:
                    services_running, services_total = (int(x) for x in status.split("(")[0].split("/")[:2])
                except (ValueError, IndexError):
                    pass
            try:
                content = compose_file.read_text(encoding="utf-8")
            except OSError:
                content = ""
            projects.append({
                "name": name,
                "path": compose_file.as_posix(),
                "up": name in running,
                "services_running": services_running,
                "services_total": services_total or content.count("\n    image:") or 1,
                "compose_yaml": content,
            })
    return projects


def _collect_swarm(info: dict[str, Any]) -> dict[str, Any]:
    swarm_info = info.get("Swarm") or {}
    local_state = swarm_info.get("LocalNodeState", "inactive")
    if local_state != "active":
        return {"active": False, "role": None}

    is_manager = bool(swarm_info.get("ControlAvailable"))
    cluster = swarm_info.get("Cluster") or {}

    nodes: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    stacks: list[dict[str, Any]] = []
    worker_token = ""
    manager_token = ""
    advertise_addr = swarm_info.get("NodeAddr", "")

    if is_manager:
        node_rows = _run_json_lines(["docker", "node", "ls", "--format", "{{json .}}"])
        for n in node_rows:
            # `docker node ls` ไม่มี field role ตรงๆ — ManagerStatus ไม่ว่าง = manager,
            # ว่าง = worker; "Leader" ปรากฏใน ManagerStatus เฉพาะ node ที่เป็น leader จริง
            manager_status = (n.get("ManagerStatus") or "").strip()
            node_id = n.get("ID", "").rstrip(" *")  # docker ls ใส่ "*" ต่อท้าย ID ของ node ปัจจุบัน
            address = _run_text(["docker", "node", "inspect", "--format", "{{.Status.Addr}}", node_id]) if node_id else None
            nodes.append({
                "hostname": n.get("Hostname", ""),
                "role": "manager" if manager_status else "worker",
                "leader": "Leader" in manager_status,
                "status": n.get("Status", ""),
                "availability": n.get("Availability", ""),
                "address": (address or "").strip() or n.get("Hostname", ""),
                "engine_version": n.get("EngineVersion", ""),
                "is_self": bool(n.get("Self")),
                "note": None,
            })

        service_rows = _run_json_lines(["docker", "service", "ls", "--format", "{{json .}}"])
        for s in service_rows:
            replicas = s.get("Replicas", "0/0")
            running_n, desired_n = 0, 0
            if "/" in replicas:
                try:
                    running_n, desired_n = (int(x) for x in replicas.split("/")[:2])
                except ValueError:
                    pass
            services.append({
                "name": s.get("Name", ""),
                "mode": s.get("Mode", "replicated"),
                "replicas_running": running_n,
                "replicas_desired": desired_n,
                "image": s.get("Image", ""),
                "ports": s.get("Ports") or None,
            })

        stack_rows = _run_json_lines(["docker", "stack", "ls", "--format", "{{json .}}"])
        for st in stack_rows:
            stacks.append({
                "name": st.get("Name", ""),
                "services_count": st.get("Services", 0),
                "path": (compose_project_path(st.get("Name", "")).as_posix()),
            })

        worker_token = _run_text(["docker", "swarm", "join-token", "-q", "worker"]) or ""
        manager_token = _run_text(["docker", "swarm", "join-token", "-q", "manager"]) or ""
        worker_token = worker_token.strip()
        manager_token = manager_token.strip()

    return {
        "active": True,
        "role": "manager" if is_manager else "worker",
        "is_leader": any(n["leader"] for n in nodes) if nodes else is_manager,
        "cluster_id": cluster.get("ID", ""),
        "advertise_addr": f"{advertise_addr}:2377" if advertise_addr else "",
        "worker_token": worker_token,
        "manager_token": manager_token,
        "nodes": nodes,
        "services": services,
        "stacks": stacks,
    }


def _read_daemon_json_text() -> str:
    try:
        if DAEMON_JSON_PATH.exists():
            return DAEMON_JSON_PATH.read_text(encoding="utf-8")
    except OSError:
        pass
    return "{\n  \n}\n"


def _collect_daemon_flags(info: dict[str, Any] | None) -> list[tuple[str, str, bool, str | None]]:
    enabled_result = subprocess.run(
        ["systemctl", "is-enabled", "docker"], text=True, capture_output=True, timeout=5, check=False,
    ) if shutil.which("systemctl") else None
    active_result = subprocess.run(
        ["systemctl", "is-active", "docker"], text=True, capture_output=True, timeout=5, check=False,
    ) if shutil.which("systemctl") else None
    enabled = bool(enabled_result and enabled_result.returncode == 0)
    active = bool(active_result and active_result.returncode == 0)

    daemon_json_text = _read_daemon_json_text()
    try:
        daemon_json = json.loads(daemon_json_text) if daemon_json_text.strip() else {}
    except json.JSONDecodeError:
        daemon_json = {}
    live_restore = bool(daemon_json.get("live-restore", False))
    buildkit_features = (daemon_json.get("features") or {})
    buildkit = bool(buildkit_features.get("buildkit", True))

    return [
        ("Docker daemon service", "systemd unit: docker.service — เปิดใช้ตอนบูตเครื่อง", enabled and active,
         f"{'enabled' if enabled else 'disabled'} · {'active' if active else 'inactive'}"),
        ("Rootless mode", "รัน Docker daemon โดยไม่ใช้สิทธิ์ root (ตรวจจาก /etc/docker/daemon.json เท่านั้น — ไม่ครอบคลุม rootless install แยกต่างหาก)", False, None),
        ("BuildKit", "ใช้ BuildKit engine สำหรับ docker build", buildkit, None),
        ("Live restore", "Container ยังรันต่อได้แม้ daemon restart", live_restore, None),
    ]


def _sanitize_name(name: str) -> str:
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name or ""):
        raise ValueError("ชื่อไม่ถูกต้อง — ใช้ได้เฉพาะตัวอักษร ตัวเลข จุด ขีดล่าง ขีดกลาง")
    return name


# ══════════════════════════════════════════════════════════════════
#  Actions (mutating — ใช้ CommandRunner ตาม convention เดิม)
# ══════════════════════════════════════════════════════════════════

def _fake_ok(*args: str) -> CommandResult:
    return CommandResult(args=tuple(args), returncode=0, stdout="", stderr="")


def container_action(runner: CommandRunner, name: str, action: str) -> CommandResult:
    if action not in VALID_CONTAINER_ACTIONS:
        raise ValueError(f"Unknown container action: {action}")
    if dev_fake_installed():
        return _fake_ok("docker", action, name)
    return runner.run(["docker", action, name], check=False)


def remove_container(runner: CommandRunner, name: str, force: bool = False) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "rm", name)
    args = ["docker", "rm"]
    if force:
        args.append("-f")
    args.append(name)
    return runner.run(args, check=False)


def get_container_logs(name: str, tail: int = 200) -> str:
    tail = min(max(1, tail), 2000)
    out = _run_text(["docker", "logs", "--tail", str(tail), name], timeout=15)
    return out or "(ไม่มี log หรือไม่สามารถอ่านได้)"


def pull_image(runner: CommandRunner, ref: str) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "pull", ref)
    return runner.run(["docker", "pull", ref], check=False)


def remove_image(runner: CommandRunner, ref: str, force: bool = False) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "rmi", ref)
    args = ["docker", "rmi"]
    if force:
        args.append("-f")
    args.append(ref)
    return runner.run(args, check=False)


def prune_images(runner: CommandRunner) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "image", "prune", "-f")
    return runner.run(["docker", "image", "prune", "-f"], check=False)


def create_network(runner: CommandRunner, name: str, driver: str = "bridge") -> CommandResult:
    _sanitize_name(name)
    if dev_fake_installed():
        return _fake_ok("docker", "network", "create", name)
    return runner.run(["docker", "network", "create", "--driver", driver, name], check=False)


def create_volume(runner: CommandRunner, name: str) -> CommandResult:
    _sanitize_name(name)
    if dev_fake_installed():
        return _fake_ok("docker", "volume", "create", name)
    return runner.run(["docker", "volume", "create", name], check=False)


def prune_volumes(runner: CommandRunner) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "volume", "prune", "-f")
    return runner.run(["docker", "volume", "prune", "-f"], check=False)


def system_prune(runner: CommandRunner) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "system", "prune", "-f")
    return runner.run(["docker", "system", "prune", "-f"], check=False)


def restart_daemon(runner: CommandRunner) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("systemctl", "restart", "docker")
    return runner.run(["systemctl", "restart", "docker"], check=False)


def save_daemon_json(content: str) -> tuple[bool, str]:
    try:
        json.loads(content)  # validate ก่อนเขียนทับ — กัน daemon.json พังจน docker start ไม่ขึ้น
    except json.JSONDecodeError as error:
        return False, f"JSON ไม่ถูกต้อง: {error}"
    if dev_fake_installed():
        return True, "บันทึกแล้ว (dev-mode — จำลองผล ไม่ได้เขียนไฟล์จริง)"
    try:
        DAEMON_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        DAEMON_JSON_PATH.write_text(content, encoding="utf-8")
    except OSError as error:
        return False, f"เขียนไฟล์ไม่สำเร็จ: {error}"
    return True, f"บันทึก {DAEMON_JSON_PATH} เรียบร้อย"


def uninstall_docker(runner: CommandRunner) -> None:
    from services.reset import LifecycleManager
    LifecycleManager(runner).uninstall_docker(remove_config=False)


# ── Compose ──────────────────────────────────────────────────────

def save_compose_file(name: str, content: str) -> Path:
    path = compose_project_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def compose_action(runner: CommandRunner, name: str, action: str) -> CommandResult:
    path = compose_project_path(name)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบ compose project: {name}")
    if dev_fake_installed():
        return _fake_ok("docker", "compose", "-f", path.as_posix(), action)
    if action == "up":
        args = ["docker", "compose", "-f", path.as_posix(), "up", "-d"]
    elif action == "down":
        args = ["docker", "compose", "-f", path.as_posix(), "down"]
    elif action == "restart":
        args = ["docker", "compose", "-f", path.as_posix(), "restart"]
    else:
        raise ValueError(f"Unknown compose action: {action}")
    return runner.run(args, check=False)


# ── Swarm ────────────────────────────────────────────────────────

def swarm_init(runner: CommandRunner, advertise_addr: str | None = None) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "swarm", "init")
    args = ["docker", "swarm", "init"]
    if advertise_addr:
        args += ["--advertise-addr", advertise_addr]
    return runner.run(args, check=False)


def swarm_join(runner: CommandRunner, token: str, remote_addr: str) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "swarm", "join")
    return runner.run(["docker", "swarm", "join", "--token", token, remote_addr], check=False)


def swarm_leave(runner: CommandRunner, force: bool = True) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "swarm", "leave")
    args = ["docker", "swarm", "leave"]
    if force:
        args.append("--force")
    return runner.run(args, check=False)


def rotate_join_tokens(runner: CommandRunner) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "swarm", "join-token", "--rotate")
    worker = runner.run(["docker", "swarm", "join-token", "--rotate", "-q", "worker"], check=False)
    if worker.returncode != 0:
        return worker
    return runner.run(["docker", "swarm", "join-token", "--rotate", "-q", "manager"], check=False)


def promote_node(runner: CommandRunner, node: str) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "node", "promote", node)
    return runner.run(["docker", "node", "promote", node], check=False)


def set_node_availability(runner: CommandRunner, node: str, availability: str) -> CommandResult:
    if availability not in VALID_NODE_AVAILABILITY:
        raise ValueError(f"Unknown node availability: {availability}")
    if dev_fake_installed():
        return _fake_ok("docker", "node", "update", "--availability", availability, node)
    return runner.run(["docker", "node", "update", "--availability", availability, node], check=False)


def remove_node(runner: CommandRunner, node: str, force: bool = True) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "node", "rm", node)
    args = ["docker", "node", "rm"]
    if force:
        args.append("--force")
    args.append(node)
    return runner.run(args, check=False)


def scale_service(runner: CommandRunner, service: str, replicas: int) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "service", "scale", f"{service}={replicas}")
    return runner.run(["docker", "service", "scale", f"{service}={replicas}"], check=False)


def remove_stack(runner: CommandRunner, stack: str) -> CommandResult:
    if dev_fake_installed():
        return _fake_ok("docker", "stack", "rm", stack)
    return runner.run(["docker", "stack", "rm", stack], check=False)


def redeploy_stack(runner: CommandRunner, stack: str) -> CommandResult:
    path = compose_project_path(stack)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบ compose file สำหรับ stack: {stack}")
    if dev_fake_installed():
        return _fake_ok("docker", "stack", "deploy", "-c", path.as_posix(), stack)
    return runner.run(["docker", "stack", "deploy", "-c", path.as_posix(), stack], check=False)
