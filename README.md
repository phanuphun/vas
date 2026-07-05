# VAS — Vending Auto Setup

CLI + web dashboard + MCP server for provisioning and operating Ubuntu 22.04 LTS vending-kiosk machines. Current version: see `pyproject.toml` (`0.1.5`).

## What it does today

- **Package install** — Node.js 22, Docker Engine, Git, AnyDesk, WireGuard, OpenSSH via `vas install`.
- **Display & touchscreen** — detect X11/Wayland, list monitors (`xrandr`) and touch devices (`xinput`/`udevadm`), apply rotation + touch-matrix mapping at runtime, persist across reboot (`.xprofile` or Xorg `InputClass`), toggle GDM Wayland on/off.
- **WireGuard VPN** — create/validate/save/sync configs, history with secret masking, unsync, status.
- **Kiosk mode** — create/delete a dedicated kiosk Linux user, GDM auto-login, GNOME/Openbox session switch, browser autostart (restart-loop or one-shot), stop kiosk mode.
- **QR reader** — ZKTeco QR500-BM support via `evdev` or raw `hidraw`, auto-detect or pinned device, udev rule install, live SSE stream, last-scan lookup.
- **MQTT publish** — configure broker/topic/QoS/TLS/retain, publish QR scans, test publish.
- **Docker** — container status/logs/restart-count via the web dashboard.
- **SQLite database** (`vas.db`) — schema init/migration (`vas db init`).
- **Remote access** — AnyDesk and OpenSSH install + status.
- **Self-update** — `vas update` pulls latest source from GitHub (release tag or branch head) and replaces the install in place, with auto-restart of the running service.
- **Web dashboard** (Flask, Thai UI) — SPA with pages for Display, WireGuard, Kiosk, QR, MQTT, Docker, Users, Remote (AnyDesk/OpenSSH), Named Pipe tester, System logs/monitor, Database, Software/Update, Settings.
- **MCP server** (FastMCP, port `8899`) — AI-facing diagnostic tools: system/OS status, web server status, remote-access status, VPN/network status, display + USB device info, Docker status/logs, system logs, journal logs, logged-in users.
- **Everything supports `--dry-run`**, and every command has an `uninstall`/`reset` counterpart.

## Requirements

Ubuntu 22.04 LTS Desktop (x86_64), Python 3.10+, internet access for install/update. `python3-evdev` for QR evdev mode, `paho-mqtt` for MQTT, `fastmcp`+`uvicorn` for the MCP server.

## Install

```bash
# One-line bootstrap (CLI + all components)
wget -qO- https://raw.githubusercontent.com/phanuphun/vending-auto-setup/main/scripts/install.sh | sudo bash -s -- --install-cli install --component all
```

## Quick start

```bash
vas check                                     # status of everything
sudo vas install --component all              # node, docker, git, wireguard, anydesk
sudo vas server start --host 0.0.0.0 --port 8080   # web dashboard
sudo vas mcp start                            # MCP diagnostic server (port 8899)
vas qr start                                  # QR reader
vas mqtt config --broker-url mqtts://broker.example.com:8883 --enable
sudo vas kiosk create-user --username kiosk-user
sudo vas wireguard sync --name wg0
```

## Command groups

`install` `uninstall` `reset` `check` `about-os` `version` `update` `db` `server` `mcp` `display` `wireguard` `kiosk` `qr` `mqtt`

Run `vas <group> --help` for full options.

## Local development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

PYTHONPATH=src python3 -m cli check
PYTHONPATH=src python3 -m pytest tests/ -q
mypy src tests
ruff check src tests
```

## Project structure

```
src/
  cli.py, core/       — entry point, config, database, auth
  features/           — display, wireguard, kiosk, qr, mqtt, docker, packages, remote
  services/           — server_service, reset, updater
  system/             — audit, clock, monitor, power, status, utils
  mcp/                — MCP server + tools (system, network, display, docker, logs)
  server.py, web/     — Flask app, Jinja templates, static assets
docs/                 — per-subsystem docs (see docs/overview.md)
tests/                — pytest suite
```

See `docs/overview.md` for the full architecture map and `AGENTS.md` / `INSTRUCTIONS.md` for contributor conventions.
