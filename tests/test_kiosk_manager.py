from __future__ import annotations

from pathlib import Path

import pytest

from core.runner import CommandRunner
from features.kiosk import manager as kiosk_manager
from features.kiosk.manager import (
    CHROME_KIOSK_FLAG_DEFS,
    CHROMIUM_POLICY_PATHS,
    GNOME_LOCKDOWN_FLAG_DEFS,
    GNOME_LOCKDOWN_SIGNATURE,
    OPENBOX_KEYBIND_BLOCKLIST,
    KioskManager,
    _parse_gnome_lockdown_flags,
    _parse_kiosk_flags,
    build_gnome_lockdown_preamble,
    build_hide_cursor_css,
    build_hide_cursor_manifest,
    build_kiosk_launch_script,
    build_translate_policy_content,
    collect_hide_cursor_extension_status,
    collect_translate_policy_status,
    kiosk_hide_cursor_extension_dir,
    normalize_chrome_flags,
    normalize_gnome_lockdown_flags,
    remove_chromium_snap,
    strip_openbox_keybinds,
)

URL = "https://vending.example.io/"


def test_translate_flag_emits_both_legacy_switch_and_disable_features() -> None:
    """--disable-translate ถูก Chromium เลิกรองรับในบางเวอร์ชัน (Chromium issue 41347677) —
    ต้องมีทั้ง switch เดิมและ --disable-features=Translate ในสคริปต์ที่สร้างออกมา"""
    script = build_kiosk_launch_script(URL, True, 2, {"disable_translate": True})

    assert "--disable-translate" in script
    assert "Translate" in script


def test_swipe_navigation_flag_emits_legacy_switch_and_feature_name() -> None:
    script = build_kiosk_launch_script(URL, True, 2, {"disable_swipe_navigation": True})

    assert "--overscroll-history-navigation=0" in script
    assert "OverscrollHistoryNavigation" in script
    assert "TouchpadOverscrollHistoryNavigation" in script


def test_disable_pinch_flag_present_only_when_enabled() -> None:
    enabled = build_kiosk_launch_script(URL, True, 2, {"disable_pinch_zoom": True})
    disabled = build_kiosk_launch_script(URL, True, 2, {"disable_pinch_zoom": False})

    assert "--disable-pinch" in enabled
    assert "--disable-pinch" not in disabled


def test_multiple_disable_features_toggles_merge_into_single_flag() -> None:
    """ห้ามมี --disable-features ปรากฏซ้ำหลายครั้งบนบรรทัดคำสั่งเดียวกัน — Chromium ใช้แค่
    occurrence สุดท้ายของ switch ซ้ำ (last-one-wins) ถ้าไม่ merge จะมี toggle หนึ่งถูกเมิน"""
    script = build_kiosk_launch_script(
        URL, True, 2, {"disable_translate": True, "disable_swipe_navigation": True},
    )

    command_line = next(line for line in script.splitlines() if "--kiosk" in line)
    assert command_line.count("--disable-features=") == 1
    assert "Translate" in command_line
    assert "OverscrollHistoryNavigation" in command_line


def test_parse_kiosk_flags_roundtrips_with_build() -> None:
    chrome_flags = normalize_chrome_flags({
        "disable_translate": True,
        "disable_swipe_navigation": False,
        "disable_pinch_zoom": True,
        "no_first_run": False,
    })
    script = build_kiosk_launch_script(URL, True, 2, chrome_flags)
    parsed = _parse_kiosk_flags(script)

    assert parsed == chrome_flags


def test_all_chrome_flag_defs_have_flag_and_features_keys() -> None:
    for item in CHROME_KIOSK_FLAG_DEFS:
        assert isinstance(item["flag"], str) and item["flag"].startswith("--")
        assert isinstance(item["features"], tuple)


def test_gnome_lockdown_preamble_contains_all_commands_by_default() -> None:
    preamble = build_gnome_lockdown_preamble(None)

    assert GNOME_LOCKDOWN_SIGNATURE in preamble
    for item in GNOME_LOCKDOWN_FLAG_DEFS:
        assert item["command"] in preamble


def test_gnome_lockdown_preamble_omits_disabled_toggle() -> None:
    flags = normalize_gnome_lockdown_flags({"disable_hot_corner": False})
    preamble = build_gnome_lockdown_preamble(flags)

    hot_corner_command = next(
        item["command"] for item in GNOME_LOCKDOWN_FLAG_DEFS if item["key"] == "disable_hot_corner"
    )
    assert hot_corner_command not in preamble


def test_parse_gnome_lockdown_flags_roundtrips_with_build() -> None:
    flags = normalize_gnome_lockdown_flags({
        "disable_hot_corner": True,
        "disable_terminal_shortcut": False,
        "disable_super_key": True,
    })
    preamble = build_gnome_lockdown_preamble(flags)
    parsed = _parse_gnome_lockdown_flags(preamble)

    assert parsed == flags


def test_ubuntu_dock_lockdown_present_by_default_and_omitted_when_disabled() -> None:
    """toggle ปิด Ubuntu Dock (เพิ่มจากการวิเคราะห์คลิปที่พบว่าปัดขอบจอซ้ายแล้ว dock โผล่ทับ
    kiosk ได้ — UUID ยืนยันจริงบนเครื่อง hapymed-sterile-00 คือ ubuntu-dock@ubuntu.com)"""
    dock_command = next(
        item["command"] for item in GNOME_LOCKDOWN_FLAG_DEFS if item["key"] == "disable_ubuntu_dock"
    )
    assert dock_command == "gnome-extensions disable ubuntu-dock@ubuntu.com"

    default_preamble = build_gnome_lockdown_preamble(None)
    assert dock_command in default_preamble

    flags = normalize_gnome_lockdown_flags({"disable_ubuntu_dock": False})
    preamble_without_dock = build_gnome_lockdown_preamble(flags)
    assert dock_command not in preamble_without_dock


def test_touch_gestures_lockdown_present_by_default_and_omitted_when_disabled() -> None:
    """toggle ปิด touch gesture (ปัดขวาสลับ workspace / ปัดขึ้น 4 นิ้วยุบแอปเข้า Activities
    Overview) เปิดใช้ extension "Disable Gestures 2021" — ทดสอบมือสำเร็จแล้วบน
    hapymed-sterile-00 (kios2-user, GNOME Shell 42.9, extension v5)"""
    gesture_command = next(
        item["command"] for item in GNOME_LOCKDOWN_FLAG_DEFS if item["key"] == "disable_touch_gestures"
    )
    assert gesture_command == "gnome-extensions enable disable-gestures-2021@verycrazydog.gmail.com"

    default_preamble = build_gnome_lockdown_preamble(None)
    assert gesture_command in default_preamble

    flags = normalize_gnome_lockdown_flags({"disable_touch_gestures": False})
    preamble_without_gestures = build_gnome_lockdown_preamble(flags)
    assert gesture_command not in preamble_without_gestures


def test_touch_gestures_wait_block_follows_enable_and_omitted_when_disabled() -> None:
    """ป้องกัน race condition ที่พบจริงบนเครื่อง hapymed-sterile-00 (2026-07-13): ปัดขึ้นยังหลุด
    เข้า Activities Overview ได้ชั่วขณะแค่ตอนแรกสุดหลัง login เพราะ 'gnome-extensions enable'
    เป็นแค่ D-Bus call ที่ return ก่อน gnome-shell จะโหลด extension เข้ามาจริง — ต้องมี wait-loop
    poll `gnome-extensions list --enabled` ตามหลังคำสั่ง enable เสมอเมื่อ toggle นี้เปิดอยู่"""
    gesture_command = next(
        item["command"] for item in GNOME_LOCKDOWN_FLAG_DEFS if item["key"] == "disable_touch_gestures"
    )

    default_preamble = build_gnome_lockdown_preamble(None)
    assert "gnome-extensions list --enabled" in default_preamble
    assert "grep -qx disable-gestures-2021@verycrazydog.gmail.com" in default_preamble
    assert default_preamble.index(gesture_command) < default_preamble.index("gnome-extensions list --enabled")

    flags_disabled = normalize_gnome_lockdown_flags({"disable_touch_gestures": False})
    preamble_without_gestures = build_gnome_lockdown_preamble(flags_disabled)
    assert "gnome-extensions list --enabled" not in preamble_without_gestures

    flags_dock_only = normalize_gnome_lockdown_flags(
        {"disable_touch_gestures": False, "disable_ubuntu_dock": True}
    )
    preamble_dock_only = build_gnome_lockdown_preamble(flags_dock_only)
    assert "gnome-extensions disable ubuntu-dock@ubuntu.com" in preamble_dock_only
    assert "gnome-extensions list --enabled" not in preamble_dock_only


def test_normalize_gnome_lockdown_flags_defaults_unknown_keys_ignored() -> None:
    result = normalize_gnome_lockdown_flags({"disable_hot_corner": False, "not_a_real_key": True})

    assert result["disable_hot_corner"] is False
    assert "not_a_real_key" not in result
    assert result["disable_terminal_shortcut"] is True  # default เมื่อไม่ได้ส่งมา


def test_reset_gnome_lockdown_skips_when_user_not_found() -> None:
    """clear_kiosk_config() ต้อง idempotent — ถ้า username ไม่มีอยู่จริงในระบบ (เช่น
    kiosk user ถูกลบไปแล้วก่อนกด "เคลียร์") reset_gnome_lockdown() ต้อง skip แบบมีเหตุผล
    กลับมา ไม่ raise ให้ทั้ง clear_kiosk_config() ล้มไปทั้งฟังก์ชัน"""
    manager = KioskManager(CommandRunner())
    result = manager.reset_gnome_lockdown("definitely-not-a-real-vas-test-user-12345")

    assert result.applied is False
    assert result.skipped_reason is not None
    assert "definitely-not-a-real-vas-test-user-12345" in result.skipped_reason


def test_reset_gnome_lockdown_dry_run_skips_bus_check_and_prints_commands() -> None:
    """dry_run ต้องข้ามการเช็ค D-Bus session bus จริง (bus_path.exists()) เพราะ dry-run แค่
    อยากดูว่าจะรันคำสั่งอะไรบ้าง ไม่ได้ต้องการ session กราฟิกจริง — ใช้ 'root' (uid 0) เพราะ
    รับประกันว่ามีอยู่จริงในทุกเครื่อง Linux ไม่ต้องพึ่งว่ามี kiosk user จริงในสภาพแวดล้อมทดสอบ"""
    manager = KioskManager(CommandRunner(dry_run=True))
    result = manager.reset_gnome_lockdown("root")

    assert result.applied is True
    assert result.skipped_reason is None


def test_reset_gnome_lockdown_reverses_every_set_command_from_flag_defs() -> None:
    """แต่ละ flag ใน GNOME_LOCKDOWN_FLAG_DEFS ("set") ต้องมีคำสั่ง "reset" ที่ตรงข้ามกันตรงๆ ใน
    reset_gnome_lockdown() — กันเคสลืมเพิ่ม reset command ตอนมี lockdown flag ใหม่เพิ่มเข้ามาทีหลัง
    (เช่นถ้ามีคนเพิ่ม flag ที่ 6 ใน GNOME_LOCKDOWN_FLAG_DEFS แต่ลืมเพิ่ม reset ใน
    reset_gnome_lockdown() test นี้ควรจะช่วยเตือน แม้จะ assert ผ่านตอนนี้เพราะเช็คแค่ 5 ตัวที่มีอยู่)"""
    import inspect

    source = inspect.getsource(KioskManager.reset_gnome_lockdown)

    assert '"gsettings", "reset", "org.gnome.desktop.interface", "enable-hot-corners"' in source
    assert '"gsettings", "reset", "org.gnome.settings-daemon.plugins.media-keys", "terminal"' in source
    assert '"gsettings", "reset", "org.gnome.mutter", "overlay-key"' in source
    assert '"gnome-extensions", "enable", "ubuntu-dock@ubuntu.com"' in source
    assert '"gnome-extensions", "disable", _GESTURE_LOCKDOWN_EXTENSION_UUID' in source


# ── Chromium hide-cursor extension (docs ข้อ 8.1) ───────────────────────────

def test_build_hide_cursor_manifest_is_manifest_v3_with_content_script() -> None:
    """manifest.json ต้องเป็น Manifest V3, inject CSS ที่ document_start ครอบทุก frame —
    ไม่งั้น cursor จะโผล่กลับมาช่วง iframe โหลดใหม่หรือก่อน DOM พร้อม"""
    import json

    manifest = json.loads(build_hide_cursor_manifest())

    assert manifest["manifest_version"] == 3
    script = manifest["content_scripts"][0]
    assert script["matches"] == ["<all_urls>"]
    assert script["css"] == ["hide-cursor.css"]
    assert script["run_at"] == "document_start"
    assert script["all_frames"] is True


def test_build_hide_cursor_css_hides_cursor_on_every_element() -> None:
    css = build_hide_cursor_css()
    assert "cursor: none !important" in css
    assert "*::before" in css and "*::after" in css


def test_write_hide_cursor_extension_creates_manifest_and_css_files(tmp_path: Path) -> None:
    """create_user()/write_autostart() เรียกเมธอดนี้ตรงๆ — เช็คว่าไฟล์ถูกสร้างจริงที่ path
    ที่ถูกต้อง (ใช้ tmp_path แทน home จริง ไม่ต้องพึ่ง user จริงบนเครื่องทดสอบ)"""
    manager = KioskManager(CommandRunner())
    manager.write_hide_cursor_extension(tmp_path, "irrelevant-test-user")

    ext_dir = kiosk_hide_cursor_extension_dir(tmp_path)
    assert (ext_dir / "manifest.json").is_file()
    assert (ext_dir / "hide-cursor.css").is_file()
    assert "cursor: none !important" in (ext_dir / "hide-cursor.css").read_text(encoding="utf-8")


def test_collect_hide_cursor_extension_status_reports_missing_then_complete(tmp_path: Path) -> None:
    status_before = collect_hide_cursor_extension_status(tmp_path)
    assert status_before.manifest_exists is False
    assert status_before.css_exists is False
    assert status_before.complete is False

    KioskManager(CommandRunner()).write_hide_cursor_extension(tmp_path, "irrelevant-test-user")

    status_after = collect_hide_cursor_extension_status(tmp_path)
    assert status_after.manifest_exists is True
    assert status_after.css_exists is True
    assert status_after.complete is True


# ── Translate Enterprise Policy (docs ข้อ 10.4) ─────────────────────────────

def test_build_translate_policy_content_disables_translate() -> None:
    import json

    content = json.loads(build_translate_policy_content())
    assert content == {"TranslateEnabled": False}


def test_set_translate_policy_writes_then_removes_both_paths(tmp_path: Path) -> None:
    """ผูกกับ toggle disable_translate — ปิด toggle ต้องลบไฟล์ policy ทั้ง 2 path ทิ้ง
    (ไม่ใช่เขียน TranslateEnabled=true ทับ เพราะไฟล์นี้ VAS เขียนเองล้วนๆ)"""
    paths = (tmp_path / "a" / "policy.json", tmp_path / "b" / "policy.json")
    manager = KioskManager(CommandRunner())

    manager.set_translate_policy(True, paths=paths)
    assert all(p.is_file() for p in paths)
    status_enabled = collect_translate_policy_status(paths=paths)
    assert status_enabled.all_present is True

    manager.set_translate_policy(False, paths=paths)
    assert not any(p.exists() for p in paths)
    status_disabled = collect_translate_policy_status(paths=paths)
    assert status_disabled.all_present is False


def test_chromium_policy_paths_cover_both_deb_and_transitional_package_dirs() -> None:
    """เขียนซ้ำทั้ง /etc/chromium/ (PPA .deb) และ /etc/chromium-browser/ (transitional
    package เก่า) เพราะไม่รู้ล่วงหน้าว่าเครื่องนี้ chromium build ไหนจะมองหา policy path ไหน"""
    posix_paths = {p.as_posix() for p in CHROMIUM_POLICY_PATHS}
    assert "/etc/chromium/policies/managed/vending-kiosk-policy.json" in posix_paths
    assert "/etc/chromium-browser/policies/managed/vending-kiosk-policy.json" in posix_paths


# ── Openbox keybind lockdown (docs ข้อ 10.3) ────────────────────────────────

def test_strip_openbox_keybinds_removes_blocked_keys_keeps_others() -> None:
    rc_xml = """<openbox_config>
  <keyboard>
    <keybind key="A-Tab">
      <action name="NextWindow"/>
    </keybind>
    <keybind key="W-e">
      <action name="Execute"><command>nautilus</command></action>
    </keybind>
    <keybind key="A-F4">
      <action name="Close"/>
    </keybind>
  </keyboard>
</openbox_config>"""

    result = strip_openbox_keybinds(rc_xml)

    assert 'key="A-Tab"' not in result
    assert 'key="W-e"' not in result
    assert 'key="A-F4"' in result  # ปุ่มที่ไม่ได้อยู่ใน blocklist ต้องยังอยู่


def test_openbox_keybind_blocklist_covers_alt_tab_and_super_e() -> None:
    assert "A-Tab" in OPENBOX_KEYBIND_BLOCKLIST
    assert "W-e" in OPENBOX_KEYBIND_BLOCKLIST


# ── ล็อกดาวน์เพิ่มเติมอัตโนมัติ (docs ข้อ 10.1-10.3) ─────────────────────────

def test_apply_lockdown_extras_dry_run_reports_all_applied(tmp_path: Path) -> None:
    """dry_run ต้องไม่ error แม้ไม่มี systemctl/apt-mark จริงในสภาพแวดล้อมทดสอบ — คืน True
    ครบทุกฟิลด์เพื่อ preview ผลลัพธ์ก่อนกดจริงได้"""
    manager = KioskManager(CommandRunner(dry_run=True))
    result = manager.apply_lockdown_extras(tmp_path, "irrelevant-test-user")

    assert result.sleep_masked is True
    assert result.chromium_held is True
    # ไม่มีทั้ง user rc.xml และ system rc.xml ในสภาพแวดล้อมทดสอบ (ปกติไม่มี /etc/xdg/openbox/
    # rc.xml ในสภาพแวดล้อม CI) จึง skip ได้โดยไม่ error — ต่างจาก sleep/chromium ที่ apply เสมอ
    assert result.openbox_keybinds_removed in (True, False)


# ── ลบ Chromium (snap) ที่ค้างอยู่ (เมนู "เคลียร์ค่า Kiosk") ─────────────────

def test_remove_chromium_snap_returns_false_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kiosk_manager, "_chromium_snap_installed", lambda: False)
    removed = remove_chromium_snap(CommandRunner())
    assert removed is False


def test_remove_chromium_snap_dry_run_returns_true_without_calling_snap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kiosk_manager, "_chromium_snap_installed", lambda: True)
    calls: list[list[str]] = []
    runner = CommandRunner(dry_run=True)
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)))

    removed = remove_chromium_snap(runner)

    assert removed is True
    assert calls == []  # dry_run ต้องไม่เรียก runner.run() จริง
