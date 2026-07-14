from __future__ import annotations

from fastmcp import FastMCP

from system.info import collect_os_info
from system.status import collect_remote_access_status, collect_status, collect_web_server_status

mcp = FastMCP("vas-system")


@mcp.tool()
def get_system_status() -> dict:
    """ตรวจสอบสถานะ tools หลักที่ติดตั้งในระบบ (Git, Node.js, npm, PM2, Docker, AnyDesk)"""
    try:
        tools = collect_status()
        return {
            "tools": [
                {
                    "name": t.name,
                    "installed": t.installed,
                    "version": t.version,
                    "path": t.path,
                }
                for t in tools
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_os_info() -> dict:
    """ข้อมูล OS และ kernel ของเครื่อง"""
    try:
        return collect_os_info()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_web_server_status() -> dict:
    """สถานะ VAS web dashboard service (port 8080)"""
    try:
        s = collect_web_server_status()
        return {
            "host": s.host,
            "port": s.port,
            "url": s.url,
            "service_enabled": s.service_enabled,
            "service_active": s.service_active,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_remote_access_status() -> dict:
    """สถานะ AnyDesk remote access"""
    try:
        s = collect_remote_access_status()
        return {
            "anydesk_installed": s.anydesk_installed,
            "anydesk_version": s.anydesk_version,
            "anydesk_id": s.anydesk_id,
            "anydesk_status": s.anydesk_status,
            "service_enabled": s.service_enabled,
            "service_active": s.service_active,
        }
    except Exception as e:
        return {"error": str(e)}
