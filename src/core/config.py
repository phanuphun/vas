import re
from dataclasses import dataclass
from pathlib import Path


_FALLBACK_VERSION = "0.1.0"


def _read_pyproject_version(fallback: str) -> str:
    """อ่าน version จาก pyproject.toml (single source of truth ที่เดียวสำหรับทั้ง

    package version, CLI --version, และเวอร์ชั่นที่แสดงในหน้า "อัปเดตระบบ")

    ใช้ regex แบบเจาะจงเฉพาะ key `version` ใต้ [project] แทนการพึ่ง `tomllib`
    (Python 3.11+) เพราะเครื่องเป้าหมาย (Ubuntu 22.04 jammy) มาพร้อม Python 3.10
    เป็นค่าเริ่มต้น — pyproject.toml ถูกก็อปปี้ไปพร้อม repo ตอน self-update อยู่แล้ว
    (`shutil.copytree(source_dir, install_dir)` ใน services/updater.py) จึงมีให้
    อ่านทั้งตอน dev และตอนติดตั้งจริงที่ /opt/vending-auto-setup
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return fallback

    in_project_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project_section = stripped == "[project]"
            continue
        if in_project_section:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    return fallback


APP_VERSION = _read_pyproject_version(_FALLBACK_VERSION)


@dataclass(frozen=True)
class InstallConfig:
    node_major: int = 22
    docker_version: str | None = None
    git_version: str | None = None
    ubuntu_codename: str = "jammy"
    docker_packages: tuple[str, ...] = (
        "docker-ce",
        "docker-ce-cli",
        "containerd.io",
        "docker-buildx-plugin",
        "docker-compose-plugin",
    )


DEFAULT_CONFIG = InstallConfig()


from pathlib import Path as _Path

# ── QR reader udev rules (access + persistent symlink) ──────────────────────
#
# 3 ไฟล์แยกกัน (path ตรงกับที่ใช้งานจริงบนเครื่อง production — ดู
# .agents/skills/zkteco-500 และ CHANGELOG.md):
#   1. 99-qr500-bm.rules            — MODE/GROUP ให้ non-root เข้าถึง hidraw/event/tty ได้
#   2. 99-zkteco-qr500-symlink.rules        — SYMLINK+="zkteco-qr500"        (USB HID)
#   3. 99-zkteco-qr500-serial-symlink.rules — SYMLINK+="zkteco-qr500-serial" (RS485 adapter)
#
# นี่คือ single source of truth ของ vendor/product id และเนื้อหา rule ทั้งหมด — เดิมกระจัดกระจาย
# อยู่ 3 จุด (installers.py, cli.py, features/packages/settings.py) ไม่ตรงกัน และ settings.py
# มี vendor id ผิด (1584:7000) ทำให้ rule ที่เขียนจากจุดนั้นไม่มีทาง match อุปกรณ์จริงได้เลย
QR_VENDOR_ID = "0416"   # ZKTeco QR500-BM เอง (ยืนยันจาก HID_ID=0003:00000416:00005020)
QR_PRODUCT_ID = "5020"
QR_SERIAL_ADAPTER_VENDOR_ID = "0403"    # FTDI FT232R (USB-to-RS485 adapter — คนละตัวกับ QR500-BM)
QR_SERIAL_ADAPTER_PRODUCT_ID = "6001"

QR_UDEV_RULE_PATH = _Path("/etc/udev/rules.d/99-qr500-bm.rules")
QR_UDEV_SYMLINK_PATH = _Path("/etc/udev/rules.d/99-zkteco-qr500-symlink.rules")
QR_UDEV_SERIAL_SYMLINK_PATH = _Path("/etc/udev/rules.d/99-zkteco-qr500-serial-symlink.rules")
QR_UDEV_SIGNATURE = "# managed by vas"

QR_UDEV_RULE_CONTENT = (
    f"{QR_UDEV_SIGNATURE}\n"
    "# ZKTeco QR500-BM -- allow non-root access to hidraw/event (USB) และ tty (RS485 adapter)\n"
    f'SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{QR_VENDOR_ID}", ATTRS{{idProduct}}=="{QR_PRODUCT_ID}", MODE="0666", GROUP="plugdev"\n'
    f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{QR_VENDOR_ID}", ATTRS{{idProduct}}=="{QR_PRODUCT_ID}", MODE="0664", GROUP="plugdev"\n'
    f'KERNEL=="event*", ATTRS{{idVendor}}=="{QR_VENDOR_ID}", ATTRS{{idProduct}}=="{QR_PRODUCT_ID}", MODE="0664", GROUP="plugdev"\n'
    f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{QR_SERIAL_ADAPTER_VENDOR_ID}", ATTRS{{idProduct}}=="{QR_SERIAL_ADAPTER_PRODUCT_ID}", MODE="0666", GROUP="dialout"\n'
)

# หมายเหตุ: ใช้ ENV{DEVPATH} แทน ATTRS{idVendor}/ATTRS{idProduct} เพราะ QR500-BM เป็น composite
# USB HID device (มีหลาย interface) — ATTRS{} จะ match ทุก interface พร้อมกัน (idVendor/idProduct
# เหมือนกันหมด) ทำให้ปักหมุด interface เจาะจงไม่ได้ ":1.1" คือเลข interface ที่ยืนยันแล้วว่าให้
# hidraw node ที่ถูกต้อง (ดู references/hid-mode.md ใน skill zkteco-500)
QR_UDEV_SYMLINK_CONTENT = (
    f"{QR_UDEV_SIGNATURE}\n"
    f'SUBSYSTEM=="hidraw", ENV{{DEVPATH}}=="*:1.1/0003:{QR_VENDOR_ID}:{QR_PRODUCT_ID}*", SYMLINK+="zkteco-qr500"\n'
)

QR_UDEV_SERIAL_SYMLINK_CONTENT = (
    f"{QR_UDEV_SIGNATURE}\n"
    f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{QR_SERIAL_ADAPTER_VENDOR_ID}", ATTRS{{idProduct}}=="{QR_SERIAL_ADAPTER_PRODUCT_ID}", SYMLINK+="zkteco-qr500-serial"\n'
)


def qr_config_dir() -> _Path:
    """Return ~/.config/vas/ ของ user จริง (รองรับ sudo)"""
    from system.status import _effective_home  # import late เพื่อหลีกเสี่ยง circular
    return _effective_home() / ".config" / "vas"


def qr_config_path() -> _Path:
    """Return ~/.config/vas/qr_config.json ของ user จริง"""
    return qr_config_dir() / "qr_config.json"
