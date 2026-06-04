# Vending Auto Setup

Automation CLI for preparing Ubuntu 22.04 LTS Desktop vending machines.

Phase 1 installs:

- Docker Engine from Docker's official apt repository
- Node.js from NodeSource apt repository
- Git from Ubuntu apt packages

Phase 2 is intentionally left for touchscreen mapping, X11 display rotation, and WireGuard.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

The current project has no third-party runtime dependencies. For a quick local check:

```bash
python -m vending_auto_setup --dry-run install
python -m vending_auto_setup check
```

After installing the Python package, check tool status with:

```bash
vending-status
```

On a fresh Ubuntu machine, run the installer with:

```bash
sudo vending-auto-setup install
```

## Bootstrap Without Git

During phase 1, the selected distribution path is GitHub Releases plus a bootstrap script. This avoids requiring Git on a fresh Ubuntu machine.

After publishing the repository to GitHub, update `OWNER/vending-auto-setup` in `scripts/install.sh`, then publish the script through GitHub raw content, a short domain, or another HTTPS location.

Fresh Ubuntu command:

```bash
curl -fsSL https://example.com/vending-auto-setup/install.sh | sudo bash
```

POC command that only prints OS information and does not install packages:

```bash
curl -fsSL https://example.com/vending-auto-setup/install.sh | VENDING_AUTO_SETUP_ARGS=about-os bash
```

Bootstrap command that checks whether Git, Node.js, npm, Docker, and the display session type are correct:

```bash
curl -fsSL https://example.com/vending-auto-setup/install.sh | VENDING_AUTO_SETUP_ARGS=check bash
```

The session check reports `OK Session x11` when the user is logged in on X11. It reports `WARN Session wayland` when the current desktop session is Wayland.

To install from a specific GitHub tag:

```bash
curl -fsSL https://example.com/vending-auto-setup/install.sh | sudo VENDING_AUTO_SETUP_VERSION=v0.1.0 bash
```

To pass installer arguments:

```bash
curl -fsSL https://example.com/vending-auto-setup/install.sh | sudo VENDING_AUTO_SETUP_ARGS="install --node-major 22" bash
```

If the tool is not published yet, copy or download the project archive and run:

```bash
sudo PYTHONPATH=src python3 -m vending_auto_setup install
```

Local POC without publishing:

```bash
PYTHONPATH=src python3 -m vending_auto_setup about-os
```

## Virtual Touchscreen POC

If no real touchscreen is available, use Linux `uinput` inside the Ubuntu VM to create a virtual touchscreen for X11/xinput mapping tests.

Install the optional dependency:

```bash
sudo apt update
sudo apt install -y python3-evdev
```

Create a virtual touchscreen and keep it alive:

```bash
sudo python3 scripts/dev/virtual_touchscreen.py --width 1920 --height 1080
```

In another terminal, verify that X11 sees the device:

```bash
xinput list
```

Emit one test tap:

```bash
sudo python3 scripts/dev/virtual_touchscreen.py --tap 960 540
```

This does not attach a fake USB device through VirtualBox. It creates a virtual Linux input device inside the guest OS, which is enough for testing `xinput` detection and mapping logic.

## Configuration

Default target versions live in `src/vending_auto_setup/config.py`.

- `NODE_MAJOR` controls NodeSource major version, currently `22`.
- Docker installs the current package versions available from Docker's apt repository unless `--docker-version` is provided.
- Git installs the current package available from Ubuntu's apt repository unless `GIT_VERSION` is set.
