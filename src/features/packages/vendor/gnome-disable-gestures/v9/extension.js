/**
 * Disable Gestures 2021
 *
 * A GNOME extension that disables built-in gestures. Useful for kiosks and touchscreen apps.
 */
import GLib from 'gi://GLib'

// ── VAS patch (2026-07-13) ──────────────────────────────────────────────────
// เพิ่ม timer poll ปิด gesture action ซ้ำทุก 500ms เป็น safety net เสริมจากของเดิม (ที่พึ่งแค่
// event 'notify::focus-window'/'in-fullscreen-changed') — เหตุผลเดียวกับ patch ใน v5/extension.js
// (ดูคอมเมนต์ที่นั่น) — ตรวจพบจริงบนเครื่อง hapymed-sterile-00
const GESTURE_LOCKDOWN_POLL_INTERVAL_MS = 500

export default class Extension {
  focusWindowId = null
  inFullscreenChangedId = null
  _vasGestureLockdownTimerId = null

  enable() {
    global.stage.get_actions().forEach(action => { action.enabled = false })
    const disableUnmaximizeGesture = () => {
      global.stage.get_actions().forEach(action => {
        if (action === this) return
        action.enabled = false
      })
    }
    if (this.focusWindowId === null) {
      this.focusWindowId = global.display.connect('notify::focus-window', disableUnmaximizeGesture)
    }
    if (this.inFullscreenChangedId === null) {
      this.inFullscreenChangedId = global.display.connect('in-fullscreen-changed', disableUnmaximizeGesture)
    }

    // VAS patch: poll ปิดซ้ำเป็นระยะ กัน gesture action ใหม่ที่โผล่มานอกจังหวะ 2 event ข้างบน
    if (this._vasGestureLockdownTimerId === null) {
      this._vasGestureLockdownTimerId = GLib.timeout_add(
        GLib.PRIORITY_DEFAULT,
        GESTURE_LOCKDOWN_POLL_INTERVAL_MS,
        () => {
          global.stage.get_actions().forEach(action => { action.enabled = false })
          return GLib.SOURCE_CONTINUE
        },
      )
    }
  }

  disable() {
    // VAS patch: เคลียร์ timer ก่อนเสมอ กัน timer ทำงานต่อหลัง extension ถูกปิด/reload
    if (this._vasGestureLockdownTimerId !== null) {
      GLib.source_remove(this._vasGestureLockdownTimerId)
      this._vasGestureLockdownTimerId = null
    }
    if (this.inFullscreenChangedId !== null) {
      global.display.disconnect(this.inFullscreenChangedId)
      this.inFullscreenChangedId = null
    }
    if (this.focusWindowId !== null) {
      global.display.disconnect(this.focusWindowId)
      this.focusWindowId = null
    }
    global.stage.get_actions().forEach(action => { action.enabled = true })
  }
}
