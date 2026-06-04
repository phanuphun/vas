#!/usr/bin/env bash
set -euo pipefail

REPO="${VENDING_AUTO_SETUP_REPO:-phanuphun/vending-auto-setup}"
VERSION="${VENDING_AUTO_SETUP_VERSION:-latest}"
PERSIST_CLI="${VENDING_AUTO_SETUP_PERSIST:-0}"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --install-cli|--persist-cli)
      PERSIST_CLI="1"
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

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

install_bootstrap_packages() {
  if [[ "$(id -u)" -ne 0 ]]; then
    return
  fi
  missing_packages=()
  command -v python3 >/dev/null 2>&1 || missing_packages+=("python3")
  command -v tar >/dev/null 2>&1 || missing_packages+=("tar")
  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    missing_packages+=("wget" "ca-certificates")
  fi
  if [[ "${#missing_packages[@]}" -gt 0 ]]; then
    apt-get update
    apt-get install -y "${missing_packages[@]}"
  fi
}

download_file() {
  url="$1"
  output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO "$output" "$url"
    return
  fi
  echo "Missing required command: curl or wget"
  exit 1
}

install_cli_wrapper() {
  source_dir="$1"
  target_dir="/opt/vending-auto-setup"
  bin_dir="/usr/local/bin"

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "--install-cli requires root."
    exit 1
  fi

  rm -rf "$target_dir"
  install -d "$target_dir"
  cp -a "$source_dir"/. "$target_dir"/

  cat >"${bin_dir}/vending-auto-setup" <<'EOF'
#!/usr/bin/env bash
PYTHONPATH=/opt/vending-auto-setup/src exec python3 -m cli "$@"
EOF
  chmod +x "${bin_dir}/vending-auto-setup"

  cat >"${bin_dir}/vas" <<'EOF'
#!/usr/bin/env bash
PYTHONPATH=/opt/vending-auto-setup/src exec python3 -m cli "$@"
EOF
  chmod +x "${bin_dir}/vas"

  cat >"${bin_dir}/vending-status" <<'EOF'
#!/usr/bin/env bash
PYTHONPATH=/opt/vending-auto-setup/src exec python3 -m status "$@"
EOF
  chmod +x "${bin_dir}/vending-status"

  echo "Installed CLI wrappers:"
  echo "  ${bin_dir}/vending-auto-setup"
  echo "  ${bin_dir}/vas"
  echo "  ${bin_dir}/vending-status"
}

install_bootstrap_packages
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
download_file "$archive_url" "$work_dir/source.tar.gz"

tar -xzf "$work_dir/source.tar.gz" -C "$work_dir"
source_dir="$(find "$work_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

if [[ -z "$source_dir" || ! -f "$source_dir/src/cli.py" ]]; then
  echo "Downloaded archive does not look like vending-auto-setup source."
  exit 1
fi

if [[ "$PERSIST_CLI" == "1" ]]; then
  install_cli_wrapper "$source_dir"
  source_dir="/opt/vending-auto-setup"
fi

cd "$source_dir"
echo "Running vending-auto-setup ${INSTALL_ARGS}"
PYTHONPATH=src python3 -m cli ${INSTALL_ARGS}
