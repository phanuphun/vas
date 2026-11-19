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


def test_kiosk_accessory_packages_registered() -> None:
    """obconf/unclutter-xfixes/xterm ต้องอยู่ใน PACKAGES หมวด kiosk ครบตาม
    docs/manual-kiosk-openbox-chromium-xorg-guide.md ข้อ 4 (เครื่องมือเสริม Openbox)"""
    for pkg_id in ("obconf", "unclutter-xfixes", "xterm"):
        assert pkg_id in _PKG_MAP, f"missing package: {pkg_id}"
        pkg = _PKG_MAP[pkg_id]
        assert pkg["category"] == "kiosk"
        assert callable(pkg["check"])
        assert len(pkg["install_cmds"]) >= 1
        assert len(pkg["uninstall_cmds"]) == 1
        assert pkg["install_cmds"][-1][:3] == ["apt-get", "install", "-y"]
        assert pkg["uninstall_cmds"][0][:3] == ["apt-get", "purge", "-y"]


def test_kiosk_accessory_packages_check_false_when_not_installed() -> None:
    """เครื่องทดสอบ/CI ไม่มี obconf/unclutter-xfixes/xterm ติดตั้งอยู่จริง — check() ต้องคืน
    False ไม่ throw (ใช้ _which_check ทั่วไปเหมือน package อื่นๆ)"""
    for pkg_id in ("obconf", "unclutter-xfixes", "xterm"):
        installed, _version = _PKG_MAP[pkg_id]["check"]()
        assert installed is False


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


def test_x11vnc_package_registered() -> None:
    """package x11vnc ต้องอยู่ใน PACKAGES หมวด remote พร้อม install/uninstall ผ่าน apt เหมือน
    anydesk/openssh — ดู docs/plans/2026-08-06-x11vnc-remote-backend-spec.md"""
    assert "x11vnc" in _PKG_MAP
    pkg = _PKG_MAP["x11vnc"]
    assert pkg["category"] == "remote"
    assert pkg["depends"] == []
    assert callable(pkg["check"])
    assert pkg["install_cmds"][-1] == ["apt-get", "install", "-y", "x11vnc"]
    assert ["systemctl", "disable", "--now", "x11vnc"] in pkg["uninstall_cmds"]
    assert ["apt-get", "purge", "-y", "x11vnc"] in pkg["uninstall_cmds"]


def test_x11vnc_check_false_when_not_installed() -> None:
    """เครื่องทดสอบ/CI ไม่มี x11vnc ติดตั้งอยู่จริง — check() ต้องคืน False ไม่ throw"""
    installed, _version = _PKG_MAP["x11vnc"]["check"]()
    assert installed is False


def test_chromium_install_uses_ppa_deb_instead_of_snap_transitional_package() -> None:
    """เปลี่ยนจาก apt-get install chromium-browser (transitional package ที่ดึง snap มาแทนเสมอบน
    Ubuntu 22.04 — snapd auto-refresh อาจรีสตาร์ท Chromium เองกลางที่ลูกค้ากำลังใช้ตู้) มาใช้ PPA
    xtradeb/apps ติดตั้งเป็น .deb ตรงๆ แทน (ตัดสินใจร่วมกับผู้ใช้ 2026-07-14) — กันเผลอเปลี่ยนกลับไป
    ใช้ chromium-browser แล้วเจอปัญหา snap auto-refresh/boot ช้า/uninstall ไม่หลุดแบบเดิมอีก"""
    pkg = _PKG_MAP["chromium"]
    assert ["add-apt-repository", "-y", "ppa:xtradeb/apps"] in pkg["install_cmds"]
    assert ["apt-get", "install", "-y", "chromium"] in pkg["install_cmds"]
    assert ["apt-get", "install", "-y", "chromium-browser"] not in pkg["install_cmds"]


def test_docker_install_cmds_supports_dynamic_distro() -> None:
    """คำสั่งติดตั้ง docker ใน settings ต้องรองรับทั้ง Ubuntu และ Debian
    โดยดึง $OS_ID จาก /etc/os-release ไม่ฮาร์ดโค้ด ubuntu อย่างเดียว"""
    pkg = _PKG_MAP["docker"]
    install_cmds_flat = " ".join(" ".join(cmd) for cmd in pkg["install_cmds"])
    assert "$OS_ID" in install_cmds_flat
    assert "${ID:-ubuntu}" in install_cmds_flat
    assert ["rm", "-f", "/etc/apt/sources.list.d/docker.list"] in pkg["install_cmds"]


def test_detect_os_id_and_codename(tmp_path: Any) -> None:
    """ทดสอบการตรวจจับ OS ID และ Codename สำหรับ Debian และ Ubuntu"""
    from system.utils import detect_os_codename, detect_os_id

    # Debian 13 trixie
    deb_file = tmp_path / "os-release-deb"
    deb_file.write_text('ID=debian\nVERSION_CODENAME=trixie\n', encoding="utf-8")
    assert detect_os_id(deb_file) == "debian"
    assert detect_os_codename(deb_file) == "trixie"

    # Ubuntu 22.04 jammy
    ubu_file = tmp_path / "os-release-ubu"
    ubu_file.write_text('ID=ubuntu\nVERSION_CODENAME=jammy\n', encoding="utf-8")
    assert detect_os_id(ubu_file) == "ubuntu"
    assert detect_os_codename(ubu_file) == "jammy"

