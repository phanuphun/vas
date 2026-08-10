"""Tests for features.qr.payload.build_scan_body() -- the shared wire-payload builder used by
both Webhook (features/qr/webhook.py) and MQTT (features/mqtt/client.py) so the two sinks no
longer send two different shapes for the same scan (webhook used to use scan/ts/source, mqtt
used data/timestamp with no source at all). Format matches qr500_reader.payload.build_scan_body()
of the sibling qr500-reader project field-for-field, except VAS sends both "scan" and "data"
(same value, "data" is an alias for "scan") and no "source" field -- see CHANGELOG.md."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features.qr.payload import UNDEFINED, build_scan_body


def _base_event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "scan": "1234567890",
        "device": "/dev/hidraw0",
        "ts": "2026-07-27T11:40:18Z",
        "raw_keycode": None,
        "raw_report": None,
        "read_mode": None,
        "scan_source": None,
        "rfid_uid": None,
    }
    event.update(overrides)
    return event


def test_build_scan_body_no_source_field() -> None:
    """VAS เดิมเคยใส่ "source": "zkteco-qr500" เอง -- ตัดออกแล้วเพื่อให้ตรงกับ qr500-reader"""
    body = build_scan_body(_base_event())
    assert "source" not in body


def test_build_scan_body_has_scan_and_data_alias() -> None:
    """qr500-reader ใช้ "data" -- VAS คงชื่อเดิม "scan" ไว้ และเพิ่ม "data" เป็น alias ค่าเดียวกัน
    เพื่อให้ downstream consumer ที่ยึด schema ของ qr500-reader ใช้งานได้ด้วยโดยไม่ต้องแก้"""
    body = build_scan_body(_base_event(scan="hello-world"))
    assert body["scan"] == "hello-world"
    assert body["data"] == "hello-world"


def test_build_scan_body_hidraw_mode() -> None:
    event = _base_event(
        read_mode="hidraw",
        raw_keycode=[30, 48, 46],
        raw_report=["a1000000041e00000000", "a1000000041e00000001"],
    )
    body = build_scan_body(event)
    assert body["device"] == "/dev/hidraw0"
    assert body["mode"] == "full"
    assert body["read_mode"] == "hidraw"
    assert body["raw_keycode"] == [30, 48, 46]
    assert body["raw_report"] == ["a1000000041e00000000", "a1000000041e00000001"]
    assert body["raw_bytes"] == UNDEFINED  # hidraw ไม่มี concept ของ raw serial buffer
    assert body["scan_source"] == UNDEFINED  # แยก RFID/QR ไม่ได้เลยในโหมด hidraw
    assert body["rfid_uids"] == UNDEFINED
    assert body["timestamp"] == "2026-07-27T11:40:18Z"


def test_build_scan_body_evdev_mode_has_no_raw_report_or_raw_bytes() -> None:
    """evdev มี raw_keycode (scancode) แต่ไม่มี raw_report เลย (ต่างจาก hidraw)"""
    event = _base_event(read_mode="evdev", raw_keycode=[2, 3, 4], raw_report=None)
    body = build_scan_body(event)
    assert body["read_mode"] == "evdev"
    assert body["raw_keycode"] == [2, 3, 4]
    assert body["raw_report"] == UNDEFINED
    assert body["raw_bytes"] == UNDEFINED


def test_build_scan_body_serial_mode_qr() -> None:
    event = _base_event(
        device="/dev/zkteco-qr500-serial",
        read_mode="serial",
        raw_keycode=None,
        raw_report=["a5160aff2d3634633264"],  # SerialQrReaderThread เก็บเป็น [hex ทั้งก้อน]
        scan_source="QR_CODE",
        rfid_uid=None,
    )
    body = build_scan_body(event)
    assert body["read_mode"] == "serial"
    assert body["raw_keycode"] == UNDEFINED  # serial ไม่มี HID keycode concept เลย
    assert body["raw_report"] == UNDEFINED  # ไม่ใช่ hidraw -- ใช้ raw_bytes แทน
    assert body["raw_bytes"] == "a5160aff2d3634633264"
    assert body["scan_source"] == "QR_CODE"
    assert body["rfid_uids"] == UNDEFINED


def test_build_scan_body_serial_mode_rfid() -> None:
    event = _base_event(
        device="/dev/zkteco-qr500-serial",
        read_mode="serial",
        raw_report=["0264010900b3e125fdae"],
        scan="83F638F5",
        scan_source="RFID",
        rfid_uid=["83F638F5"],
    )
    body = build_scan_body(event)
    assert body["scan"] == "83F638F5"
    assert body["scan_source"] == "RFID"
    assert body["rfid_uids"] == ["83F638F5"]
    assert body["raw_bytes"] == "0264010900b3e125fdae"


def test_build_scan_body_missing_read_mode_is_undefined() -> None:
    """read_mode=None (ไม่ควรเกิดจริงเพราะทุก reader class ตั้งค่าคงที่เสมอ แต่กันเหนียวไว้)"""
    body = build_scan_body(_base_event(read_mode=None))
    assert body["read_mode"] == UNDEFINED
    assert body["raw_report"] == UNDEFINED
    assert body["raw_bytes"] == UNDEFINED
