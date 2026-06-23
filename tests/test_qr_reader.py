"""Tests for qr_reader module and QR-related CLI/status functions."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qr_reader import (
    QrConfig,
    decode_hid_report,
    find_zkteco_hidraw_devices,
    load_qr_config,
    save_qr_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(modifier: int = 0, keycodes: list | None = None) -> bytes:
    """Build a 64-byte HID keyboard report."""
    keycodes = keycodes or []
    buf = [0] * 64
    buf[0] = modifier
    for i, kc in enumerate(keycodes[:6]):
        buf[2 + i] = kc
    return bytes(buf)


# ---------------------------------------------------------------------------
# find_zkteco_hidraw_devices
# ---------------------------------------------------------------------------

ZKTECO_UEVENT = "HID_ID=0003:00000416:00005020\nHID_NAME=ZKTeco QR500-BM\n"
OTHER_UEVENT = "HID_ID=0003:0000046D:0000C52B\nHID_NAME=Logitech Keyboard\n"


def test_find_zkteco_hidraw_devices_returns_path_when_device_found() -> None:
    uevent_paths = ["/sys/class/hidraw/hidraw0/device/uevent"]

    with patch("qr_reader.glob.glob", return_value=uevent_paths):
        with patch("qr_reader.Path.read_text", return_value=ZKTECO_UEVENT):
            result = find_zkteco_hidraw_devices()

    assert result == ["/dev/hidraw0"]


def test_find_zkteco_hidraw_devices_returns_empty_when_no_zkteco() -> None:
    uevent_paths = ["/sys/class/hidraw/hidraw0/device/uevent"]

    with patch("qr_reader.glob.glob", return_value=uevent_paths):
        with patch("qr_reader.Path.read_text", return_value=OTHER_UEVENT):
            result = find_zkteco_hidraw_devices()

    assert result == []


def test_find_zkteco_hidraw_devices_returns_empty_when_no_hidraw_dir() -> None:
    with patch("qr_reader.glob.glob", return_value=[]):
        result = find_zkteco_hidraw_devices()

    assert result == []


def test_find_zkteco_hidraw_devices_skips_unreadable_uevent() -> None:
    uevent_paths = [
        "/sys/class/hidraw/hidraw0/device/uevent",
        "/sys/class/hidraw/hidraw1/device/uevent",
    ]
    call_count = [0]

    def fake_read_text(self, encoding="utf-8"):
        call_count[0] += 1
        if call_count[0] == 1:
            raise OSError("permission denied")
        return ZKTECO_UEVENT

    with patch("qr_reader.glob.glob", return_value=uevent_paths):
        with patch("qr_reader.Path.read_text", fake_read_text):
            result = find_zkteco_hidraw_devices()

    assert result == ["/dev/hidraw1"]


def test_find_zkteco_hidraw_devices_returns_multiple_when_several_found() -> None:
    uevent_paths = [
        "/sys/class/hidraw/hidraw0/device/uevent",
        "/sys/class/hidraw/hidraw1/device/uevent",
    ]

    with patch("qr_reader.glob.glob", return_value=uevent_paths):
        with patch("qr_reader.Path.read_text", return_value=ZKTECO_UEVENT):
            result = find_zkteco_hidraw_devices()

    assert result == ["/dev/hidraw0", "/dev/hidraw1"]


# ---------------------------------------------------------------------------
# decode_hid_report
# ---------------------------------------------------------------------------

def test_decode_hid_report_lowercase_letter() -> None:
    report = _make_report(modifier=0, keycodes=[4])  # keycode 4 -> 'a'
    assert decode_hid_report(report) == "a"


def test_decode_hid_report_uppercase_with_left_shift() -> None:
    report = _make_report(modifier=0x02, keycodes=[4])  # left shift + keycode 4 -> 'A'
    assert decode_hid_report(report) == "A"


def test_decode_hid_report_enter_keycode_excluded() -> None:
    # keycode 40 is Enter -- must NOT appear in returned string
    report = _make_report(modifier=0, keycodes=[40])
    assert decode_hid_report(report) == ""


def test_decode_hid_report_digit_no_shift() -> None:
    report = _make_report(modifier=0, keycodes=[30])  # '1'
    assert decode_hid_report(report) == "1"


def test_decode_hid_report_digit_with_shift() -> None:
    report = _make_report(modifier=0x02, keycodes=[30])  # '!'
    assert decode_hid_report(report) == "!"


def test_decode_hid_report_all_zeros_returns_empty() -> None:
    report = bytes(64)
    assert decode_hid_report(report) == ""


def test_decode_hid_report_multiple_keycodes_combined() -> None:
    # keycodes 4=a, 5=b, 6=c (no shift)
    report = _make_report(modifier=0, keycodes=[4, 5, 6])
    assert decode_hid_report(report) == "abc"


def test_decode_hid_report_right_shift_modifier() -> None:
    # right shift mask = 0x20
    report = _make_report(modifier=0x20, keycodes=[4])
    assert decode_hid_report(report) == "A"


def test_decode_hid_report_unknown_keycode_skipped() -> None:
    # keycode 200 is not in any map; keycode 4 = 'a'
    report = _make_report(modifier=0, keycodes=[200, 4])
    assert decode_hid_report(report) == "a"


def test_decode_hid_report_too_short_returns_empty() -> None:
    assert decode_hid_report(b"\x00\x00") == ""


# Regression tests for corrected keycode map (46=equals, 49=backslash, 56=slash)

def test_decode_hid_report_equals_sign() -> None:
    """Keycode 46 (HID 0x2E) unshifted → '='"""
    report = bytearray(64)
    report[0] = 0x00   # no modifier
    report[2] = 46
    assert decode_hid_report(bytes(report)) == "="


def test_decode_hid_report_plus_sign() -> None:
    """Keycode 46 with shift → '+'"""
    report = bytearray(64)
    report[0] = 0x02   # left shift
    report[2] = 46
    assert decode_hid_report(bytes(report)) == "+"


def test_decode_hid_report_forward_slash() -> None:
    """Keycode 56 (HID 0x38) unshifted → '/'"""
    report = bytearray(64)
    report[0] = 0x00
    report[2] = 56
    assert decode_hid_report(bytes(report)) == "/"


def test_decode_hid_report_question_mark() -> None:
    """Keycode 56 with shift → '?'"""
    report = bytearray(64)
    report[0] = 0x02
    report[2] = 56
    assert decode_hid_report(bytes(report)) == "?"


def test_decode_hid_report_backslash() -> None:
    """Keycode 49 (HID 0x31) unshifted → '\\'"""
    report = bytearray(64)
    report[0] = 0x00
    report[2] = 49
    assert decode_hid_report(bytes(report)) == "\\"


def test_decode_hid_report_pipe() -> None:
    """Keycode 49 with shift → '|'"""
    report = bytearray(64)
    report[0] = 0x02
    report[2] = 49
    assert decode_hid_report(bytes(report)) == "|"


def test_decode_hid_report_url_string() -> None:
    """QR codes with URLs must round-trip correctly (/, =, ?)"""
    # Simulate: "a/b=c?" — keycodes: a=4, /=56, b=5, ==46, c=6, shift+/=?
    # keycode slots: report[2..7] = [4, 56, 5, 46, 6, 0]  — one report per group of keys
    # In practice the scanner sends one keycode per report, but decode_hid_report
    # handles 6 keycodes per 64-byte report when they're present simultaneously.
    report = bytearray(64)
    report[2] = 4   # a
    report[3] = 56  # /
    report[4] = 5   # b
    report[5] = 46  # =
    report[6] = 6   # c
    assert decode_hid_report(bytes(report)) == "a/b=c"


# ---------------------------------------------------------------------------
# load_qr_config / save_qr_config
#
# qr_reader.load_qr_config / save_qr_config do lazy `from config import qr_config_path`
# so the correct patch target is "config.qr_config_path" (the function in the
# config module that is imported at call time).
# ---------------------------------------------------------------------------

def test_load_qr_config_returns_defaults_when_file_missing() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.read_text.side_effect = OSError("no such file")

    with patch("config.qr_config_path", return_value=fake_path):
        config = load_qr_config()

    assert config.device_path is None


def test_load_qr_config_returns_device_path_from_file() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.read_text.return_value = json.dumps({"device_path": "/dev/hidraw0"})

    with patch("config.qr_config_path", return_value=fake_path):
        config = load_qr_config()

    assert config.device_path == "/dev/hidraw0"


def test_load_qr_config_returns_defaults_on_invalid_json() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.read_text.return_value = "not valid json{"

    with patch("config.qr_config_path", return_value=fake_path):
        config = load_qr_config()

    assert config.device_path is None


def test_load_qr_config_returns_defaults_when_json_not_dict() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.read_text.return_value = json.dumps([1, 2, 3])

    with patch("config.qr_config_path", return_value=fake_path):
        config = load_qr_config()

    assert config.device_path is None


def test_save_qr_config_writes_correct_json() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.parent = MagicMock()
    fake_path.write_text = MagicMock()

    with patch("config.qr_config_path", return_value=fake_path):
        save_qr_config(QrConfig(device_path="/dev/hidraw1"))

    fake_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    written = fake_path.write_text.call_args[0][0]
    data = json.loads(written)
    assert data["device_path"] == "/dev/hidraw1"


def test_save_qr_config_writes_none_device_path() -> None:
    fake_path = MagicMock(spec=Path)
    fake_path.parent = MagicMock()
    fake_path.write_text = MagicMock()

    with patch("config.qr_config_path", return_value=fake_path):
        save_qr_config(QrConfig(device_path=None))

    written = fake_path.write_text.call_args[0][0]
    data = json.loads(written)
    assert data["device_path"] is None


# ---------------------------------------------------------------------------
# collect_qr_reader_status
#
# collect_qr_reader_status does:
#   from config import QR_UDEV_RULE_PATH, QR_UDEV_SIGNATURE, qr_config_path
#   from qr_reader import find_zkteco_hidraw_devices, get_reader
# so we patch config.QR_UDEV_RULE_PATH, config.qr_config_path, and the
# qr_reader functions.
# ---------------------------------------------------------------------------

def test_collect_qr_reader_status_udev_signature_present(tmp_path: Path) -> None:
    from status import collect_qr_reader_status

    udev_file = tmp_path / "99-qr500-bm.rules"
    udev_file.write_text("# managed by vas\nACTION==\"add\"\n", encoding="utf-8")

    with patch("config.QR_UDEV_RULE_PATH", udev_file):
        with patch("config.qr_config_path", return_value=tmp_path / "qr_config.json"):
            with patch("qr_reader.find_zkteco_hidraw_devices", return_value=[]):
                with patch("qr_reader.get_reader", return_value=None):
                    status = collect_qr_reader_status()

    assert status.udev_rule_exists is True
    assert status.udev_rule_has_signature is True


def test_collect_qr_reader_status_udev_file_missing(tmp_path: Path) -> None:
    from status import collect_qr_reader_status

    missing_path = tmp_path / "nonexistent.rules"

    with patch("config.QR_UDEV_RULE_PATH", missing_path):
        with patch("config.qr_config_path", return_value=tmp_path / "qr_config.json"):
            with patch("qr_reader.find_zkteco_hidraw_devices", return_value=[]):
                with patch("qr_reader.get_reader", return_value=None):
                    status = collect_qr_reader_status()

    assert status.udev_rule_exists is False
    assert status.udev_rule_has_signature is False


def test_collect_qr_reader_status_udev_exists_but_no_signature(tmp_path: Path) -> None:
    from status import collect_qr_reader_status

    udev_file = tmp_path / "99-qr500-bm.rules"
    udev_file.write_text("ACTION==\"add\"\n", encoding="utf-8")

    with patch("config.QR_UDEV_RULE_PATH", udev_file):
        with patch("config.qr_config_path", return_value=tmp_path / "qr_config.json"):
            with patch("qr_reader.find_zkteco_hidraw_devices", return_value=[]):
                with patch("qr_reader.get_reader", return_value=None):
                    status = collect_qr_reader_status()

    assert status.udev_rule_exists is True
    assert status.udev_rule_has_signature is False


def test_collect_qr_reader_status_detected_devices_propagated(tmp_path: Path) -> None:
    from status import collect_qr_reader_status

    with patch("config.QR_UDEV_RULE_PATH", tmp_path / "no.rules"):
        with patch("config.qr_config_path", return_value=tmp_path / "qr_config.json"):
            with patch("qr_reader.find_zkteco_hidraw_devices", return_value=["/dev/hidraw0"]):
                with patch("qr_reader.get_reader", return_value=None):
                    status = collect_qr_reader_status()

    assert status.detected_devices == ("/dev/hidraw0",)
    assert status.reader_running is False
    assert status.active_device is None


def test_collect_qr_reader_status_reader_running(tmp_path: Path) -> None:
    from status import collect_qr_reader_status

    mock_reader = MagicMock()
    mock_reader.is_alive.return_value = True
    mock_reader.device_path = "/dev/hidraw0"
    mock_reader.last_scan = "QR_CONTENT_ABC"

    with patch("config.QR_UDEV_RULE_PATH", tmp_path / "no.rules"):
        with patch("config.qr_config_path", return_value=tmp_path / "qr_config.json"):
            with patch("qr_reader.find_zkteco_hidraw_devices", return_value=["/dev/hidraw0"]):
                with patch("qr_reader.get_reader", return_value=mock_reader):
                    status = collect_qr_reader_status()

    assert status.reader_running is True
    assert status.active_device == "/dev/hidraw0"
    assert status.last_scan == "QR_CONTENT_ABC"


# ---------------------------------------------------------------------------
# CLI: vas qr status
# ---------------------------------------------------------------------------

def test_cli_qr_status_exits_zero(capsys: Any) -> None:
    from cli import main

    with patch("config.QR_UDEV_RULE_PATH", Path("/nonexistent/99-qr.rules")):
        with patch("config.qr_config_path", return_value=Path("/nonexistent/qr_config.json")):
            with patch("qr_reader.glob.glob", return_value=[]):
                with patch("qr_reader.get_reader", return_value=None):
                    exit_code = main(["qr", "status"])

    assert exit_code == 0


def test_cli_qr_status_output_contains_qr_section(capsys: Any) -> None:
    from cli import main

    with patch("config.QR_UDEV_RULE_PATH", Path("/nonexistent/99-qr.rules")):
        with patch("config.qr_config_path", return_value=Path("/nonexistent/qr_config.json")):
            with patch("qr_reader.glob.glob", return_value=[]):
                with patch("qr_reader.get_reader", return_value=None):
                    main(["qr", "status"])

    output = capsys.readouterr().out
    assert "QR" in output
