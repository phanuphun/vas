# (Superseded — see `hid-mode.md`)

This file described a generic USB HID Boot Keyboard report layout (`byte[1]`=modifier,
`byte[3:9]`=keycodes) that **does not match the byte offsets confirmed on real hardware** for
this project (`byte[0]`=modifier, `byte[2:8]`=keycodes — see `references/hid-mode.md`).

Keeping this file only as a pointer rather than deleting it, since another reference/note may
still link to the old filename — **read `references/hid-mode.md` instead**, it contains the
verified byte layout, the full keycode map, and an explicit callout about this exact offset
discrepancy so it doesn't get re-introduced by accident.
