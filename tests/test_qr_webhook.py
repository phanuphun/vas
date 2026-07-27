"""Tests for features.qr.webhook -- HTTP retry/backoff logic (send_webhook_request) and the
async queue-based WebhookDispatcherThread that actually fires the webhook integration when a
QR/RFID scan comes in (previously the "Webhook" card in the UI only saved config, nothing ever
sent a real request -- see CHANGELOG.md)."""
from __future__ import annotations

import email.message
import sys
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features.qr.webhook import (
    DEFAULT_RETRY_STATUS_CODES,
    WebhookDispatcherThread,
    send_webhook_request,
)


# ---------------------------------------------------------------------------
# send_webhook_request -- retry + exponential backoff
# ---------------------------------------------------------------------------

def _fake_response(status: int):
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_send_webhook_request_success_first_try() -> None:
    with patch("urllib.request.urlopen", return_value=_fake_response(200)) as mock_open:
        with patch("time.sleep") as mock_sleep:
            ok, status, error = send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 3, {"scan": "abc"},
            )
    assert ok is True
    assert status == 200
    assert error is None
    mock_open.assert_called_once()
    mock_sleep.assert_not_called()


def test_send_webhook_request_retries_on_retryable_status_then_succeeds() -> None:
    responses = [
        urllib.error.HTTPError("url", 503, "Service Unavailable", email.message.Message(), None),
        _fake_response(200),
    ]

    def _urlopen_side_effect(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("urllib.request.urlopen", side_effect=_urlopen_side_effect) as mock_open:
        with patch("time.sleep") as mock_sleep:
            ok, status, _error = send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 3, {"scan": "abc"},
            )
    assert ok is True
    assert status == 200
    assert mock_open.call_count == 2
    mock_sleep.assert_called_once()  # 1 retry -> sleep ก่อน attempt ที่ 2 ครั้งเดียว


def test_send_webhook_request_non_retryable_status_stops_immediately() -> None:
    """404 ไม่อยู่ใน DEFAULT_RETRY_STATUS_CODES -- ต้องไม่ retry เลย (ยิงครั้งเดียวจบ)"""
    assert 404 not in DEFAULT_RETRY_STATUS_CODES
    err = urllib.error.HTTPError("url", 404, "Not Found", email.message.Message(), None)
    with patch("urllib.request.urlopen", side_effect=err) as mock_open:
        with patch("time.sleep") as mock_sleep:
            ok, status, error = send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 5, {"scan": "abc"},
            )
    assert ok is False
    assert status == 404
    assert error is not None and "404" in error
    mock_open.assert_called_once()
    mock_sleep.assert_not_called()


def test_send_webhook_request_exhausts_retries_on_network_error() -> None:
    err = urllib.error.URLError("Connection refused")
    with patch("urllib.request.urlopen", side_effect=err) as mock_open:
        with patch("time.sleep") as mock_sleep:
            ok, status, error = send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 3, {"scan": "abc"},
            )
    assert ok is False
    assert status is None
    assert error is not None
    assert mock_open.call_count == 3  # ครบ retry_max_attempts
    assert mock_sleep.call_count == 2  # sleep ระหว่าง attempt เท่านั้น ไม่ sleep หลัง attempt สุดท้าย


def test_send_webhook_request_network_error_no_retry_when_disabled() -> None:
    err = urllib.error.URLError("Connection refused")
    with patch("urllib.request.urlopen", side_effect=err) as mock_open:
        with patch("time.sleep") as mock_sleep:
            ok, _status, _error = send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 5, {"scan": "abc"},
                retry_on_network_error=False,
            )
    assert ok is False
    mock_open.assert_called_once()
    mock_sleep.assert_not_called()


def test_send_webhook_request_backoff_is_exponential_capped() -> None:
    err = urllib.error.URLError("timeout")
    with patch("urllib.request.urlopen", side_effect=err):
        with patch("time.sleep") as mock_sleep:
            send_webhook_request(
                "https://example.com/hook", "POST", 5.0, 4, {"scan": "abc"},
                retry_backoff_seconds=1.0, retry_max_backoff_seconds=3.0,
            )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [1.0, 2.0, 3.0]  # 1, 2, 4->capped ที่ 3


# ---------------------------------------------------------------------------
# WebhookDispatcherThread -- async queue, ต้อง publish() แบบ non-blocking เสมอ
# ---------------------------------------------------------------------------

def test_dispatcher_publish_is_non_blocking() -> None:
    d = WebhookDispatcherThread()
    start = time.monotonic()
    d.publish({"scan": "abc", "device": "/dev/ttyUSB0", "ts": "2026-07-27T00:00:00Z"})
    elapsed = time.monotonic() - start
    assert elapsed < 0.05
    assert d._queue.qsize() == 1  # ตรวจ internal queue ตรงๆ เพื่อยืนยัน enqueue จริง


def test_dispatcher_skips_send_when_integration_disabled() -> None:
    d = WebhookDispatcherThread()
    with patch("features.qr.registry.load_integrations", return_value={"webhook": {"enabled": False}}):
        with patch("features.qr.webhook.send_webhook_request") as mock_send:
            d._queue.put({"scan": "abc", "device": "/dev/hidraw0", "ts": "2026-07-27T00:00:00Z"})
            d.start()
            time.sleep(0.1)  # ให้ queue.get() ดึง item ออกไป process ก่อน
            d.stop()
            d.join(timeout=2.0)
    mock_send.assert_not_called()
    status = d.get_last_status()
    assert status["enabled"] is False


def test_dispatcher_reports_error_when_url_missing() -> None:
    d = WebhookDispatcherThread()
    with patch("features.qr.registry.load_integrations", return_value={"webhook": {"enabled": True, "url": ""}}):
        with patch("features.qr.webhook.send_webhook_request") as mock_send:
            d._queue.put({"scan": "abc", "device": "/dev/hidraw0", "ts": "2026-07-27T00:00:00Z"})
            d.start()
            time.sleep(0.1)
            d.stop()
            d.join(timeout=2.0)
    mock_send.assert_not_called()
    status = d.get_last_status()
    assert status["enabled"] is True
    assert status["connected"] is False
    assert "URL" in (status["error"] or "")


def test_dispatcher_sends_and_reports_published_status() -> None:
    d = WebhookDispatcherThread()
    integ = {"webhook": {"enabled": True, "url": "https://example.com/hook", "method": "POST", "retry": 3, "timeout_sec": 5}}
    with patch("features.qr.registry.load_integrations", return_value=integ):
        with patch("features.qr.webhook.send_webhook_request", return_value=(True, 200, None)) as mock_send:
            d._queue.put({"scan": "abc123", "device": "/dev/hidraw0", "ts": "2026-07-27T00:00:00Z"})
            d.start()
            time.sleep(0.1)
            d.stop()
            d.join(timeout=2.0)
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.args[0] == "https://example.com/hook"
    payload = call_kwargs.args[4]
    # payload มาจาก features.qr.payload.build_scan_body() -- รูปแบบเดียวกับ qr500-reader
    # (ยกเว้น "scan" แทน "data" และไม่มี "source") ดู tests/test_qr_payload.py สำหรับเทสของ
    # build_scan_body() เอง ตรงนี้แค่ยืนยันว่า dispatcher เรียกมันจริงและส่ง scan ที่ถูกต้อง
    assert payload["scan"] == "abc123"
    assert payload["device"] == "/dev/hidraw0"
    assert payload["mode"] == "full"
    assert "source" not in payload
    status = d.get_last_status()
    assert status == {"enabled": True, "connected": True, "published": True, "error": None}


def test_dispatcher_reports_error_when_send_fails() -> None:
    d = WebhookDispatcherThread()
    integ = {"webhook": {"enabled": True, "url": "https://example.com/hook"}}
    with patch("features.qr.registry.load_integrations", return_value=integ):
        with patch("features.qr.webhook.send_webhook_request", return_value=(False, 500, "HTTP 500")):
            d._queue.put({"scan": "abc", "device": "/dev/hidraw0", "ts": "2026-07-27T00:00:00Z"})
            d.start()
            time.sleep(0.1)
            d.stop()
            d.join(timeout=2.0)
    status = d.get_last_status()
    assert status["published"] is False
    assert status["error"] == "HTTP 500"
