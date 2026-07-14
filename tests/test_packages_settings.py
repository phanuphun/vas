from __future__ import annotations

from features.packages.settings import (
    PACKAGES,
    _GESTURE_LOCKDOWN_SYSTEM_DIR,
    _GESTURE_LOCKDOWN_UUID,
    _GESTURE_LOCKDOWN_VENDOR_DIR,
    _gesture_lockdown_install_script,
)

_PKG_MAP = {p["id"]: p for p in PACKAGES}


def test_gnome_gesture_lockdown_package_registered() -> None:
    """package ใหม่ต้องอยู่ใน PACKAGES พร้อม field ที่จำเป็นครบ (id/category/check/install_cmds/
    uninstall_cmds) — โครงเดียวกับ package อื่นๆ ที่มีอยู่แล้ว (openbox, chromium, qr-udev)"""
    assert "gnome-gesture-lockdown" in _PKG_MAP
    pkg = _PKG_MAP["gnome-gesture-lockdown"]
    assert pkg["category"] == "kiosk"
    assert pkg["depends"] == []
    assert callable(pkg["check"])
    assert len(pkg["install_cmds"]) == 1
    assert len(pkg["uninstall_cmds"]) == 1


def test_gnome_gesture_lockdown_check_false_when_not_installed() -> None:
    """เครื่องทดสอบ/CI ไม่มี /usr/share/gnome-shell/extensions/... อยู่แล้วจริง — check() ต้องคืน
    False ไม่ throw (สอดคล้องกับ _file_check ที่ใช้ทั่วทั้งไฟล์นี้)"""
    pkg = _PKG_MAP["gnome-gesture-lockdown"]
    installed, version = pkg["check"]()
    assert installed is False
    assert version is None


def test_gnome_gesture_lockdown_uninstall_removes_system_dir() -> None:
    pkg = _PKG_MAP["gnome-gesture-lockdown"]
    assert pkg["uninstall_cmds"][0] == ["rm", "-rf", _GESTURE_LOCKDOWN_SYSTEM_DIR]
    assert _GESTURE_LOCKDOWN_UUID in _GESTURE_LOCKDOWN_SYSTEM_DIR


def test_gesture_lockdown_install_script_picks_v9_for_shell_45_plus() -> None:
    """สคริปต์ install ต้องเช็ค GNOME Shell major version แล้วเลือกโฟลเดอร์ vendor ให้ตรง —
    v9 (Shell 45-47) vs v5 (Shell 3.36-44, รวม 42 ที่ยืนยันจริงบน hapymed-sterile-00)"""
    script = _gesture_lockdown_install_script()
    assert "gnome-shell --version" in script
    assert str(_GESTURE_LOCKDOWN_VENDOR_DIR / "v5") in script
    assert str(_GESTURE_LOCKDOWN_VENDOR_DIR / "v9") in script
    assert _GESTURE_LOCKDOWN_SYSTEM_DIR in script


def test_vendored_extension_files_exist_for_both_shell_versions() -> None:
    """กันเผลอลบ/ลืม commit ไฟล์ vendor asset — ทั้ง v5 (Shell 3.36-44) และ v9 (Shell 45-47)
    ต้องมี extension.js + metadata.json ครบทั้งคู่ เพราะ install script (ข้อข้างบน) เลือกใช้
    ตามเวอร์ชันจริงของเครื่อง ณ เวลาติดตั้ง ไม่ได้ตายตัวว่าจะได้โฟลเดอร์ไหน"""
    for version_dir in ("v5", "v9"):
        base = _GESTURE_LOCKDOWN_VENDOR_DIR / version_dir
        assert (base / "extension.js").is_file(), f"missing {version_dir}/extension.js"
        assert (base / "metadata.json").is_file(), f"missing {version_dir}/metadata.json"
        metadata_content = (base / "metadata.json").read_text(encoding="utf-8")
        assert _GESTURE_LOCKDOWN_UUID in metadata_content


def test_chromium_uninstall_removes_snap_not_just_apt_transitional_package() -> None:
    """"chromium-browser" บน Ubuntu 22.04 เป็นแค่ transitional package — apt purge ตัวนี้ไม่เคย
    เรียก "snap remove" ให้เอง (ยืนยันจริงจากผู้ใช้ที่ clone OS ไปตู้ vending แล้วกด uninstall ผ่าน
    หน้า "โปรแกรมเพิ่มเติม" chromium ไม่หลุดจริง ต้องไปลบเองผ่าน Ubuntu Software) — กันเผลอลบคำสั่ง
    "snap remove --purge chromium" ออกในอนาคตแล้วบั๊กเดิมกลับมา"""
    pkg = _PKG_MAP["chromium"]
    assert ["apt-get", "purge", "-y", "chromium-browser", "chromium"] in pkg["uninstall_cmds"]
    assert ["snap", "remove", "--purge", "chromium"] in pkg["uninstall_cmds"]


def test_chromium_install_uses_ppa_deb_instead_of_snap_transitional_package() -> None:
    """เปลี่ยนจาก apt-get install chromium-browser (transitional package ที่ดึง snap มาแทนเสมอบน
    Ubuntu 22.04 — snapd auto-refresh อาจรีสตาร์ท Chromium เองกลางที่ลูกค้ากำลังใช้ตู้) มาใช้ PPA
    xtradeb/apps ติดตั้งเป็น .deb ตรงๆ แทน (ตัดสินใจร่วมกับผู้ใช้ 2026-07-14) — กันเผลอเปลี่ยนกลับไป
    ใช้ chromium-browser แล้วเจอปัญหา snap auto-refresh/boot ช้า/uninstall ไม่หลุดแบบเดิมอีก"""
    pkg = _PKG_MAP["chromium"]
    assert ["add-apt-repository", "-y", "ppa:xtradeb/apps"] in pkg["install_cmds"]
    assert ["apt-get", "install", "-y", "chromium"] in pkg["install_cmds"]
    assert ["apt-get", "install", "-y", "chromium-browser"] not in pkg["install_cmds"]
