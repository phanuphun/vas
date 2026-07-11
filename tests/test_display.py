from pathlib import Path

from display import (
    DISPLAY_SESSION_SIGNATURE,
    XORG_TOUCHSCREEN_SIGNATURE,
    build_display_session_block,
    build_display_session_script,
    build_gdm_wayland_config,
    build_xorg_touchscreen_config,
    matrix_for_rotation,
    remove_managed_block,
    upsert_managed_block,
)


def test_matrix_for_left_rotation() -> None:
    assert matrix_for_rotation("left") == ("0", "-1", "1", "1", "0", "0", "0", "0", "1")


def test_xorg_config_includes_signature_and_touch_name() -> None:
    config = build_xorg_touchscreen_config("Vending Virtual Touchscreen", "1 0 0 0 1 0 0 0 1")

    assert XORG_TOUCHSCREEN_SIGNATURE in config
    assert 'MatchProduct "Vending Virtual Touchscreen"' in config
    assert 'Option "TransformationMatrix" "1 0 0 0 1 0 0 0 1"' in config


def test_display_session_script_includes_retry_rotation_and_mapping() -> None:
    script = build_display_session_script(
        output="Virtual1",
        touch="Vending Virtual Touchscreen",
        rotate="left",
        matrix="0 -1 1 1 0 0 0 0 1",
        x_display=":0",
        delay_seconds=5,
        retries=30,
    )

    assert "vending-auto-config: display-session-script" in script
    assert "export DISPLAY=:0" in script
    assert 'xrandr --output "$OUTPUT" --rotate "$ROTATE"' in script
    assert 'xinput set-prop "$TOUCH_DEVICE"' in script
    assert "RETRIES=30" in script


def test_display_session_block_calls_script() -> None:
    block = build_display_session_block(script_path=Path("/home/first/.config/vending/display.sh"))

    assert DISPLAY_SESSION_SIGNATURE in block
    assert "/home/first/.config/vending/display.sh &" in block


def test_gdm_wayland_disable_adds_daemon_setting() -> None:
    config = build_gdm_wayland_config("[daemon]\nAutomaticLoginEnable=true\n", enabled=False)

    assert "[daemon]\nWaylandEnable=false\nAutomaticLoginEnable=true\n" == config


def test_gdm_wayland_enable_comments_active_disable_setting() -> None:
    config = build_gdm_wayland_config("[daemon]\nWaylandEnable=false\n", enabled=True)

    assert "[daemon]\n#WaylandEnable=false\n" == config


def test_gdm_wayland_disable_creates_daemon_section_when_missing() -> None:
    config = build_gdm_wayland_config("[security]\nDisallowTCP=true\n", enabled=False)

    assert "[security]\nDisallowTCP=true\n\n[daemon]\nWaylandEnable=false\n" == config


def test_gdm_wayland_collapses_duplicate_commented_lines() -> None:
    # simulate a config file already corrupted by the old bug: repeated toggling
    # accumulated multiple #WaylandEnable=false lines. A new toggle must collapse
    # these back down to a single line instead of adding yet another one.
    existing = (
        "[daemon]\n"
        "WaylandEnable=false\n"
        "#WaylandEnable=false\n"
        "#WaylandEnable=false\n"
        "#WaylandEnable=false\n"
        "# Uncomment the line below to force the login screen to use Xorg\n"
        "#WaylandEnable=false\n"
        "\n"
        "# Enabling automatic login\n"
    )

    config = build_gdm_wayland_config(existing, enabled=False)

    assert config == (
        "[daemon]\n"
        "WaylandEnable=false\n"
        "# Uncomment the line below to force the login screen to use Xorg\n"
        "\n"
        "# Enabling automatic login\n"
    )
    assert config.count("WaylandEnable=false") == 1


def test_gdm_wayland_toggle_twice_does_not_accumulate_lines() -> None:
    # toggling enable/disable repeatedly must never grow the number of
    # WaylandEnable lines beyond one.
    config = "[daemon]\nAutomaticLoginEnable=true\n"
    for enabled in (False, True, False, True, False):
        config = build_gdm_wayland_config(config, enabled=enabled)

    assert config.count("WaylandEnable=false") == 1
    assert "AutomaticLoginEnable=true" in config


def test_upsert_managed_block_replaces_existing_block() -> None:
    old_content = (
        "before\n"
        "# vending-auto-config: display-session BEGIN\n"
        "old\n"
        "# vending-auto-config: display-session END\n"
        "after\n"
    )
    new_block = (
        "# vending-auto-config: display-session BEGIN\n"
        "new\n"
        "# vending-auto-config: display-session END\n"
    )

    content = upsert_managed_block(old_content, new_block)

    assert "before\n" in content
    assert "new\n" in content
    assert "old\n" not in content
    assert "after\n" in content


def test_remove_managed_block_removes_only_vending_block() -> None:
    old_content = (
        "before\n"
        "# vending-auto-config: display-session BEGIN\n"
        "managed\n"
        "# vending-auto-config: display-session END\n"
        "after\n"
    )

    content = remove_managed_block(old_content)

    assert "before\n" in content
    assert "after\n" in content
    assert "managed\n" not in content