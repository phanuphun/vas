"""Tests for RS485 serial QR/RFID reading support (features.qr.reader) and the
scan_source/rfid_uid persistence added in database migration v4.

Uses the current package layout (features.qr.reader, core.database, core.config) --
NOT the flat "qr_reader"/"config" module names used by the stale tests/test_qr_reader.py
(that file predates the features/core/system package refactor and currently fails to
even collect -- pre-existing, unrelated to this change)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features.qr.reader import (
    QrConfig,
    SYMLINK_HIDRAW_PATH,
    SYMLINK_SERIAL_PATH,
    classify_scan_source,
    find_zkteco_serial_devices,
    _resolve_hidraw_path,
    _resolve_serial_path,
)


# ---------------------------------------------------------------------------
# classify_scan_source
# ---------------------------------------------------------------------------

def _rfid_frame(uid: bytes, addr: int = 0x64, suffix: bytes = b"\x2f\xec") -> bytes:
    assert len(uid) == 4 and len(suffix) == 2
    return bytes([0x02, addr, 0x01, 0x09, 0x00]) + uid + bytes([addr, 0x1A, 0x88, 0x39, 0x05]) + suffix


def test_classify_scan_source_qr_text() -> None:
    buf = b"a5160aff-c32f-40c5-ac58-41651e70e6b4"
    assert classify_scan_source(buf) == ("QR_CODE", None)


def test_classify_scan_source_empty_buffer_is_qr() -> None:
    assert classify_scan_source(b"") == ("QR_CODE", None)


def test_classify_scan_source_single_rfid_frame() -> None:
    frame = _rfid_frame(bytes.fromhex("83F638F5"))
    assert len(frame) == 16
    source, uids = classify_scan_source(frame)
    assert source == "RFID"
    assert uids == ["83F638F5"]


def test_classify_scan_source_multiple_rfid_frames_concatenated() -> None:
    frame1 = _rfid_frame(bytes.fromhex("83F638F5"))
    frame2 = _rfid_frame(bytes.fromhex("234949FA"))
    source, uids = classify_scan_source(frame1 + frame2)
    assert source == "RFID"
    assert uids == ["83F638F5", "234949FA"]


def test_classify_scan_source_wrong_length_falls_back_to_qr() -> None:
    # 15 bytes, not a multiple of 16 -- even though it starts with STX
    buf = bytes([0x02]) + b"x" * 14
    assert classify_scan_source(buf) == ("QR_CODE", None)


def test_classify_scan_source_multiple_of_16_but_no_stx_is_qr() -> None:
    buf = b"0123456789ABCDEF"  # 16 bytes, first byte != STX
    assert classify_scan_source(buf) == ("QR_CODE", None)


def test_classify_scan_source_one_bad_subframe_invalidates_whole_buffer() -> None:
    frame1 = _rfid_frame(bytes.fromhex("83F638F5"))
    bad_frame = b"Q" * 16  # does not start with STX
    source, uids = classify_scan_source(frame1 + bad_frame)
    assert source == "QR_CODE"
    assert uids is None


# ---------------------------------------------------------------------------
# find_zkteco_serial_devices
# ---------------------------------------------------------------------------

def test_find_zkteco_serial_devices_matches_adapter_vendor_product() -> None:
    tty_paths = ["/sys/class/tty/ttyUSB0"]

    def fake_read_text(self, encoding="utf-8"):
        name = self.name
        if name == "idVendor":
            return "0403\n"
        if name == "idProduct":
            return "6001\n"
        raise OSError("unexpected file")

    with patch("features.qr.reader.glob.glob", return_value=tty_paths):
        with patch("features.qr.reader.Path.read_text", fake_read_text):
            result = find_zkteco_serial_devices()

    assert result == ["/dev/ttyUSB0"]


def test_find_zkteco_serial_devices_skips_non_matching_adapter() -> None:
    tty_paths = ["/sys/class/tty/ttyUSB0"]

    def fake_read_text(self, encoding="utf-8"):
        if self.name == "idVendor":
            return "1234\n"
        if self.name == "idProduct":
            return "5678\n"
        raise OSError("unexpected file")

    with patch("features.qr.reader.glob.glob", return_value=tty_paths):
        with patch("features.qr.reader.Path.read_text", fake_read_text):
            result = find_zkteco_serial_devices()

    assert result == []


def test_find_zkteco_serial_devices_returns_empty_when_no_ttyusb() -> None:
    with patch("features.qr.reader.glob.glob", return_value=[]):
        assert find_zkteco_serial_devices() == []


def test_find_zkteco_serial_devices_skips_unreadable_id_files() -> None:
    with patch("features.qr.reader.glob.glob", return_value=["/sys/class/tty/ttyUSB0"]):
        with patch("features.qr.reader.Path.read_text", side_effect=OSError("no such file")):
            assert find_zkteco_serial_devices() == []


# ---------------------------------------------------------------------------
# Symlink-aware resolution (_resolve_hidraw_path / _resolve_serial_path)
# ---------------------------------------------------------------------------

def test_resolve_hidraw_path_prefers_symlink_when_present() -> None:
    with patch("features.qr.reader.os.path.exists", return_value=True):
        assert _resolve_hidraw_path() == SYMLINK_HIDRAW_PATH


def test_resolve_hidraw_path_falls_back_to_scan_when_no_symlink() -> None:
    with patch("features.qr.reader.os.path.exists", return_value=False):
        with patch("features.qr.reader.find_zkteco_hidraw_devices", return_value=["/dev/hidraw3"]):
            assert _resolve_hidraw_path() == "/dev/hidraw3"


def test_resolve_hidraw_path_returns_none_when_nothing_found() -> None:
    with patch("features.qr.reader.os.path.exists", return_value=False):
        with patch("features.qr.reader.find_zkteco_hidraw_devices", return_value=[]):
            assert _resolve_hidraw_path() is None


def test_resolve_serial_path_prefers_symlink_when_present() -> None:
    with patch("features.qr.reader.os.path.exists", return_value=True):
        assert _resolve_serial_path() == SYMLINK_SERIAL_PATH


def test_resolve_serial_path_falls_back_to_scan_when_no_symlink() -> None:
    with patch("features.qr.reader.os.path.exists", return_value=False):
        with patch("features.qr.reader.find_zkteco_serial_devices", return_value=["/dev/ttyUSB2"]):
            assert _resolve_serial_path() == "/dev/ttyUSB2"


# ---------------------------------------------------------------------------
# QrConfig.interface
# ---------------------------------------------------------------------------

def test_qrconfig_default_interface_is_usb() -> None:
    assert QrConfig().interface == "usb"


def test_qrconfig_interface_round_trip_serial() -> None:
    cfg = QrConfig.from_dict({"interface": "serial", "device_path": "/dev/ttyUSB0"})
    assert cfg.interface == "serial"
    assert cfg.to_dict()["interface"] == "serial"


def test_qrconfig_invalid_interface_falls_back_to_usb() -> None:
    cfg = QrConfig.from_dict({"interface": "bluetooth"})
    assert cfg.interface == "usb"


# ---------------------------------------------------------------------------
# start_reader() dispatch -- explicit device_path prefix routing
# ---------------------------------------------------------------------------

def test_start_reader_dispatches_serial_thread_for_ttyusb_path() -> None:
    import features.qr.reader as reader_mod

    with patch.object(reader_mod, "_reader_thread", None):
        with patch("features.qr.reader.SerialQrReaderThread") as MockSerial:
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = True
            MockSerial.return_value = mock_thread
            result = reader_mod.start_reader(device_path="/dev/ttyUSB0")

    MockSerial.assert_called_once_with(device_path="/dev/ttyUSB0")
    mock_thread.start.assert_called_once()
    assert result is mock_thread


def test_start_reader_dispatches_serial_thread_for_serial_symlink() -> None:
    import features.qr.reader as reader_mod

    with patch.object(reader_mod, "_reader_thread", None):
        with patch("features.qr.reader.SerialQrReaderThread") as MockSerial:
            mock_thread = MagicMock()
            MockSerial.return_value = mock_thread
            reader_mod.start_reader(device_path=reader_mod.SYMLINK_SERIAL_PATH)

    MockSerial.assert_called_once_with(device_path=reader_mod.SYMLINK_SERIAL_PATH)


def test_start_reader_auto_detect_uses_serial_interface_from_config() -> None:
    import features.qr.reader as reader_mod

    with patch.object(reader_mod, "_reader_thread", None):
        with patch("features.qr.reader.load_qr_config", return_value=QrConfig(interface="serial")):
            with patch("features.qr.reader._resolve_serial_path", return_value="/dev/ttyUSB5"):
                with patch("features.qr.reader.SerialQrReaderThread") as MockSerial:
                    mock_thread = MagicMock()
                    MockSerial.return_value = mock_thread
                    reader_mod.start_reader(device_path=None)

    MockSerial.assert_called_once_with(device_path="/dev/ttyUSB5")


def test_start_reader_auto_detect_serial_raises_when_nothing_found() -> None:
    import features.qr.reader as reader_mod

    with patch.object(reader_mod, "_reader_thread", None):
        with patch("features.qr.reader.load_qr_config", return_value=QrConfig(interface="serial")):
            with patch("features.qr.reader._resolve_serial_path", return_value=None):
                with pytest.raises(RuntimeError):
                    reader_mod.start_reader(device_path=None)


# ---------------------------------------------------------------------------
# database.py migration v4 -- scan_source / rfid_uid persistence
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """แยก DB connection ต่อ test -- reset thread-local connection cache ของ core.database
    เพื่อไม่ให้ test อื่นที่รันในกระบวนการเดียวกัน (thread เดียวกัน) แชร์ connection/ไฟล์เดิม"""
    import core.database as db

    db_file = tmp_path / "vas_test.db"
    monkeypatch.setattr(db, "db_path", lambda: db_file)
    if hasattr(db._local, "conn") and db._local.conn is not None:
        db._local.conn.close()
        db._local.conn = None
    db.run_migrations()
    yield db
    if hasattr(db._local, "conn") and db._local.conn is not None:
        db._local.conn.close()
        db._local.conn = None


def test_migration_v4_reaches_schema_version_4(isolated_db) -> None:
    assert isolated_db.current_schema_version() == 4


def test_log_qr_scan_persists_scan_source_and_rfid_uid(isolated_db) -> None:
    isolated_db.log_qr_scan(
        "83F638F5", device="/dev/ttyUSB0", read_mode="serial",
        scan_source="RFID", rfid_uid=["83F638F5"],
    )
    rows = isolated_db.list_qr_scans(limit=10)["rows"]
    assert len(rows) == 1
    assert rows[0]["scan_source"] == "RFID"
    assert rows[0]["rfid_uid"] == ["83F638F5"]


def test_log_qr_scan_qr_code_has_no_rfid_uid(isolated_db) -> None:
    isolated_db.log_qr_scan(
        "a5160aff-c32f-40c5-ac58-41651e70e6b4", device="/dev/ttyUSB0",
        read_mode="serial", scan_source="QR_CODE",
    )
    rows = isolated_db.list_qr_scans(limit=10)["rows"]
    assert rows[0]["scan_source"] == "QR_CODE"
    assert rows[0]["rfid_uid"] is None


def test_log_qr_scan_hidraw_scan_has_null_scan_source(isolated_db) -> None:
    """ค่าเดิม (hidraw/evdev) ไม่แยก RFID/QR ได้ -- scan_source ต้องเป็น NULL ไม่ใช่ error"""
    isolated_db.log_qr_scan("1234567890", device="/dev/hidraw0", read_mode="hidraw")
    rows = isolated_db.list_qr_scans(limit=10)["rows"]
    assert rows[0]["scan_source"] is None
    assert rows[0]["rfid_uid"] is None
