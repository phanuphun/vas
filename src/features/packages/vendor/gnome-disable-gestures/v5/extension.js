/**
 * Disable Gestures 2021
 *
 * A GNOME extension that disables built-in gestures. Useful for kiosks and touch screen apps.
 *
 */

/* exported init */

const { GLib } = imports.gi

// ── VAS patch (2026-07-13) ──────────────────────────────────────────────────
// เพิ่ม timer poll ปิด gesture action ซ้ำทุก 500ms เป็น safety net เสริมจากของเดิม (ที่พึ่งแค่
// event 'notify::focus-window'/'in-fullscreen-changed') — พบว่า gesture action ตัวใหม่ที่
// gnome-shell สร้างขึ้นมาแปะบน global.stage ในจังหวะที่ไม่ตรงกับ 2 event นี้ (เช่น popup/
// permission dialog ระหว่างหน้า "Boost" ของแอป kiosk) จะไม่ถูกปิดจนกว่าจะมี event มา trigger ซ้ำ
// ทำให้ปัดจอทะลุเข้า Activities Overview ได้ชั่วขณะ — ตรวจพบจริงบนเครื่อง hapymed-sterile-00
const GESTURE_LOCKDOWN_POLL_INTERVAL_MS = 500

class Extension {
  enable () {
    global.stage.get_actions().forEach(a => { a.enabled = false })
    const disableUnmaximizeGesture = () => {
      global.stage.get_actions().forEach(a => { if (a !== this) { a.enabled = false } })
    }
    global.display.connect('notify::focus-window', disableUnmaximizeGesture)
    global.display.connect('in-fullscreen-changed', disableUnmaximizeGesture)

    // VAS patch: poll ปิดซ้ำเป็นระยะ กัน gesture action ใหม่ที่โผล่มานอกจังหวะ 2 event ข้างบน
    this._vasGestureLockdownTimerId = GLib.timeout_add(
      GLib.PRIORITY_DEFAULT,
      GESTURE_LOCKDOWN_POLL_INTERVAL_MS,
      () => {
        global.stage.get_actions().forEach(a => { a.enabled = false })
        return GLib.SOURCE_CONTINUE
      },
    )
  }

  disable () {
    // VAS patch: เคลียร์ timer ก่อนเสมอ กัน timer ทำงานต่อหลัง extension ถูกปิด/reload
    if (this._vasGestureLockdownTimerId) {
      GLib.source_remove(this._vasGestureLockdownTimerId)
      this._vasGestureLockdownTimerId = null
    }

    global.stage.get_actions().forEach(a => { a.enabled = true })
    const enableUnmaximizeGesture = () => {
      global.stage.get_actions().forEach(a => { if (a !== this) { a.enabled = true } })
    }
    global.display.connect('notify::focus-window', enableUnmaximizeGesture)
    global.display.connect('in-fullscreen-changed', enableUnmaximizeGesture)
  }
}

function init () {
  return new Extension()
}
