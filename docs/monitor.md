# System Monitor — รายละเอียดทั้งหมด

## ภาพรวม

Monitor ดึงข้อมูล metrics จาก **Linux built-in sources เท่านั้น** — ไม่ต้องติดตั้ง package เพิ่ม

Source: `src/system/monitor.py`
API: `GET /api/monitor/metrics`

---

## แหล่งข้อมูล

| Metric | Source |
|---|---|
| CPU usage % | `/proc/stat` (อ่าน 2 ครั้ง ห่าง 0.4s) |
| CPU info (model, cores, MHz) | `/proc/cpuinfo` |
| Load average | `/proc/loadavg` |
| RAM / Swap | `/proc/meminfo` |
| Uptime | `/proc/uptime` |
| Network I/O | `/proc/net/dev` |
| CPU temperature | `/sys/class/thermal/thermal_zone*/temp` |
| OS info | `/etc/os-release` + `uname` |
| Disk usage | `/proc/mounts` + `os.statvfs()` |
| Block devices | `lsblk -b --json` (pre-installed บน Ubuntu) |

---

## Metrics รายละเอียด

### CPU (`get_cpu()`)

```json
{
  "model": "Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz",
  "cores": 4,
  "threads": 8,
  "mhz": 1800.0,
  "usage_pct": 12.5,
  "load_1": 0.45,
  "load_5": 0.38,
  "load_15": 0.32,
  "per_core_pct": [8.1, 15.2, 10.3, 11.8, 9.5, 14.1, 12.7, 13.9]
}
```

**วิธีคำนวณ usage %:**
1. อ่าน `/proc/stat` snapshot ที่ 1
2. sleep 0.4 วินาที
3. อ่าน `/proc/stat` snapshot ที่ 2
4. `usage = (1 - Δidle / Δtotal) × 100`

โดย `idle = idle + iowait` จาก `/proc/stat` columns:
```
cpu user nice system idle iowait irq softirq steal
```

---

### Memory (`get_memory()`)

อ่านจาก `/proc/meminfo` แปลงจาก kB → bytes

```json
{
  "total":      8589934592,
  "used":       3221225472,
  "free":       1073741824,
  "available":  5368709120,
  "cached":     2147483648,
  "buffers":    268435456,
  "used_pct":   37.5,
  "swap_total": 2147483648,
  "swap_used":  0,
  "swap_pct":   0.0
}
```

**สูตร:**
```
used      = total - available
used_pct  = used / total × 100
cached    = Cached + SReclaimable
available = MemAvailable (kernel-reported, รวม page cache ที่คืนได้)
```

---

### Disk (`get_disk()`)

อ่าน mount points จาก `/proc/mounts` แล้วเรียก `os.statvfs()` แต่ละ mount

```json
[
  {
    "mount":    "/",
    "device":   "/dev/sda1",
    "fstype":   "ext4",
    "total":    107374182400,
    "used":     21474836480,
    "free":     85899345920,
    "used_pct": 20.0
  },
  {
    "mount":    "/home",
    "device":   "/dev/sda2",
    "fstype":   "ext4",
    "total":    214748364800,
    "used":     53687091200,
    "free":     161061273600,
    "used_pct": 25.0
  }
]
```

**Filesystem ที่ filter ออก (ไม่แสดง):**
```
tmpfs, devtmpfs, sysfs, proc, devpts, cgroup, cgroup2,
pstore, bpf, tracefs, debugfs, hugetlbfs, mqueue,
fusectl, overlay, squashfs, efivarfs
```

**Mount prefix ที่ filter ออก:**
```
/proc, /sys, /dev, /run, /snap
```

Duplicate devices (bind mounts) ถูก filter โดย `seen_devices` set

---

### Temperature (`get_temperatures()`)

อ่านจาก `/sys/class/thermal/thermal_zone*/temp`

```json
[
  {"label": "x86_pkg_temp", "temp_c": 45.0},
  {"label": "acpitz",       "temp_c": 27.8}
]
```

- แปลง raw value / 1000 → °C
- Filter: แสดงเฉพาะ 0°C < temp < 120°C (ค่านอกช่วงถือว่า invalid)

---

### Uptime (`get_uptime()`)

อ่านจาก `/proc/uptime` (ค่าแรก = uptime seconds)

```json
{
  "total_seconds": 86523.4,
  "days":    1,
  "hours":   0,
  "minutes": 2,
  "human":   "1d 0h 2m"
}
```

---

### Network I/O (`get_network()`)

อ่านจาก `/proc/net/dev`

```json
[
  {
    "iface":    "eth0",
    "rx_bytes": 1073741824,
    "tx_bytes": 536870912,
    "rx_mb":    1024.0,
    "tx_mb":    512.0
  },
  {
    "iface":    "wg0",
    "rx_bytes": 10485760,
    "tx_bytes": 5242880,
    "rx_mb":    10.0,
    "tx_mb":    5.0
  }
]
```

- ไม่แสดง `lo` (loopback)
- เรียงตามชื่อ interface

> **หมายเหตุ:** ค่า rx/tx เป็น **cumulative** นับตั้งแต่ boot ไม่ใช่ throughput ปัจจุบัน

---

### OS Info (`get_os_info()`)

```json
{
  "os_name":  "Ubuntu 22.04.3 LTS",
  "kernel":   "5.15.0-89-generic",
  "arch":     "x86_64",
  "hostname": "vending-machine-01"
}
```

- `os_name` — จาก `/etc/os-release` (PRETTY_NAME)
- `kernel` — จาก `os.uname().release`
- `arch` — จาก `os.uname().machine`

---

### Block Devices (`get_block_devices()`)

รัน `lsblk -b -o NAME,SIZE,TYPE,MODEL,TRAN --json`

```json
[
  {
    "name":    "sda",
    "size":    256060514304,
    "size_gb": 238.5,
    "model":   "Samsung SSD 860",
    "tran":    "sata"
  }
]
```

- แสดงเฉพาะ `type=disk` (ไม่รวม partition)
- `tran`: `sata`, `nvme`, `usb`, `unknown`

---

## Full Snapshot API

`GET /api/monitor/metrics` — คืน metrics ทั้งหมดในครั้งเดียว

```json
{
  "ts": 1703001234.567,
  "os": { ... },
  "uptime": { ... },
  "cpu": { ... },
  "memory": { ... },
  "disk": [ ... ],
  "temps": [ ... ],
  "network": [ ... ],
  "block": [ ... ]
}
```

> ⚠️ Request นี้ใช้เวลา ~0.4 วินาที เพราะต้องรอ CPU usage delta
