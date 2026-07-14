"""
Guarded shell-command policy — ตรวจว่าคำสั่งเข้าข่าย delete/install/update หรือไม่

แยกออกมาจาก mcp/tools/shell.py เป็นโมดูลอิสระใน core/ (ไม่ depend on fastmcp หรืออะไรใน
project) ด้วยเหตุผล 2 ข้อ:
1. ตาม convention ของไฟล์อื่นใน core/ (ดู core/runner.py) — เป็น infra กลางที่ควร test ได้
   โดยไม่ต้องพึ่ง framework ภายนอก
2. mcp/tools/shell.py import `fastmcp` ซึ่งพึ่งพา pip package ชื่อ "mcp" — โปรเจกต์นี้เองก็มี
   subpackage ชื่อ "mcp" (src/mcp/) จึงชนกันเมื่อรันด้วย PYTHONPATH=src (convention หลักของ
   โปรเจกต์ตาม INSTRUCTIONS.md) ทำให้ `from fastmcp import FastMCP` fail ด้วย
   `ModuleNotFoundError: No module named 'mcp.types'` เพราะ src/mcp ถูก resolve ก่อน
   pip package "mcp" จริง — บั๊กนี้มีอยู่ก่อนแล้วกับทุกไฟล์ใน mcp/tools/ (system.py, docker.py,
   network.py, logs.py) ไม่ใช่สิ่งที่ไฟล์นี้สร้างขึ้นใหม่ แต่แยก logic การเช็ค policy ออกมาที่นี่
   ทำให้อย่างน้อย unit test ของ policy เองรันได้โดยไม่ชนปัญหานี้ — การแก้ collision จริง (เช่น
   เปลี่ยนชื่อ src/mcp/ เป็นชื่ออื่น) เป็นงานแยกต่างหาก ไม่ได้อยู่ใน scope ของงานนี้
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_OUTPUT_CHARS = 50_000

BLOCKED_CATEGORIES = ("delete", "install/remove", "update/self-update")

# binary ที่ถือว่าเป็นคำสั่ง "ลบ" เสมอไม่ว่าจะมี argument อะไรตามมา
BLOCKED_BINARIES: frozenset[str] = frozenset(
    {"rm", "rmdir", "unlink", "shred"}
)

# (binary -> verb ที่ถูกห้าม) ครอบคลุม install/remove/update — verb อื่นของ binary เดียวกัน
# (เช่น `apt list`, `pip show`, `npm ls`, `git status`) ยังใช้ได้ปกติ
BLOCKED_VERB_COMBOS: dict[str, frozenset[str]] = {
    "apt": frozenset({"install", "remove", "purge", "update", "upgrade", "dist-upgrade", "full-upgrade", "autoremove"}),
    "apt-get": frozenset({"install", "remove", "purge", "update", "upgrade", "dist-upgrade", "full-upgrade", "autoremove"}),
    "dpkg": frozenset({"-i", "--install", "-r", "--remove", "-p", "--purge"}),
    "pip": frozenset({"install", "uninstall"}),
    "pip3": frozenset({"install", "uninstall"}),
    "npm": frozenset({"install", "i", "ci", "uninstall", "update", "upgrade", "remove", "rm"}),
    "yarn": frozenset({"add", "remove", "upgrade"}),
    "snap": frozenset({"install", "remove", "refresh"}),
    "gem": frozenset({"install", "uninstall"}),
    "vas": frozenset({"update"}),
    "git": frozenset({"pull"}),  # ป้องกันการ self-update codebase ผ่าน git
}

# รูปแบบที่ไม่ได้ผูกกับ binary ตัวใดตัวหนึ่งโดยตรง — เช็คทับซ้อนกับด้านบนอีกชั้น
BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfind\b.*-delete\b"),             # find ... -delete
    re.compile(r"\btruncate\b.*-s\s*0\b"),           # truncate -s 0 <file> == ลบเนื้อหาไฟล์
    re.compile(r"\|\s*(sudo\s+)?(bash|sh|zsh)\b"),   # curl ... | bash == install pattern คลาสสิก
)


@dataclass(frozen=True)
class CommandRejected(Exception):
    reason: str
    segment: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.reason


def split_segments(command: str) -> list[str]:
    """แยกคำสั่งที่ chain กันด้วย ; && || | ออกเป็น segment ย่อยเพื่อเช็คทีละท่อน"""
    return [seg for seg in re.split(r"&&|\|\||;|\|", command) if seg.strip()]


def _check_segment(segment: str) -> None:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    if not tokens:
        return

    binary = tokens[0].rsplit("/", 1)[-1].lower()

    if binary in BLOCKED_BINARIES:
        raise CommandRejected(
            f"บล็อก: '{binary}' เป็นคำสั่งลบไฟล์/ข้อมูล (อยู่ในหมวด delete ที่ห้ามใช้)",
            segment.strip(),
        )

    blocked_verbs = BLOCKED_VERB_COMBOS.get(binary)
    if blocked_verbs:
        rest = [t.lower() for t in tokens[1:]]
        hit = next((v for v in rest if v in blocked_verbs), None)
        if hit is not None:
            raise CommandRejected(
                f"บล็อก: '{binary} {hit}' เข้าข่าย install/remove/update ที่ห้ามใช้",
                segment.strip(),
            )


def check_command(command: str) -> None:
    """ตรวจว่าคำสั่งเข้าข่าย delete/install/update หรือไม่ — raise CommandRejected ถ้าเข้าข่าย

    คำสั่งที่ chain กันด้วย ; && || | จะถูกแยกเช็คทีละ segment เพื่อกันการ bypass แบบ
    `echo ok && rm -rf /` — segment แรกผ่านไม่ได้แปลว่า block ทั้งคำสั่งไม่ทำงาน

    นี่คือ blocklist แบบ keyword (เช็คจาก binary+verb ไม่ใช่ full-string matching เพื่อกัน
    false positive เช่น `echo "please install this"`) — ไม่ใช่ sandbox แบบสมบูรณ์ กัน
    "คำสั่งตรงๆ" ได้ ไม่ได้กันทุกวิธี obfuscate (เช่น เข้ารหัส base64 แล้ว pipe เข้า sh)
    """
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            raise CommandRejected(
                "บล็อก: รูปแบบคำสั่งเข้าข่าย delete/install (find -delete, truncate -s 0, "
                "หรือ pipe เข้า shell เช่น curl | bash)",
                command.strip(),
            )
    for segment in split_segments(command):
        _check_segment(segment)


def truncate_output(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    hidden = len(text) - max_chars
    return text[:max_chars] + f"\n...[truncated, {hidden} more chars]"


def exec_policy() -> dict:
    """สรุป policy ปัจจุบันเป็น dict — ใช้ทั้งจาก MCP tool (get_exec_policy) และ debug/test"""
    return {
        "categories": list(BLOCKED_CATEGORIES),
        "blocked_binaries": sorted(BLOCKED_BINARIES),
        "blocked_verb_combos": {k: sorted(v) for k, v in BLOCKED_VERB_COMBOS.items()},
        "blocked_patterns": [p.pattern for p in BLOCKED_PATTERNS],
        "default_timeout": DEFAULT_TIMEOUT,
        "max_timeout": MAX_TIMEOUT,
        "max_output_chars": MAX_OUTPUT_CHARS,
    }
