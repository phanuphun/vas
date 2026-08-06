from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from core.runner import CommandRunner
from features.remote import x11vnc
from system import status as status_module
from system.status import X11vncConfig, X11vncStatus, collect_x11vnc_status

# ---------------------------------------------------------------------------
# render_service_file()
# ---------------------------------------------------------------------------

def test_render_service_file_matches_reference_template() -> None:
    """ต้องตรงกับ template ที่ user ให้มาเป๊ะๆ (docs/plans/2026-08-06-x11vnc-remote-backend-spec.md)
    — เปลี่ยนแค่ path ของ -rfbauth ให้มาจาก PASSWORD_PATH แทน hardcode"""
    text = x11vnc.render_service_file(
        listen_ip="10.8.0.56", port=5900, display=":0", user="first", home="/home/first",
    )
    lines = text.splitlines()
    assert "[Unit]" in lines
    assert "Description=x11vnc mirror service" in lines
    assert "After=multi-user.target" in lines
    assert "[Service]" in lines
    assert "Type=simple" in lines
    assert "User=first" in lines
    assert "ExecStart=/usr/bin/x11vnc -display :0 -auth /home/first/.Xauthority \\" in lines
    assert "  -forever -loop -noxdamage -repeat -shared \\" in lines
    assert f"  -rfbauth {x11vnc.PASSWORD_PATH} -rfbport 5900 \\" in lines
    assert "  -listen 10.8.0.56" in lines
    assert "Restart=on-failure" in lines
    assert "RestartSec=5" in lines
    assert "[Install]" in lines
    assert "WantedBy=multi-user.target" in lines


# ---------------------------------------------------------------------------
# apply_setup() — validation (ต้องเช็คก่อนแตะ filesystem เสมอ ไม่ว่า dev-mode หรือไม่)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "listen_ip,port,display,user",
    [
        ("", 5900, ":0", "first"),              # listen_ip ว่าง
        ("not-an-ip", 5900, ":0", "first"),      # listen_ip ผิดฟอร์แมต
        ("10.8.0.56", 0, ":0", "first"),         # port ต่ำไป
        ("10.8.0.56", 70000, ":0", "first"),     # port สูงไป
        ("10.8.0.56", 5900, "0", "first"),       # display ไม่ขึ้นต้นด้วย ":"
        ("10.8.0.56", 5900, ":0", ""),           # user ว่าง
    ],
)
def test_apply_setup_rejects_invalid_input_without_touching_filesystem(
    monkeypatch: pytest.MonkeyPatch, listen_ip: str, port: int, display: str, user: str,
) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    runner = CommandRunner(dry_run=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)))

    fake_path = Mock()
    with patch("features.remote.x11vnc.SERVICE_PATH", fake_path):
        ok, message = x11vnc.apply_setup(runner, listen_ip, port, display, user)

    assert ok is False
    assert message
    assert calls == []
    fake_path.write_text.assert_not_called()


def test_apply_setup_unknown_user_returns_error_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    runner = CommandRunner(dry_run=True)
    with patch("features.remote.x11vnc._resolve_home", side_effect=ValueError("ไม่พบ user 'ghost' ในเครื่องนี้")):
        ok, message = x11vnc.apply_setup(runner, "10.8.0.56", 5900, ":0", "ghost")
    assert ok is False
    assert "ghost" in message


# ---------------------------------------------------------------------------
# apply_setup() — dev-mode (VAS_DEV_FAKE_INSTALLED=1) ต้องไม่แตะ filesystem/systemctl เลย
# ---------------------------------------------------------------------------

def test_apply_setup_dev_mode_succeeds_without_writing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    runner = CommandRunner(dry_run=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)))
    fake_path = Mock()

    with patch("features.remote.x11vnc.SERVICE_PATH", fake_path):
        ok, message = x11vnc.apply_setup(runner, "10.8.0.56", 5900, ":0", "first")

    assert ok is True
    assert "dev-mode" in message
    assert calls == []
    fake_path.write_text.assert_not_called()
    fake_path.chmod.assert_not_called()


# ---------------------------------------------------------------------------
# apply_setup() — real mode (mock filesystem + runner ทั้งคู่ ไม่แตะระบบจริง)
# ---------------------------------------------------------------------------

def test_apply_setup_real_mode_writes_unit_and_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    runner = CommandRunner(dry_run=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)))
    fake_path = Mock()

    with patch("features.remote.x11vnc.SERVICE_PATH", fake_path), \
         patch("features.remote.x11vnc._resolve_home", return_value="/home/first"):
        ok, message = x11vnc.apply_setup(runner, "10.8.0.56", 5900, ":0", "first")

    assert ok is True
    assert message
    fake_path.write_text.assert_called_once()
    written_text = fake_path.write_text.call_args[0][0]
    assert "User=first" in written_text
    assert "-auth /home/first/.Xauthority" in written_text
    fake_path.chmod.assert_called_once_with(0o644)
    assert calls == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "x11vnc.service"],
    ]


# ---------------------------------------------------------------------------
# service_action()
# ---------------------------------------------------------------------------

def test_service_action_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        x11vnc.service_action(CommandRunner(dry_run=True), "delete-everything")


def test_service_action_dev_mode_does_not_call_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    runner = CommandRunner(dry_run=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)))

    result = x11vnc.service_action(runner, "start")

    assert result.returncode == 0
    assert calls == []


@pytest.mark.parametrize("action", x11vnc.VALID_SERVICE_ACTIONS)
def test_service_action_real_mode_calls_systemctl(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    runner = CommandRunner(dry_run=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "run", lambda args, **kw: calls.append(list(args)) or Mock(returncode=0))

    x11vnc.service_action(runner, action)

    assert calls == [["systemctl", action, "x11vnc"]]


# ---------------------------------------------------------------------------
# set_vnc_password()
# ---------------------------------------------------------------------------

def test_set_vnc_password_rejects_empty() -> None:
    ok, message = x11vnc.set_vnc_password("")
    assert ok is False
    assert message


def test_set_vnc_password_rejects_too_short() -> None:
    ok, message = x11vnc.set_vnc_password("short")
    assert ok is False
    assert message


def test_set_vnc_password_dev_mode_does_not_call_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    with patch("features.remote.x11vnc.subprocess.run") as mock_run:
        ok, message = x11vnc.set_vnc_password("longenoughpw")
    assert ok is True
    assert "dev-mode" in message
    mock_run.assert_not_called()


def test_set_vnc_password_real_mode_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    with patch("features.remote.x11vnc.shutil.which", return_value=None):
        ok, message = x11vnc.set_vnc_password("longenoughpw")
    assert ok is False
    assert "ยังไม่ได้ติดตั้ง" in message


def test_set_vnc_password_real_mode_success_passes_password_as_literal_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    """x11vnc -storepasswd ไม่รองรับ stdin จริง (แก้บั๊กเมื่อ 2026-08-06 — ของเดิมส่ง "-" แทนรหัสผ่าน
    จริงทำให้รหัสที่เก็บกลายเป็น "-" เสมอ) ต้องส่งรหัสผ่านเป็น argument ที่ 2 ตรงๆ ถึงจะใช้งานได้จริง"""
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    fake_completed = Mock(returncode=0, stdout="", stderr="")
    fake_path = Mock()

    with patch("features.remote.x11vnc.shutil.which", return_value="/usr/bin/x11vnc"), \
         patch("features.remote.x11vnc.subprocess.run", return_value=fake_completed) as mock_run, \
         patch("features.remote.x11vnc.PASSWORD_PATH", fake_path):
        ok, _message = x11vnc.set_vnc_password("longenoughpw")

    assert ok is True
    args = mock_run.call_args.args[0]
    assert args == ["/usr/bin/x11vnc", "-storepasswd", "longenoughpw", str(fake_path)]
    assert "input" not in mock_run.call_args.kwargs  # ไม่มี stdin mode ให้ใช้ ต้องไม่ส่ง input= อีกต่อไป
    fake_path.chmod.assert_called_once_with(0o644)


# ---------------------------------------------------------------------------
# collect_x11vnc_status() / _parse_x11vnc_unit() (src/system/status.py)
# ---------------------------------------------------------------------------

def test_collect_x11vnc_status_dev_fake_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    status = collect_x11vnc_status()
    assert status.installed is True
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"
    assert status.config == X11vncConfig(listen_ip="10.8.0.56", port=5900, display=":0", user="first")
    assert status.password_set is True


def test_collect_x11vnc_status_real_mode_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    with patch("system.status.shutil.which", return_value=None), \
         patch("system.status._read_command_first_line", return_value="unknown"), \
         patch("system.status._parse_x11vnc_unit", return_value=None), \
         patch("system.status._X11VNC_PASSWORD_PATH", Mock(exists=lambda: False)):
        status = collect_x11vnc_status()
    assert status.installed is False
    assert status.version is None
    assert status.config is None
    assert status.password_set is False


def test_x11vnc_status_is_frozen_dataclass() -> None:
    status = X11vncStatus(
        installed=True, version="x11vnc 0.9.16", service_enabled="enabled", service_active="active",
        config=None, password_set=False,
    )
    with pytest.raises(Exception):
        status.installed = False  # type: ignore[misc]


def test_parse_x11vnc_unit_returns_none_when_file_missing(tmp_path: object) -> None:
    from pathlib import Path
    missing = Path(str(tmp_path)) / "does-not-exist.service"
    with patch.object(status_module, "_X11VNC_SERVICE_PATH", missing):
        assert status_module._parse_x11vnc_unit() is None


def test_parse_x11vnc_unit_reads_back_rendered_service_file(tmp_path: object) -> None:
    from pathlib import Path
    unit_path = Path(str(tmp_path)) / "x11vnc.service"
    unit_path.write_text(
        x11vnc.render_service_file(
            listen_ip="10.8.0.56", port=5900, display=":0", user="first", home="/home/first",
        ),
        encoding="utf-8",
    )
    with patch.object(status_module, "_X11VNC_SERVICE_PATH", unit_path):
        config = status_module._parse_x11vnc_unit()

    assert config == X11vncConfig(listen_ip="10.8.0.56", port=5900, display=":0", user="first")


def test_parse_x11vnc_unit_returns_none_when_format_unrecognized(tmp_path: object) -> None:
    from pathlib import Path
    unit_path = Path(str(tmp_path)) / "x11vnc.service"
    unit_path.write_text("[Unit]\nDescription=someone edited this by hand\n", encoding="utf-8")
    with patch.object(status_module, "_X11VNC_SERVICE_PATH", unit_path):
        assert status_module._parse_x11vnc_unit() is None


# ---------------------------------------------------------------------------
# Flask routes — /x11vnc, /api/x11vnc/*, /api/nav/status
#
# วางไว้ในไฟล์นี้แทน tests/test_server.py ตามที่ spec ระบุไว้เดิม เพราะ tests/test_server.py
# ปัจจุบัน collect ไม่ได้อยู่แล้ว (ModuleNotFoundError: display/status/runner/wireguard — import
# module แบบ flat top-level ที่ไม่มีอยู่จริงในโครงสร้างปัจจุบัน, pre-existing ก่อนงานนี้ ไม่เกี่ยวกับ
# x11vnc) เทสต์ในไฟล์นี้ import จาก `server` ตรงๆ ซึ่งใช้งานได้ปกติ ไม่ชนปัญหาเดียวกัน
# ---------------------------------------------------------------------------

@pytest.fixture
def flask_app(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import core.database as db

    db_file = tmp_path / "vas-test.db"
    monkeypatch.setattr(db, "db_path", lambda: db_file)
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    db.run_migrations()

    from core.auth import create_user, is_first_run
    from server import create_app

    app = create_app()
    with app.app_context():
        if is_first_run():
            create_user("root", "testpass12345", role="root")
    return app


@pytest.fixture
def admin_client(flask_app):
    client = flask_app.test_client()
    client.post("/login", data={"username": "root", "password": "testpass12345"}, follow_redirects=True)
    return client


def test_x11vnc_page_renders_ok(admin_client) -> None:
    response = admin_client.get("/x11vnc")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "vnc-unit-preview" in body
    assert "mock-up" not in body.lower()  # banner mockup ต้องถูกลบออกไปแล้วหลัง implement backend


def test_x11vnc_status_api_returns_ok(admin_client) -> None:
    response = admin_client.get("/api/x11vnc/status")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["installed"] is True  # dev-fake mode


def test_x11vnc_action_api_requires_login(flask_app) -> None:
    response = flask_app.test_client().post("/api/x11vnc/action", json={"action": "start"})
    assert response.status_code in (302, 401, 403)


def test_x11vnc_action_api_succeeds_for_admin(admin_client) -> None:
    response = admin_client.post("/api/x11vnc/action", json={"action": "start"})
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_x11vnc_action_api_rejects_unknown_action(admin_client) -> None:
    response = admin_client.post("/api/x11vnc/action", json={"action": "delete-everything"})
    assert response.status_code == 400


def test_x11vnc_apply_api_rejects_bad_ip(admin_client) -> None:
    response = admin_client.post(
        "/api/x11vnc/apply",
        json={"listen_ip": "not-an-ip", "port": 5900, "display": ":0", "user": "first"},
    )
    assert response.status_code == 400


def test_x11vnc_password_api_rejects_short_password(admin_client) -> None:
    response = admin_client.post("/api/x11vnc/password", json={"password": "short"})
    assert response.status_code == 400


def test_nav_status_api_includes_x11vnc_key(admin_client) -> None:
    response = admin_client.get("/api/nav/status")
    assert response.status_code == 200
    assert "x11vnc" in response.json["installed"]
