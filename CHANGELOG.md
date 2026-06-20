# Changelog

## [2026-06-20]

### เพิ่ม MCP tool specs และปรับปรุง TODO
- เพิ่ม spec สำหรับ MCP tool `diagnose_touchscreen` — วิเคราะห์ปัญหา touchscreen แบบ step-by-step (kernel → xinput → xorg → session)
- เพิ่ม spec สำหรับ MCP tool `diagnose_remote_access` — วิเคราะห์ปัญหา AnyDesk เข้าไม่ได้ (service → network → logs)
- เพิ่ม spec สำหรับ MCP tool `diagnose_display` — วิเคราะห์ปัญหาหน้าจอไม่แสดงผลหรือ rotation ผิด
- เพิ่ม improvement notes สำหรับ production server (gunicorn), Basic Auth dashboard, และ pytest-cov
- เพิ่ม retrospective: MCP server startup และ mount() fix

## [2026-06-18]

### ปรับปรุง agentflow และโครงสร้างโปรเจกต์
- อัปเดต `.agents/README.md`, `.agents/workflows/` ให้ใช้ config.json แทน hardcode path
- ลบ `AGENTS.md` (ย้ายเนื้อหาไปใช้ผ่าน `@AGENTS.md` ใน CLAUDE.md)
- อัปเดต `AGENTS.md.bak` ให้ตรงกับเนื้อหาล่าสุด
- เพิ่ม `.agents/config.json` สำหรับ resolve `agentsPath` และ `wikiPath` แบบ dynamic
- เพิ่ม `.agents/skills/grill-me/` skill ใหม่
- เพิ่มโฟลเดอร์ `wiki/` สำหรับ project wiki
- เพิ่ม `.mcp.json` ใน `.gitignore` เพื่อป้องกัน machine-specific config รั่วไหล
- แก้ไข `CLAUDE.md` ให้ reference `@AGENTS.md` ตัวพิมพ์ถูกต้อง

