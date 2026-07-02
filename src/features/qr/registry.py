"""
qr_device_registry.py — ลงทะเบียนอุปกรณ์ QR / Barcode reader และ integration config

Files:
  ~/.config/vas/qr_devices.json       — list of installed device ids

Integration config เก็บใน SQLite (ตาราง device_integrations) แล้ว — ไม่ใช้
~/.config/vas/qr_integrations.json อีกต่อไป (ย้ายข้อมูลแล้วที่ migration version 2
ดู core/database.py: _migrate_qr_integrations_json_to_device_integrations)
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


# ── Integration config (เก็บใน SQLite: device_integrations) ──────────────────


def load_integrations(device_id: str) -> dict[str, Any]:
    """Return integration config dict for a device, keyed by type (webhook/mqtt/pipe)."""
    from core.database import list_device_integrations
    try:
        return list_device_integrations(device_id)
    except Exception:
        return {}


def save_integrations(device_id: str, data: dict[str, Any]) -> None:
    """
    บันทึก integration config ทั้งชุดของ device (keyed by type) — signature เดิม (dict ทั้งก้อน)
    เพื่อลด diff ที่ server.py แต่ภายใน upsert ทีละ type ลง device_integrations
    """
    from core.database import upsert_device_integration
    for integ_type, integ_data in data.items():
        if integ_type not in ("webhook", "mqtt", "pipe"):
            continue
        if not isinstance(integ_data, dict):
            continue
        upsert_device_integration(device_id, integ_type, integ_data)
