# VAS CLI Reference

Entry point: `src/cli.py`, exposed as `vas` / `vending-auto-setup` after install, or run in place with `PYTHONPATH=src python3 -m cli`.

```
vas [--dry-run] [--version] <command> [subcommand] [options]
```

- `--dry-run` — global flag, valid before the command. Prints what would run without executing it. Supported by every command.
- `--version` — print the CLI version and exit (reads `pyproject.toml`).
- Exit codes: `0` success, `1` runtime/validation error, `2` unknown command.
- Commands that touch the system (`install`, `update`, `uninstall`, `reset`, service `start`/`stop`/`install-service`, `wireguard sync`/`unsync`/`install`, `display persist-xorg`/`disable-wayland`/`enable-wayland`, all `kiosk` mutations, `qr install-udev`) require root and Linux — enforced unless `--dry-run` is set.

---

## `vas check`

Print status of every managed tool, service, and config (Git, Node, Docker, AnyDesk, WireGuard, display, kiosk, QR, MQTT, web server, MCP server).

```bash
vas check
```

## `vas about-os`

Print OS/kernel info.

```bash
vas about-os
```

## `vas version`

Print the CLI version string.

```bash
vas version
```

## `vas db migrate`

Apply pending SQLite schema migrations to `vas.db`. Additive only — never drops data. Safe to run repeatedly; also runs automatically at the end of `vas install`.

```bash
vas db migrate
```

## `vas update`

Replace the installed source with the latest from GitHub and rewrite the `/usr/local/bin` wrappers. Requires root.

```bash
sudo vas update [--repo <owner/repo>] [--version <tag|latest>] [--branch <name>]
```

| Flag | Default | Notes |
|---|---|---|
| `--repo` | `phanuphun/vending-auto-setup` | |
| `--version` | `latest` | a git tag, or `latest` to pull branch head |
| `--branch` | `main` | branch used when `--version latest` |

---

## `vas install`

Install one or more components on Ubuntu 22.04.

```bash
sudo vas install [--component <name> ...] [--node-major 22] [--docker-version <ver>] [--git-version <ver>]
```

Components: `node`, `docker`, `git`, `wireguard`, `anydesk`, `openssh`, `qr-udev`, `all`. `--component` is repeatable; omit it to install the default set (`node`, `docker`, `git`). Shows a progress bar, then runs `db migrate` at the end.

## `vas uninstall`

Remove installed components, keep their config files.

```bash
sudo vas uninstall --component <name> [...] [--wireguard-name wg0]
```

Same component list as `install` (`--component` required, repeatable, or `all`).

## `vas reset`

Uninstall components and delete the configs VAS manages for them.

```bash
sudo vas reset --component <name> [...] [--wireguard-name wg0]
```

Components: `node`, `docker`, `git`, `wireguard`, `anydesk`, `openssh`, `display`, `qr-udev`, `all`. Docker reset never touches `/var/lib/docker`.

---

## `vas server` — web dashboard

| Subcommand | Purpose |
|---|---|
| `run [--host 127.0.0.1] [--port 8080] [--debug]` | run Flask in the foreground |
| `start [--host] [--port] [--foreground]` | install systemd unit and start it (root); `--foreground` behaves like `run` |
| `install-service [--host] [--port]` | write the systemd unit only, don't start it (root) |
| `stop` | stop and disable the service (root) |
| `status` | show service status |

```bash
sudo vas server start --host 0.0.0.0 --port 8080
vas server status
```

## `vas mcp` — AI diagnostic server (FastMCP, default port 8899)

Same subcommand shape as `server`: `run [--host] [--port]`, `start [--host] [--port] [--foreground]`, `install-service`, `stop`, `status`. Requires `fastmcp`/`uvicorn` (`uv pip install -e '.[mcp]'`).

```bash
sudo vas mcp start
vas mcp status
```

---

## `vas display`

Inspect and configure display/touchscreen via `xrandr`, `xinput`, `udevadm`.

| Subcommand | Purpose |
|---|---|
| `status [--display :0] [--xauthority <path>]` | show xrandr outputs + xinput devices |
| `list-touch [--display :0]` | list touchscreens with xinput IDs |
| `apply --output <name> --touch <name/id> --rotate <mode> [--display :0]` | apply rotation + touch mapping now (runtime) |
| `persist-session --output <name> --touch <name/id> --rotate <mode> [--delay-seconds 5] [--retries 30]` | write `~/.xprofile` + retry script so it re-applies on login (do **not** use `sudo`) |
| `persist-xorg --touch <name> --rotate <mode>` | write `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf` (root) |
| `disable-wayland` | force GDM into X11 (root) |
| `enable-wayland` | re-enable GDM Wayland (root) |

Rotation values: `normal`, `left`, `right`, `inverted`.

```bash
vas display status --display :0
vas display apply --output Virtual1 --touch "Vending Virtual Touchscreen" --rotate left
sudo vas display persist-xorg --touch "Vending Virtual Touchscreen" --rotate left
```

---

## `vas wireguard`

Global option on the group itself: `--store-dir <path>` (app storage for saved configs/history).

| Subcommand | Purpose |
|---|---|
| `status [--name wg0]` | tool/config/service status |
| `install` | install the `wireguard` package (root) |
| `init-config [--name wg0] [--output wg0.conf] [--force]` | write a config template |
| `validate --config <path>` | validate a config; exit `0`/`1` |
| `save [--name wg0] --config <path>` | store config in app storage, don't apply |
| `sync [--name wg0] [--config <path>] [--no-restart]` | deploy to `/etc/wireguard` and restart the service (root) |
| `history [--name wg0]` | list synced snapshots |
| `show [--name wg0] --id <snapshot_id> [--reveal-secrets]` | show a snapshot (secrets masked by default) |
| `unsync [--name wg0]` | disable service, remove active config (root) |

```bash
vas wireguard init-config --name wg0 --output ./wg0.conf
vas wireguard save --name wg0 --config ./wg0.conf
sudo vas wireguard sync --name wg0
```

Never commit private/preshared keys to the repository.

---

## `vas kiosk`

Manage the dedicated kiosk user, GDM auto-login, session type, and browser autostart. All mutating subcommands require root.

| Subcommand | Purpose |
|---|---|
| `status` | kiosk readiness overview |
| `create-user --username <name> [--groups video,input,plugdev]` | create the Linux user |
| `delete-user --username <name>` | remove the user and home directory |
| `autologin (--enable --username <name> \| --disable)` | toggle GDM auto-login |
| `session-type --username <name> --type gnome\|openbox` | set the desktop session |
| `autostart --username <name> --session-type gnome\|openbox [--home <path>] [--url http://localhost:8888] [--restart-delay 2] [--no-restart]` | write browser autostart files |
| `stop [--username <name>] [--home <path>]` | disable auto-login + remove autostart files; defaults to the current auto-login user |

```bash
sudo vas kiosk create-user --username kiosk-user
sudo vas kiosk autologin --enable --username kiosk-user
sudo vas kiosk session-type --username kiosk-user --type gnome
sudo vas kiosk autostart --username kiosk-user --session-type gnome
```

---

## `vas qr` — ZKTeco QR500-BM reader

| Subcommand | Purpose |
|---|---|
| `status` | udev rule, detected devices, reader thread state |
| `start [--device <path>]` | start the reader thread, blocks until Ctrl+C; auto-detects device if omitted |
| `stop` | stop the global reader thread |
| `last-scan` | print the most recent scan held in memory |
| `test [--device <path>] [--no-grab]` | interactive evdev test, prints each scan live (needs `python3-evdev`); `--no-grab` leaves keystrokes reaching the OS, debug only |
| `install-udev` | write the udev rule for non-root `hidraw` access (root) |
| `config [--device <path>] [--clear-device]` | pin a device path, or clear it to resume auto-detect |

```bash
sudo vas qr install-udev
vas qr start
vas qr last-scan
```

---

## `vas mqtt`

| Subcommand | Purpose |
|---|---|
| `status` | current config + live connection status |
| `config [flags]` | update settings (see below); no flags prints the current config |
| `test` | connect and publish a `TEST-VAS-QR` payload to the configured topic |

`config` flags: `--broker-url <url>`, `--username <user>`, `--password <pass>`, `--client-id <id>`, `--topic <topic>`, `--qos 0|1|2`, `--retain` / `--no-retain`, `--tls-insecure` / `--no-tls-insecure`, `--enable` / `--disable`.

```bash
vas mqtt config --broker-url mqtts://broker.example.com:8883 --topic vending/qr/scan --enable
vas mqtt test
```

Config is stored in `vas.db` (not a flat file); saving triggers a live reload on the running web server if one is up.

---

## Command index

```
install  uninstall  reset  check  about-os  version  update  db
server   mcp        display   wireguard   kiosk   qr   mqtt
```

Run `vas <command> --help` or `vas <command> <subcommand> --help` for the authoritative flag list at any time.
