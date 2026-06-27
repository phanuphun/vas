"""
qr_device_registry.py — ลงทะเบียนอุปกรณ์ QR / Barcode reader และ integration config

Files:
  ~/.config/vas/qr_devices.json       — list of installed device ids
  ~/.config/vas/qr_integrations.json  — per-device integration config
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── Device catalog ──────────────────────────────────────────────────────────

DEVICE_CATALOG: list[dict[str, str]] = [
    {
        "id":            "zkteco-qr500",
        "name":          "ZKTeco QR500-BM",
        "brand":         "ZKTeco",
        "page_endpoint": "qr_device_zkteco_qr500_page",
    },
]

# ── Config paths ─────────────────────────────────────────────────────────────


def _config_dir() -> Path:
    from system.status import _effective_home  # late import เพื่อหลีกเสี่ยง circular
    return _effective_home() / ".config" / "vas"


def _devices_path() -> Path:
    return _config_dir() / "qr_devices.json"


def _integrations_path() -> Path:
    return _config_dir() / "qr_integrations.json"


# ── Installed devices ─────────────────────────────────────────────────────────


def load_installed_devices() -> list[dict[str, str]]:
    """Return list of installed device dicts (from DEVICE_CATALOG)."""
    path = _devices_path()
    if not path.exists():
        return []
    try:
        raw: list[str] = json.loads(path.read_text())
        catalog_ids = {d["id"]: d for d in DEVICE_CATALOG}
        return [catalog_ids[did] for did in raw if did in catalog_ids]
    except Exception:
        return []


def install_device(device_id: str) -> None:
    path = _devices_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    if path.exists():
        try:
            ids = json.loads(path.read_text())
        except Exception:
            ids = []
    if device_id not in ids:
        ids.append(device_id)
    path.write_text(json.dumps(ids, ensure_ascii=False, indent=2))


def uninstall_device(device_id: str) -> None:
    path = _devices_path()
    if not path.exists():
        return
    try:
        ids: list[str] = json.loads(path.read_text())
        ids = [i for i in ids if i != device_id]
        path.write_text(json.dumps(ids, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ── Integration config ────────────────────────────────────────────────────────


def load_integrations(device_id: str) -> dict[str, Any]:
    """Return integration config dict for a device, keyed by type (webhook/mqtt/pipe)."""
    path = _integrations_path()
    if not path.exists():
        return {}
    try:
        all_integ: dict[str, Any] = json.loads(path.read_text())
        return all_integ.get(device_id, {})
    except Exception:
        return {}


def save_integrations(device_id: str, data: dict[str, Any]) -> None:
    path = _integrations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    all_integ: dict[str, Any] = {}
    if path.exists():
        try:
            all_integ = json.loads(path.read_text())
        except Exception:
            all_integ = {}
    all_integ[device_id] = data
    path.write_text(json.dumps(all_integ, ensure_ascii=False, indent=2))
