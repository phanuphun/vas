---
tags: [spec, plan]
date: 2026-06-18
project: vas
status: approved
---

# Spec: VAS MCP Server (Phase 4)

## Goal

Implement a read-only FastMCP HTTP/SSE server (`mcp_server.py` + `mcp_tools/` package) that exposes 12 diagnostic tools over port 8899, secured by WireGuard VPN, so AI agents can remotely inspect vending machine Mini PC state without physical access.

---

## Resolved Design Decisions

| Question | Decision |
|---|---|
| systemd service user | `root` — consistent with `vas-server.service`; journalctl, docker, lsusb work without sudo |
| Deploy path / ExecStart | `WorkingDirectory=/opt/vas`, `ExecStart=uv run python -m mcp_server` |
| CommandRunner in display.py | Use `subprocess.run()` directly — consistent with other MCP tools; no CommandRunner import |
| MCP_PORT location | Add `MCP_PORT = 8899` constant to existing `src/server_service.py` |

---

## Data model changes

None. New server process + tool layer on top of existing read-only collectors. No database, migration, or schema changes.

---

## Process flow

1. `vas-mcp.service` starts on boot (After `network.target` and `vending-auto-setup-server.service`).
2. `mcp_server.py` initialises a FastMCP app with `transport="sse"`, `host="0.0.0.0"`, `port=8899`.
3. FastMCP auto-discovers tools by importing each submodule in `mcp_tools/`.
4. AI agent connects through WireGuard VPN (`wg0`) to `http://<wg-ip>:8899`.
5. Agent calls a tool → FastMCP routes to decorated function in `mcp_tools/*.py`.
6. Tool calls existing collector, serializes result to plain `dict`, returns it. All Path fields → `.as_posix()`.
7. FastMCP serializes dict to JSON and streams response over SSE.
8. No writes to disk. All tools strictly read-only.

---

## API changes

No existing endpoints changed. New server on separate port.

- Base URL: `http://0.0.0.0:8899`
- Transport: HTTP/SSE (FastMCP built-in)
- Auth: None at application layer — WireGuard VPN is trust boundary

### 12 MCP Tools

| Tool | Module | Params | Backing call |
|---|---|---|---|
| `get_system_status` | `mcp_tools/system.py` | none | `status.collect_status()` |
| `get_os_info` | `mcp_tools/system.py` | none | `os_info.collect_os_info()` |
| `get_web_server_status` | `mcp_tools/system.py` | none | `status.collect_web_server_status()` |
| `get_remote_access_status` | `mcp_tools/system.py` | none | `status.collect_remote_access_status()` |
| `get_vpn_status` | `mcp_tools/network.py` | `interface_name: str = "wg0"` | `status.collect_vpn_status(interface_name)` |
| `get_network_status` | `mcp_tools/network.py` | none | subprocess: `ip -j addr`, `ip route`, `ping -c 1 -W 2` |
| `get_display_status` | `mcp_tools/display.py` | none | multiple `status.collect_*` calls |
| `get_usb_devices` | `mcp_tools/display.py` | none | subprocess: `lsusb` + `display.get_udevadm_touchscreen_names(runner)` |
| `get_docker_status` | `mcp_tools/docker.py` | `include_logs: bool = False`, `log_lines: int = 50` | subprocess: `docker ps`, `docker inspect`, `docker logs` |
| `get_logs` | `mcp_tools/logs.py` | `snapshot_id: str \| None = None` | `audit_log.list_system_snapshots()` / `read_system_snapshot()` |
| `get_journal_logs` | `mcp_tools/logs.py` | `since`, `until`, `unit`, `lines: int = 200` | subprocess: `journalctl` |
| `get_logged_in_users` | `mcp_tools/logs.py` | `history: bool = False` | subprocess: `who`, `last -n 50` |

---

## Implementation routing

- **frontend-builder:** not required
- **backend-builder:** required
- **build order:** pyproject.toml → server_service.py → mcp_tools/__init__.py → system.py → network.py → display.py → docker.py → logs.py → mcp_server.py → vas-mcp.service content

---

## Files that will change

### New files

| File | Description |
|---|---|
| `src/mcp_server.py` | FastMCP app entry point |
| `src/mcp_tools/__init__.py` | Empty package marker |
| `src/mcp_tools/system.py` | get_system_status, get_os_info, get_web_server_status, get_remote_access_status |
| `src/mcp_tools/network.py` | get_vpn_status, get_network_status |
| `src/mcp_tools/display.py` | get_display_status, get_usb_devices |
| `src/mcp_tools/docker.py` | get_docker_status |
| `src/mcp_tools/logs.py` | get_logs, get_journal_logs, get_logged_in_users |

### Modified files

| File | Change |
|---|---|
| `pyproject.toml` | Add `[project.optional-dependencies]` with `mcp = ["fastmcp>=2.0", "uvicorn>=0.29"]` |
| `src/server_service.py` | Add `MCP_PORT = 8899` module-level constant |

### systemd unit (rendered content, not in repo)

```ini
[Unit]
Description=VAS MCP Server
After=network.target vending-auto-setup-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vas
ExecStart=uv run python -m mcp_server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Error handling contract

- No tool may raise an unhandled exception
- All errors return `{"error": "<message>"}`
- Subprocess timeout: 10 seconds for all subprocess calls
- Missing tool (docker not installed, etc.): return error dict, not exception
- Path fields: always `.as_posix()` before returning

---

## Tests required

- `tests/test_mcp_tools_system.py` — mock collectors, assert dict shape
- `tests/test_mcp_tools_network.py` — mock subprocess, assert error dict on timeout
- `tests/test_mcp_tools_display.py` — mock collectors + lsusb subprocess
- `tests/test_mcp_tools_docker.py` — mock subprocess, test include_logs, test daemon not running
- `tests/test_mcp_tools_logs.py` — mock audit_log, test list/read modes, test invalid snapshot_id
