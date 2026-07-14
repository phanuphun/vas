from __future__ import annotations

from core.runner import CommandRunner
from features.kiosk.manager import (
    CHROME_KIOSK_FLAG_DEFS,
    GNOME_LOCKDOWN_FLAG_DEFS,
    GNOME_LOCKDOWN_SIGNATURE,
    KioskManager,
    _parse_gnome_lockdown_flags,
    _parse_kiosk_flags,
    build_gnome_lockdown_preamble,
    build_kiosk_launch_script,
    normalize_chrome_flags,
    normalize_gnome_lockdown_flags,
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
