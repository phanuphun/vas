from __future__ import annotations

import json
import socket
import subprocess

from fastmcp import FastMCP

from system.status import collect_vpn_status

mcp = FastMCP("vas-network")


@mcp.tool()
def get_vpn_status(interface_name: str = "wg0") -> dict:
    """สถานะ WireGuard VPN"""
    try:
        s = collect_vpn_status(interface_name)
        return {
            "interface_name": s.interface_name,
            "wg_installed": s.wg_installed,
            "wg_version": s.wg_version,
            "app_config_path": s.app_config_path.as_posix(),
            "app_config_exists": s.app_config_exists,
            "active_config_path": s.active_config_path.as_posix(),
            "active_config_exists": s.active_config_exists,
            "history_dir": s.history_dir.as_posix(),
            "history_exists": s.history_exists,
            "service_enabled": s.service_enabled,
            "service_active": s.service_active,
            "interface_exists": s.interface_exists,
            "handshake_peers": s.handshake_peers,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_network_status() -> dict:
    """สถานะ network interfaces, default gateway และ connectivity"""
    try:
        interfaces = _get_interfaces()
        gateway = _get_default_gateway()
        gateway_reachable = _ping_gateway(gateway) if gateway else False
        dns_resolving = _check_dns()
        return {
            "interfaces": interfaces,
            "default_gateway": gateway,
            "gateway_reachable": gateway_reachable,
            "dns_resolving": dns_resolving,
        }
    except Exception as e:
        return {"error": str(e)}


def _get_interfaces() -> list[dict]:
    try:
        result = subprocess.run(
            ["ip", "-j", "addr", "show"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return []
    except OSError:
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    interfaces = []
    for iface in raw:
        addresses = [
            f"{addr['local']}/{addr['prefixlen']}"
            for addr in iface.get("addr_info", [])
            if "local" in addr and "prefixlen" in addr
        ]
        interfaces.append(
            {
                "name": iface.get("ifname", ""),
                "state": iface.get("operstate", "UNKNOWN"),
                "addresses": addresses,
            }
        )
    return interfaces


def _get_default_gateway() -> str | None:
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    for line in result.stdout.splitlines():
        parts = line.split()
        if "via" in parts:
            idx = parts.index("via")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return None


def _ping_gateway(gateway: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", gateway],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _check_dns() -> bool:
    try:
        socket.getaddrinfo("google.com", 80)
        return True
    except OSError:
        return False
