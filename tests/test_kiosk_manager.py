from __future__ import annotations

from features.kiosk.manager import (
    CHROME_KIOSK_FLAG_DEFS,
    GNOME_LOCKDOWN_FLAG_DEFS,
    GNOME_LOCKDOWN_SIGNATURE,
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


def test_normalize_gnome_lockdown_flags_defaults_unknown_keys_ignored() -> None:
    result = normalize_gnome_lockdown_flags({"disable_hot_corner": False, "not_a_real_key": True})

    assert result["disable_hot_corner"] is False
    assert "not_a_real_key" not in result
    assert result["disable_terminal_shortcut"] is True  # default เมื่อไม่ได้ส่งมา
