#!/usr/bin/env bash
set -euo pipefail

REPO="${VENDING_AUTO_SETUP_REPO:-phanuphun/vending-auto-setup}"
VERSION="${VENDING_AUTO_SETUP_VERSION:-latest}"
if [[ -n "${VENDING_AUTO_SETUP_ARGS:-}" ]]; then
  INSTALL_ARGS="${VENDING_AUTO_SETUP_ARGS}"
elif [[ "$#" -gt 0 ]]; then
  INSTALL_ARGS="$*"
else
  INSTALL_ARGS="check"
fi

if [[ "$INSTALL_ARGS" == install* && "$(id -u)" -ne 0 ]]; then
  echo "Install commands must run as root."
  echo "Recommended flow:"
  echo "  wget -O vending-auto-setup.tar.gz https://github.com/${REPO}/archive/refs/heads/main.tar.gz"
  echo "  tar -xzf vending-auto-setup.tar.gz"
  echo "  cd vending-auto-setup-main"
  echo "  sudo PYTHONPATH=src python3 -m cli ${INSTALL_ARGS}"
  exit 1
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

require_command curl
require_command python3
require_command tar

work_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

if [[ "$VERSION" == "latest" ]]; then
  archive_url="https://github.com/${REPO}/archive/refs/heads/main.tar.gz"
else
  archive_url="https://github.com/${REPO}/archive/refs/tags/${VERSION}.tar.gz"
fi

echo "Downloading vending-auto-setup from ${archive_url}"
curl -fsSL "$archive_url" -o "$work_dir/source.tar.gz"

tar -xzf "$work_dir/source.tar.gz" -C "$work_dir"
source_dir="$(find "$work_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

if [[ -z "$source_dir" || ! -f "$source_dir/src/cli.py" ]]; then
  echo "Downloaded archive does not look like vending-auto-setup source."
  exit 1
fi

cd "$source_dir"
echo "Running vending-auto-setup ${INSTALL_ARGS}"
PYTHONPATH=src python3 -m cli ${INSTALL_ARGS}
