"""
payload.py — ประกอบ wire payload (JSON body) ที่ใช้ร่วมกันทั้ง Webhook และ MQTT จาก scan event
เดียวกัน (features/qr/scan_publisher.py) แทนที่จะให้แต่ละ sink ประกอบ body เองแยกกันคนละแบบ
เหมือนก่อนหน้านี้ (webhook ใช้ scan/ts/source, mqtt ใช้ data/timestamp ไม่มี source เลย)

Field ตั้งชื่อ/รูปแบบตรงกับ qr500_reader.payload.build_scan_body() (โปรเจกต์พี่น้องที่อ่าน
QR500-BM ตัวเดียวกันแต่ deploy แยกจาก VAS -- ดู qr500-reader/src/qr500_reader/payload.py) ทุก
field ยกเว้น 2 จุด:
  1. "scan" (VAS) แทน "data" (qr500-reader) -- "scan" เป็นชื่อเดิมของ VAS เองมาตั้งแต่ SSE event/
     DB schema อยู่แล้ว เปลี่ยนตอนนี้จะกระทบหลายจุดเกินจำเป็นโดยไม่ได้ประโยชน์อะไรเพิ่ม
  2. ไม่มี field "source" -- เดิม VAS เคยใส่ "source": "zkteco-qr500" เพิ่มเข้าไปเอง (ไม่มีใน
     qr500-reader) ตัดออกให้ตรงกับ qr500-reader เป๊ะๆ ตามที่ตกลงกันไว้

ส่งแบบ "full" เสมอ (ทุก field พร้อมกันในก้อนเดียว) ไม่มีการเลือก payload_mode (decoded/
raw_keycode/raw_report) แยกส่งทีละอย่างแบบเดิมอีกต่อไป -- field ไหนไม่มีข้อมูลจริงสำหรับ
read_mode ปัจจุบันใช้ UNDEFINED ("undefined" string literal) แทน null เพื่อให้ downstream
แยกแยะได้ว่า "field นี้ใช้กับ read_mode นี้ไม่ได้เลย" ต่างจาก null ที่แปลว่า "มี field นี้แต่ค่า
ว่างจริงๆ" (แนวคิดเดียวกับ qr500_reader.payload.UNDEFINED)
"""
from __future__ import annotations

from typing import Any

UNDEFINED = "undefined"


def build_scan_body(event: dict[str, Any]) -> dict[str, Any]:
    """
    แปลง scan event dict (จาก ScanPublisherThread -- key: scan, device, ts, raw_keycode,
    raw_report, read_mode, scan_source, rfid_uid) เป็น wire payload พร้อมส่งออก (webhook/mqtt)

    หมายเหตุ raw_report/raw_bytes: reader.py ของ VAS ใช้ property เดียวกัน
    (`last_scan_raw_report`) แทนทั้ง 2 ความหมายตาม read_mode -- hidraw: raw HID byte report
    จริง (list[str] หลาย element), serial: hex ของ raw serial buffer ทั้งก้อน (list[str] ที่มี
    1 element เสมอ) -- ฟังก์ชันนี้ map ให้ถูกช่อง wire field ตาม read_mode ให้ตรงกับที่
    qr500-reader แยก raw_report (hidraw) ออกจาก raw_bytes (serial) เป็นคนละ field กัน:
        read_mode="hidraw" -> "raw_report" = list ของ hex report, "raw_bytes" = UNDEFINED
        read_mode="serial" -> "raw_bytes" = hex string ของ buffer ทั้งก้อน, "raw_report" = UNDEFINED
        read_mode="evdev"  -> ทั้งคู่ = UNDEFINED (evdev ไม่มี raw byte report concept เลย)
    ไม่ต้องแก้ reader.py class ใดๆ เลย -- แค่ map ตอนประกอบ payload ชั้นนี้ชั้นเดียว
    """
    read_mode = event.get("read_mode")
    raw_keycode = event.get("raw_keycode")
    raw_report_value = event.get("raw_report")

    raw_report: Any = UNDEFINED
    raw_bytes: Any = UNDEFINED
    if read_mode == "hidraw" and raw_report_value:
        raw_report = raw_report_value
    elif read_mode == "serial" and raw_report_value:
        raw_bytes = raw_report_value[0]

    scan_source = event.get("scan_source")
    rfid_uid = event.get("rfid_uid")

    return {
        "device": event.get("device"),
        "mode": "full",
        "read_mode": read_mode if read_mode is not None else UNDEFINED,
        "scan": event.get("scan"),
        "raw_keycode": raw_keycode if raw_keycode is not None else UNDEFINED,
        "raw_report": raw_report,
        "raw_bytes": raw_bytes,
        "scan_source": scan_source if scan_source is not None else UNDEFINED,
        "rfid_uids": rfid_uid if rfid_uid is not None else UNDEFINED,
        "timestamp": event.get("ts"),
    }
