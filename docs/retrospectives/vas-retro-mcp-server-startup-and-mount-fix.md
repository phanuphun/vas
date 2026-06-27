---
date: 2026-06-20
status: resolved
---

# Retro: VAS MCP Server — Startup Failures and Tool Registration Fix

## Summary

`vas mcp start` ล้มเหลวหลายจุดซ้อนกันระหว่าง 2026-06-18 ถึง 2026-06-20 รวม 6 ปัญหา ได้แก่ pip bootstrap, subprocess output streaming, FastMCP API rename (include_router → import_server), .mcp.json format ผิด, และปัญหาหลักคือ `import_server()` ใน FastMCP 3.x เป็น async แต่ถูกเรียกแบบ synchronous ทำให้ server start ได้แต่ไม่มี tools เลย แก้ทั้งหมดด้วยการแก้ไข `src/mcp_server.py`, `src/mcp_service.py`, `src/runner.py` และ commit เข้า main

## Symptom

ปัญหาปรากฏเป็นลำดับ:

1. `FileNotFoundError: [Errno 2] No such file or directory: 'pip3'`
2. `/usr/bin/python3 -m pip --version` → exit code 1, `No module named pip`
3. apt-get / pip install ทำงานแต่ไม่มี output แสดงผล (ดูเหมือน hang)
4. `AttributeError: 'FastMCP' object has no attribute 'include_router'`
5. `.mcp.json` warning: `command: expected string, received undefined`
6. `/mcp` ใน Claude Code แสดง `vas · △ connected · no tools`

## Root Cause

**ปัญหา 1 — pip3 not found**
`src/mcp_service.py` เรียก `["pip3", "install", ...]` ตรงๆ แต่ Ubuntu 22.04 minimal ไม่มี `pip3` symlink ใน PATH

**ปัญหา 2 — No module named pip**
Ubuntu 22.04 minimal ติดตั้ง Python โดยไม่มี pip — ต้อง bootstrap ก่อน

**ปัญหา 3 — ไม่มี progress output**
`runner.run()` ใช้ `stdout=subprocess.PIPE, stderr=subprocess.PIPE` ดัก output ไว้หมด
ทำให้ apt-get และ pip install ดูเหมือนค้างแต่จริงๆ ทำงานอยู่

**ปัญหา 4 — include_router AttributeError**
FastMCP เปลี่ยน API ใน v2.x: `include_router()` → `import_server()`
โค้ดใน `src/mcp_server.py` ยังใช้ชื่อเก่า

**ปัญหา 5 — .mcp.json format ผิด**
`.mcp.json` ที่สร้างใหม่ใช้แค่ `"url"` field
Claude Code ต้องการ `"type": "sse"` ด้วยจึงจะรู้ว่าเป็น SSE transport

**ปัญหา 6 — no tools (root cause หลัก)**
`src/mcp_server.py` เรียก `mcp.import_server()` แบบ synchronous ที่ module level:

```python
mcp.import_server(system.mcp)   # ไม่มี await
mcp.import_server(network.mcp)
...
```

ใน FastMCP 3.x `import_server()` เป็น coroutine (async method) การเรียกโดยไม่ `await`
ทำให้ได้ coroutine object ที่ไม่ถูก execute เลย ไม่มี error หรือ warning ใดๆ
tools จึงไม่ถูก register เข้า server แม้ SSE connection จะสำเร็จ

## Why It Produced the Symptom

FastMCP 3.x เปลี่ยน composition API จาก async `import_server()` (v2) ไปเป็น
synchronous `mount()` (v3) โดยไม่มี deprecation warning หรือ runtime error
Server start สำเร็จ (transport layer OK) แต่ tool list ว่างเปล่า (application layer fail เงียบๆ)

## Fix

**ปัญหา 1-2** — `src/mcp_service.py`: เปลี่ยน pip3 → sys.executable + bootstrap

```python
# เดิม
runner.run(["pip3", "install", ...])

# ใหม่
runner.run([sys.executable, "-m", "pip", "install", ...])

# เพิ่ม _ensure_pip() — ลอง ensurepip ก่อน fallback ไป apt-get
def _ensure_pip(runner: CommandRunner) -> None:
    result = runner.run([sys.executable, "-m", "pip", "--version"], check=False)
    if result.returncode == 0:
        return
    result = runner.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
    if result.returncode == 0:
        return
    runner.run(["apt-get", "install", "-y", "python3-pip"], stream=True)
```

**ปัญหา 3** — `src/runner.py`: เพิ่ม `stream: bool = False`

```python
def run(self, args, check=True, stream=False):
    if stream:
        completed = subprocess.run(normalized_args, check=False)
        # ไม่ PIPE = output ไหลออก terminal ตรงๆ
```

**ปัญหา 4** — `src/mcp_server.py`:

```python
# เดิม (FastMCP 1.x)
mcp.include_router(system.mcp)
# ใหม่ (FastMCP 2.x)
mcp.import_server(system.mcp)
```

**ปัญหา 5** — `.mcp.json`:

```json
{
  "mcpServers": {
    "vas": {
      "type": "sse",
      "url": "http://10.8.0.56:8899/sse"
    }
  }
}
```

**ปัญหา 6 (หลัก)** — `src/mcp_server.py`: เปลี่ยน import_server → mount

```python
# เดิม (FastMCP 3.x async — ไม่ await = ไม่ทำงาน)
mcp.import_server(system.mcp)
mcp.import_server(network.mcp)
mcp.import_server(display.mcp)
mcp.import_server(docker.mcp)
mcp.import_server(logs.mcp)

# ใหม่ (synchronous)
mcp.mount(system.mcp)
mcp.mount(network.mcp)
mcp.mount(display.mcp)
mcp.mount(docker.mcp)
mcp.mount(logs.mcp)
```

## How It Was Found

1. รัน `vas mcp start` บน Ubuntu VM → `pip3 not found`
2. เปลี่ยนเป็น `sys.executable -m pip` → `No module named pip`
3. เพิ่ม `_ensure_pip()` → install ทำงานแต่ไม่มี output → เพิ่ม `stream=True`
4. Server start ใหม่ → `AttributeError: include_router` → ดู FastMCP changelog → rename เป็น `import_server`
5. แก้แล้ว start สำเร็จ แต่ Claude Code แสดง `no tools`
6. ค้น FastMCP 3.x docs → พบว่า `import_server` เป็น async ใน v2 แต่ v3 ให้ใช้ `mount()` (sync)
7. เปลี่ยนทุก `import_server` → `mount()` → `/mcp` แสดง 11 tools

## Why It Slipped Through

FastMCP ไม่ raise `RuntimeWarning: coroutine was never awaited` เมื่อเรียก
async method ที่ module level ใน Python ทำให้ตรวจจับไม่ได้จาก log
Server start สำเร็จ + SSE connected ทำให้ดูเหมือนทุกอย่างปกติ

## Validation

หลัง `sudo vas update && sudo vas mcp start` บน kiosk:
- `/mcp` ใน Claude Code: `vas · ✓ connected · 11 tools`
- Deferred tools ขึ้น: `mcp__vas__get_system_status`, `mcp__vas__get_os_info`, ฯลฯ ครบ 11 tools

## Action Items

| # | What | Owner | Status |
|---|------|-------|--------|
| 1 | Deploy fix ไปเครื่อง kiosk จริง (`sudo vas update`) | Phanuphun | Open |
| 2 | เพิ่ม test สำหรับ `_ensure_pip()` bootstrap path | Phanuphun | Open |
