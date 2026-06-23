---
date: 2026-06-20
status: resolved
---

# Retro: VAS MCP Server — Startup Failures and Tool Registration Fix

## Summary

`vas mcp start` ล้มเหลวหลายจุดระหว่าง session 2026-06-18 ถึง 2026-06-20 รวม 6 ปัญหาซ้อนกัน ได้แก่ pip bootstrap, subprocess streaming, FastMCP API incompatibility (include_router → import_server), .mcp.json format ผิด, และ import_server ไม่ register tools เพราะไม่ถูก await ใน FastMCP 3.x แก้ทั้งหมดด้วยการแก้ไข 3 ไฟล์ใน src/ และ commit เข้า main

## Symptom

ปัญหาปรากฏเป็นลำดับ:

1. `FileNotFoundError: [Errno 2] No such file or directory: 'pip3'`
2. `/usr/bin/python3 -m pip --version` → `No module named pip`
3. apt-get / pip install ทำงานแต่ไม่มี output แสดงผลใดๆ (ดูเหมือน hang)
4. `AttributeError: 'FastMCP' object has no attribute 'include_router'`
5. `.mcp.json` warning: `command: expected string, received undefined`
6. Claude Code แสดง `vas · △ connected · no tools` แม้ server จะ start สำเร็จ

## Root Cause

ปัญหาแต่ละจุดมี root cause แยกกัน:

**ปัญหา 1 — pip3 not found**
`src/mcp_service.py` เรียก `pip3` ตรงๆ แต่ Ubuntu 22.04 บางเครื่องไม่มี `pip3` ใน PATH

**ปัญหา 2 — No module named pip**
เครื่องที่ติดตั้ง Python จาก minimal image ไม่มี pip มาด้วย ต้อง bootstrap ก่อน

**ปัญหา 3 — ไม่มี progress output**
`runner.run()` ใช้ `subprocess.PIPE` ดัก stdout/stderr ไว้หมด ทำให้ output ของ apt-get และ pip ไม่ปรากฏบน terminal

**ปัญหา 4 — include_router AttributeError**
FastMCP เปลี่ยน API ใน version 2.x: `include_router()` → `import_server()` แต่โค้ดยังใช้ชื่อเก่า

**ปัญหา 5 — .mcp.json format ผิด**
`.mcp.json` ที่สร้างใหม่ใช้แค่ `"url"` field แต่ Claude Code ต้องการ `"type": "sse"` ด้วยจึงจะรู้ว่าเป็น SSE transport

**ปัญหา 6 — no tools (root cause หลัก)**
`mcp_server.py` เรียก `mcp.import_server()` แบบ synchronous ที่ module level แต่ใน FastMCP 3.x `import_server()` เป็น coroutine (async) การเรียกโดยไม่ `await` ทำให้ได้ coroutine object ที่ไม่ถูก execute เลย tools จึงไม่ถูก register เข้าไปใน server แม้ server จะ start ได้ปกติและ SSE connection สำเร็จก็ตาม

## Why It Produced the Symptom

FastMCP 3.x เปลี่ยน composition API จาก async `import_server()` ไปเป็น synchronous `mount()` โดยไม่มี deprecation warning หรือ runtime error ทำให้ server start สำเร็จ (transport layer OK) แต่ tool list ว่างเปล่า (application layer fail เงียบๆ)

## Fix

**ปัญหา 1-2** — `src/mcp_service.py`
```python
# เดิม
runner.run(["pip3", "install", ...])

# ใหม่
runner.run([sys.executable, "-m", "pip", "install", ...])

# เพิ่ม _ensure_pip() bootstrap
def _ensure_pip(runner):
    result = runner.run([sys.executable, "-m", "pip", "--version"], check=False)
    if result.returncode == 0:
        return
    result = runner.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
    if result.returncode == 0:
        return
    runner.run(["apt-get", "install", "-y", "python3-pip"], stream=True)
```

**ปัญหา 3** — `src/runner.py`
เพิ่ม parameter `stream: bool = False` ใน `run()`:
```python
if stream:
    completed = subprocess.run(normalized_args, check=False)  # ไม่ PIPE = output ไหลออก
```

**ปัญหา 4** — `src/mcp_server.py`
```python
# เดิม
mcp.include_router(system.mcp)
# ใหม่ (FastMCP 2.x)
mcp.import_server(system.mcp)
```

**ปัญหา 5** — `.mcp.json`
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

**ปัญหา 6 (หลัก)** — `src/mcp_server.py`
```python
# เดิม (FastMCP 3.x async — ไม่ await = ไม่ทำงาน)
mcp.import_server(system.mcp)
mcp.import_server(network.mcp)
mcp.import_server(display.mcp)
mcp.import_server(docker.mcp)
mcp.import_server(logs.mcp)

# ใหม่ (synchronous — ทำงานทันที)
mcp.mount(system.mcp)
mcp.mount(network.mcp)
mcp.mount(display.mcp)
mcp.mount(docker.mcp)
mcp.mount(logs.mcp)
```

## How It Was Found

1. รัน `vas mcp start` บน Ubuntu VM → เห็น `pip3 not found`
2. เปลี่ยนเป็น `sys.executable -m pip` → พบ `No module named pip`
3. เพิ่ม `_ensure_pip()` → pip install ทำงานแต่ไม่มี output → เพิ่ม `stream=True`
4. `vas mcp start` ใหม่ → `AttributeError: include_router` → ค้น FastMCP changelog → พบ rename เป็น `import_server`
5. แก้แล้ว start สำเร็จ แต่ Claude Code แสดง `no tools`
6. ค้น FastMCP 3.x docs → พบว่า `import_server` เป็น async ใน v2 แต่ v3 เปลี่ยนเป็น `mount()` (synchronous)
7. เปลี่ยนทุก `import_server` → `mount()` → tools ปรากฏครบ

## Why It Slipped Through

FastMCP ไม่มี deprecation warning เมื่อเรียก `import_server()` โดยไม่ await — Python สร้าง coroutine object แล้วทิ้งเงียบๆ โดยไม่ raise RuntimeWarning (พฤติกรรมนี้เกิดเฉพาะเมื่อ coroutine ถูกสร้างที่ module level) ทำให้ยากต่อการตรวจจับ

## Validation

หลังแก้ไขและ `sudo vas update && sudo vas mcp start` บนเครื่อง kiosk:
- `/mcp` ใน Claude Code แสดง `vas · ✓ connected · 11 tools`
- Deferred tools ปรากฏใน session: `mcp__vas__get_system_status`, `mcp__vas__get_os_info`, ฯลฯ

## Action Items

| # | What | Owner | Status |
|---|------|-------|--------|
| 1 | Deploy fix ไปเครื่อง kiosk จริง (`sudo vas update`) | Phanuphun | Open |
| 2 | เพิ่ม test สำหรับ `_ensure_pip()` bootstrap path | Phanuphun | Open |
