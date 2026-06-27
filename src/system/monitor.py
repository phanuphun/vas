"""
VAS — System Monitor

อ่าน metrics จาก Linux built-in sources เท่านั้น (ไม่ต้อง apt install เพิ่ม):
    /proc/stat          → CPU usage %
    /proc/cpuinfo       → CPU model, cores, MHz
    /proc/loadavg       → load average 1/5/15 min
    /proc/meminfo       → RAM, swap, buffers, cache
    /proc/uptime        → uptime seconds
    /proc/net/dev       → network bytes sent/received per interface
    /sys/class/thermal/ → CPU temperature
    /etc/os-release     → OS name/version
    os.statvfs()        → disk usage per mount point
    subprocess: uname, lsblk (pre-installed on Ubuntu)
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def _read_proc_stat() -> dict[str, list[int]]:
    """อ่าน /proc/stat และคืน dict cpu_name → [user,nice,system,idle,iowait,irq,softirq,steal]"""
    result: dict[str, list[int]] = {}
    try:
        lines = Path("/proc/stat").read_text().splitlines()
        for line in lines:
            if not line.startswith("cpu"):
                break
            parts = line.split()
            result[parts[0]] = [int(x) for x in parts[1:]]
    except OSError:
        pass
    return result


def _cpu_percent(stat1: dict[str, list[int]], stat2: dict[str, list[int]]) -> float:
    """คำนวณ CPU usage % จาก 2 snapshots ของ /proc/stat"""
    s1 = stat1.get("cpu", [])
    s2 = stat2.get("cpu", [])
    if len(s1) < 4 or len(s2) < 4:
        return 0.0
    idle1 = s1[3] + (s1[4] if len(s1) > 4 else 0)
    idle2 = s2[3] + (s2[4] if len(s2) > 4 else 0)
    total1 = sum(s1)
    total2 = sum(s2)
    total_diff = total2 - total1
    idle_diff  = idle2 - idle1
    if total_diff == 0:
        return 0.0
    return round((1 - idle_diff / total_diff) * 100, 1)


def get_cpu() -> dict[str, Any]:
    """
    อ่าน CPU info + usage % (อ่าน /proc/stat 2 ครั้ง ห่างกัน 0.4s)
    Returns: model, cores, threads, mhz, usage_pct, load_1/5/15, per_core_pct
    """
    # --- CPU info จาก /proc/cpuinfo ---
    model = "Unknown"
    cores = 0
    threads = 0
    mhz_list: list[float] = []

    try:
        text = Path("/proc/cpuinfo").read_text()
        for line in text.splitlines():
            if line.startswith("model name") and model == "Unknown":
                model = line.split(":", 1)[-1].strip()
            elif line.startswith("cpu cores"):
                try:
                    cores = int(line.split(":", 1)[-1].strip())
                except ValueError:
                    pass
            elif line.startswith("processor"):
                threads += 1
            elif line.startswith("cpu MHz"):
                try:
                    mhz_list.append(float(line.split(":", 1)[-1].strip()))
                except ValueError:
                    pass
    except OSError:
        pass

    if cores == 0:
        cores = threads or 1
    avg_mhz = round(sum(mhz_list) / len(mhz_list), 0) if mhz_list else None

    # --- Load average ---
    load_1 = load_5 = load_15 = 0.0
    try:
        parts = Path("/proc/loadavg").read_text().split()
        load_1, load_5, load_15 = float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, IndexError, ValueError):
        pass

    # --- CPU usage % (delta สอง snapshot) ---
    stat1 = _read_proc_stat()
    time.sleep(0.4)
    stat2 = _read_proc_stat()

    usage_pct = _cpu_percent(stat1, stat2)

    # per-core usage
    per_core: list[float] = []
    for i in range(threads):
        key = f"cpu{i}"
        if key in stat1 and key in stat2:
            per_core.append(_cpu_percent({key: stat1[key]}, {key: stat2[key]}))

    return {
        "model": model,
        "cores": cores,
        "threads": threads,
        "mhz": avg_mhz,
        "usage_pct": usage_pct,
        "load_1": load_1,
        "load_5": load_5,
        "load_15": load_15,
        "per_core_pct": per_core,
    }


# ---------------------------------------------------------------------------
# Memory / RAM
# ---------------------------------------------------------------------------

def get_memory() -> dict[str, Any]:
    """อ่าน /proc/meminfo — คืน total/used/free/cached/buffers/swap (bytes)"""
    info: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                nums = re.findall(r"\d+", val)
                if nums:
                    info[key.strip()] = int(nums[0]) * 1024  # kB → bytes
    except OSError:
        pass

    total   = info.get("MemTotal", 0)
    free    = info.get("MemFree", 0)
    cached  = info.get("Cached", 0) + info.get("SReclaimable", 0)
    buffers = info.get("Buffers", 0)
    available = info.get("MemAvailable", free)
    used    = total - available

    swap_total = info.get("SwapTotal", 0)
    swap_free  = info.get("SwapFree", 0)
    swap_used  = swap_total - swap_free

    used_pct  = round(used  / total  * 100, 1) if total  else 0.0
    swap_pct  = round(swap_used / swap_total * 100, 1) if swap_total else 0.0

    return {
        "total":       total,
        "used":        used,
        "free":        free,
        "available":   available,
        "cached":      cached,
        "buffers":     buffers,
        "used_pct":    used_pct,
        "swap_total":  swap_total,
        "swap_used":   swap_used,
        "swap_pct":    swap_pct,
    }


# ---------------------------------------------------------------------------
# Disk
# ---------------------------------------------------------------------------

_EXCLUDE_FS = frozenset([
    "tmpfs", "devtmpfs", "sysfs", "proc", "devpts", "cgroup",
    "cgroup2", "pstore", "bpf", "tracefs", "debugfs", "hugetlbfs",
    "mqueue", "fusectl", "overlay", "squashfs", "efivarfs",
])
_EXCLUDE_MOUNT_PREFIX = ("/proc", "/sys", "/dev", "/run", "/snap")


def get_disk() -> list[dict[str, Any]]:
    """
    อ่าน mount points ที่น่าสนใจจาก /proc/mounts แล้วใช้ os.statvfs()
    คืน list ของ {mount, device, fstype, total, used, free, used_pct}
    """
    mounts: list[dict[str, Any]] = []
    seen_devices: set[str] = set()

    try:
        lines = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return []

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1], parts[2]

        if fstype in _EXCLUDE_FS:
            continue
        if any(mount.startswith(p) for p in _EXCLUDE_MOUNT_PREFIX):
            continue
        # ข้าม duplicate device (เช่น bind mounts)
        if device in seen_devices and device != "none":
            continue
        seen_devices.add(device)

        try:
            st = os.statvfs(mount)
        except OSError:
            continue

        total = st.f_frsize * st.f_blocks
        free  = st.f_frsize * st.f_bfree
        used  = total - free
        avail = st.f_frsize * st.f_bavail

        if total == 0:
            continue

        mounts.append({
            "mount":    mount,
            "device":   device,
            "fstype":   fstype,
            "total":    total,
            "used":     used,
            "free":     avail,
            "used_pct": round(used / total * 100, 1),
        })

    return sorted(mounts, key=lambda x: x["mount"])


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------

def get_temperatures() -> list[dict[str, Any]]:
    """อ่าน /sys/class/thermal/thermal_zone*/temp — คืน list {label, temp_c}"""
    temps: list[dict[str, Any]] = []
    thermal_dir = Path("/sys/class/thermal")
    if not thermal_dir.exists():
        return temps

    for zone in sorted(thermal_dir.glob("thermal_zone*")):
        try:
            raw = int((zone / "temp").read_text().strip())
            temp_c = round(raw / 1000, 1)
        except (OSError, ValueError):
            continue

        try:
            label = (zone / "type").read_text().strip()
        except OSError:
            label = zone.name

        # กรอง zone ที่ไม่มีความหมาย (0°C หรือ ≥ 120°C น่าจะผิดปกติ)
        if 0 < temp_c < 120:
            temps.append({"label": label, "temp_c": temp_c})

    return temps


# ---------------------------------------------------------------------------
# Uptime
# ---------------------------------------------------------------------------

def get_uptime() -> dict[str, Any]:
    """อ่าน /proc/uptime — คืน total_seconds, days, hours, minutes"""
    try:
        parts = Path("/proc/uptime").read_text().split()
        total = float(parts[0])
    except (OSError, IndexError, ValueError):
        total = 0.0

    days    = int(total // 86400)
    hours   = int((total % 86400) // 3600)
    minutes = int((total % 3600) // 60)

    return {
        "total_seconds": total,
        "days":    days,
        "hours":   hours,
        "minutes": minutes,
        "human":   f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m",
    }


# ---------------------------------------------------------------------------
# Network I/O
# ---------------------------------------------------------------------------

_EXCLUDE_IFACE = frozenset(["lo"])


def get_network() -> list[dict[str, Any]]:
    """อ่าน /proc/net/dev — คืน list {iface, rx_bytes, tx_bytes, rx_mb, tx_mb}"""
    ifaces: list[dict[str, Any]] = []
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()
    except OSError:
        return ifaces

    for line in lines[2:]:  # skip 2 header lines
        if ":" not in line:
            continue
        iface, rest = line.split(":", 1)
        iface = iface.strip()
        if iface in _EXCLUDE_IFACE:
            continue
        nums = rest.split()
        if len(nums) < 9:
            continue
        rx_bytes = int(nums[0])
        tx_bytes = int(nums[8])
        ifaces.append({
            "iface":    iface,
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "rx_mb":    round(rx_bytes / 1_048_576, 1),
            "tx_mb":    round(tx_bytes / 1_048_576, 1),
        })

    return sorted(ifaces, key=lambda x: x["iface"])


# ---------------------------------------------------------------------------
# OS / System info
# ---------------------------------------------------------------------------

def get_os_info() -> dict[str, Any]:
    """อ่าน /etc/os-release + uname — คืน os_name, kernel, hostname, arch"""
    os_name = "Linux"
    os_version = ""

    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip().strip('"')
                break
    except OSError:
        pass

    try:
        uname = os.uname()
        kernel = uname.release
        arch   = uname.machine
    except AttributeError:
        kernel = arch = "unknown"

    try:
        hostname = os.uname().nodename
    except Exception:
        import socket
        hostname = socket.gethostname()

    return {
        "os_name":  os_name,
        "kernel":   kernel,
        "arch":     arch,
        "hostname": hostname,
    }


# ---------------------------------------------------------------------------
# Block devices (lsblk — pre-installed on Ubuntu)
# ---------------------------------------------------------------------------

def get_block_devices() -> list[dict[str, Any]]:
    """รัน lsblk -b -o NAME,SIZE,TYPE,MODEL,TRAN --json (pre-installed บน Ubuntu)"""
    try:
        import json as _json
        result = subprocess.run(
            ["lsblk", "-b", "-o", "NAME,SIZE,TYPE,MODEL,TRAN", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        data = _json.loads(result.stdout)
        devices: list[dict[str, Any]] = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") == "disk":
                size = int(dev.get("size") or 0)
                devices.append({
                    "name":  dev.get("name", ""),
                    "size":  size,
                    "size_gb": round(size / 1_073_741_824, 1),
                    "model": (dev.get("model") or "").strip(),
                    "tran":  dev.get("tran") or "unknown",
                })
        return devices
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        return []


# ---------------------------------------------------------------------------
# All-in-one snapshot
# ---------------------------------------------------------------------------

def collect_metrics() -> dict[str, Any]:
    """คืน metrics ทั้งหมดในครั้งเดียว — เรียกจาก API endpoint"""
    return {
        "ts":      time.time(),
        "os":      get_os_info(),
        "uptime":  get_uptime(),
        "cpu":     get_cpu(),        # อ่าน /proc/stat 2 ครั้ง ใช้เวลา ~0.4s
        "memory":  get_memory(),
        "disk":    get_disk(),
        "temps":   get_temperatures(),
        "network": get_network(),
        "block":   get_block_devices(),
    }


# ---------------------------------------------------------------------------
# Format helpers (ใช้ใน template หรือ JS)
# ---------------------------------------------------------------------------

def fmt_bytes(n: int) -> str:
    """1234567890 → '1.15 GB'"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} PB"