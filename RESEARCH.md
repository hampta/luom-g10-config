# LUOM G10 — Research Notes

Protocol reverse-engineering findings from USBPcap captures, Windows driver DLL analysis,
and binary profile file parsing.

---

## USB Protocol

### Packet structure

Every ctrl packet is **8 bytes**:

```
[b0] [b1] [b2] [b3] [b4] [b5] [b6] [b7]
```

| Byte | Role |
|------|------|
| `b0` | Magic: `0x27` (always); `0x25` only for LOD ctrl#1 |
| `b1` | Register: `0x27` / `0x2A` / `0x2B` / `0x2C` / `0x2D` |
| `b2` | Primary parameter (varies per command) |
| `b3` | Separator: `0xFF` (always); exceptions: `0x04` in light_std_c5, `0x02` in ctrl#14 |
| `b4` | Secondary parameter — shared 7-value lookup table |
| `b5` | **Command type tag** (fixed per category) |
| `b6` | Secondary result / light variant selector |
| `b7` | **Command subtype tag** (fixed per category) |

### Command categories (b5, b7 pair)

| `b5` | `b7` | Category |
|------|------|---------|
| `0xD5` | `0x76` | Polling rate |
| `0x25` | `0x76` | Active DPI slot |
| `0x55` | `0xB6` | DPI count |
| `0x35` | `0xF6` | Light ctrl#6 (standard / neon / key-reaction / yo-yo / marbles / flying-star) |
| `0x35` | `0x8E` | Light ctrl#6 (breathing / wave / trailing) |
| `0x35` | `0x86` | Light ctrl#6 (drag / slide) |
| `0x35` | `0x6E` | Light ctrl#6 standard color variant (multicolor / white) |
| `0xEA` | `0xEE` | LOD ctrl#1 |

### b4 shared lookup table

`b4` uses the **same 7-entry table** for both active DPI slot (index 0–6) and DPI count (index 0–6):

```
index:  0     1     2     3     4     5     6
b4:    0xE8  0x00  0xF8  0xD0  0xC8  0xE0  0xD8
```

### b2 low nibble pattern

`b2` low nibble alternates `0xD` / `0x5` across DPI slot and DPI count tables:
- Odd indices (0, 2, 4, 6) → `lo = 0xD`
- Even indices (1, 3, 5) → `lo = 0x5`

### DPI slot vs DPI count b2 offset

```
b2_dpi_slot = (b2_dpi_count + 0x50) & 0xFF
```

The two tables share the same `b4` lookup and differ only by a fixed `0x50` offset in `b2`.

### Full ctrl sequence (16 packets per config apply)

```
ctrl#0   2727d5fff4e57676         preamble (fixed)
ctrl#1   252d75fff8ea26ee         LOD 1/2  (LOD3: 252db5fff8eae6ee)
ctrl#2   272bd5ffe8ed7676         fixed
ctrl#3   <polling rate packet>    125/250/500/1000 Hz
ctrl#4   <dpi slot packet>        active DPI slot (0–6)
ctrl#5   <light mode ctrl5>       LED on/off + effect type
ctrl#6   <light mode ctrl6>       effect params / color variant
ctrl#7   272a8dfff05d7636         fixed
  — EP3 OUT ×8 (32B each) —
ctrl#8   272a85ffe85d7636         fixed
ctrl#9   <dpi count packet>       number of active slots (1–7)
ctrl#10  272d55ffe86d7876         fixed
  — EP3 OUT: button map —
  — EP3 OUT: timing —
  — EP3 OUT: zeros —
  — EP3 OUT: scroll —
ctrl#11  272d2dff006d7876         fixed
  — EP3 OUT: commit (ff 00...) —
ctrl#12  272bf5fff85d76d6         fixed
ctrl#13  <key_response + LOD>     debounce + lift-off encoded jointly
ctrl#14  272c6d024022ccd6         fixed
ctrl#15  272bb5fff0057676         fixed
```

### Light modes (ctrl#5 / ctrl#6)

| Name | ctrl#5 | ctrl#6 |
|------|--------|--------|
| standard (default) | `272b85049842556e` | `272afdffe83577f6` |
| off | `272b6dfff03d7676` | `272afdffe83577f6` |
| breathing | `272b85049842556e` | `272b2dff0035668e` |
| neon | `272b85049842556e` | `272dcdffe83567f6` |
| wave | `272b85049842556e` | `272dd5fff834f68e` |
| key-reaction | `272b85049842556e` | `272dadffc83567f6` |
| trailing | `272b85049842556e` | `272dadffd034f68e` |
| drag | `272b85049842556e` | `272b35ffe0356686` |
| slide | `272b85049842556e` | `272b0dffd8356686` |
| yo-yo | `272b85049842556e` | `272d0dff2835e7f6` |
| marbles | `272b85049842556e` | `272dbdff30357ff6` |
| flying-star | `272b85049842556e` | `272d8dff40357ff6` |

### Standard mode color variants

**Verified from `luom g10-light-2.pcapng` and `luom g10-colors.pcapng`.**

Protocol:
- **ctrl#5** encodes the color (different packet per color)
- **ctrl#6** = `272b65ffe8357d6e` (b2=0x65) — **fixed for ALL single-color modes**
- multicolor/rainbow = standard ctrl#5 + ctrl#6 b2=`0x75`

#### Known single-color ctrl#5 packets

| Color | ctrl#5 |
|-------|--------|
| white (default) | `272b85049842556e` |
| ~red | `272d4d04a03c6f8e` |
| ~green | `272bc5ff703d8596` |
| ~blue | `27293dffe843b67e` |

Colors are device firmware slots (not exact #FF0000 etc.).
cyan / magenta / yellow / gray — need additional pcap captures.

#### ctrl#6 variants (standard mode)

| Variant | ctrl#6 | b2 | b6 |
|---------|--------|-----|-----|
| multicolor (rainbow) | `272b75ffe8356d6e` | `0x75` | `0x6D` |
| single-color (any) | `272b65ffe8357d6e` | `0x65` | `0x7D` |

Checksum invariant: `(b2 + b6) & 0xFF == 0xE2`.

**Previous (WRONG) hypothesis** (disproved): EP3 F0 slot[7] controls color → NO.
EP3 F0 is only used for rainbow palette in multicolor mode.


### Key response + LOD encoding (ctrl#13)

`b2` and `b4` are taken from `KR_TABLE[kr_index]`.
LOD 1 modifier: `b2 += 0x08`, `b4 = 0xE8`.

```python
KR_TABLE = [
    (0x2B, 0x8D, 0x76, 0x86),  # 0 =   1 ms
    (0x2B, 0x9D, 0x76, 0x96),  # 1 =   2 ms
    (0x2B, 0x95, 0x76, 0x9E),  # 2 =   3 ms
    (0x2B, 0x6D, 0x76, 0xA6),  # 3 =   4 ms
    (0x2B, 0x65, 0x76, 0xAE),  # 4 =   5 ms
    (0x2B, 0x7D, 0x76, 0xB6),  # 5 =   6 ms
    (0x2B, 0x4D, 0x76, 0xC6),  # 6 =   7 ms
    (0x2B, 0x15, 0x76, 0x1E),  # 7 =   8 ms
    (0x2A, 0xC5, 0x76, 0x4E),  # 8 =   9 ms
    (0x2A, 0x95, 0x77, 0x9E),  # 9 =  10 ms
    (0x2A, 0x55, 0x77, 0xDE),  # 10 = 20 ms
    (0x2B, 0xB5, 0x76, 0x7E),  # 11 = 100 ms (default)
]
# ctrl#13 = bytes([0x27, b1, b2, 0xFF, b4, 0xFD, b6, b7])
```

### DPI encoding

```
USB register: reg = (cpi // 50) - 1
Profile file: val = cpi // 50  (val = reg + 1)
```

---

## Windows Driver DLLs

### MSDriver.dll (internal name: hiddriver.dll)

Generic HID wrapper. **No hardcoded protocol packets** — packet construction is in the main EXE.

| Export | Equivalent in luom_config.py |
|--------|------------------------------|
| `Set_VIDPID(vid, pid)` | `usb.core.find(idVendor=VID, idProduct=PID)` |
| `Open_FeatureDevice()` | `dev.set_configuration()` + `detach_kernel_driver` |
| `SetFeature(buf[8B])` | `dev.ctrl_transfer(0x21, 0x09, 0x0300, 2, data)` |
| `GetFeature(buf)` | HID GET_FEATURE (not used in config write path) |
| `Open_ReportDevice()` | Opens EP3 OUT + EP1 IN handles |
| `WriteUSB(buf[32B])` | `dev.write(0x03, data, timeout=1000)` |
| `ReadUSB(buf[7B])` | `dev.read(0x81, 7)` — HID mouse reports |
| `Open_DevMonitor(hwnd)` | `RegisterDeviceNotification` for plug/unplug |
| `Close_*` | `usb.util.dispose_resources` + `attach_kernel_driver` |

**Windows port**: a ctypes wrapper around `MSDriver.dll` would allow running the tool
on Windows without admin rights or WinUSB driver replacement.

### Hook.dll

Windows keyboard/mouse hook (`SetWindowsHookEx`). Used for macro recording/playback.
Exports: `installhook`, `installmousehook`, `enablehook`, `enablemousehook`, `removehook`, `removemousehook`, `MouseMoveHook`.

### IsTask.dll

System utilities: `RunTask`, `KillTask`, `ExecConsoleAppX`, `SerialNumberDisk`, `SerialNumberHDD`.
Used by the driver app for process management and hardware ID.

### DuiLib.dll

DirectUI rendering framework. UI-only, irrelevant to the protocol.

---

## Profile Binary Format (.bin / .pbin)

File size: **57,088 bytes** (mostly zero-padded).

### Header block (0x00–0x13F)

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| `0x00` | 16B | Profile name | UTF-16LE, null-terminated |
| `0x64` | 4B | DPI slots enabled | int32 |
| `0x68` | 4B | Lift-off (duplicate?) | int32, same as 0x80 |
| `0x6C` | 4B | Polling rate index (?) | `5` in all captured profiles |
| `0x78` | 4B | Motion sync A | int32, always 10 |
| `0x7C` | 4B | Motion sync B | int32, always 10 |
| `0x80` | 4B | **Lift-off distance** | int32, 1–3 |
| `0x84` | 4B | **Active DPI slot** | int32, 0-based |
| `0x88` | 4B | **DPI count** | int32, 1–7 |
| `0x8C` | 4B | **Debounce ms** | int32 (raw ms value) |
| `0x90`–`0xA4` | 4B×6 | **DPI slots** | int32; `val × 50 = CPI` |
| `0xA8`–`0xC4` | 4B×8 | Scroll step %? | 10,20,30,40,50,60,70,80 |
| `0xC8`–`0xCC` | 4B×2 | Button enable mask | `0x01010101` × 2 = 8 buttons |
| `0xD6` | 3B×9 | **Color palette 1** | 9 × RGB |
| `0x11A` | 3B×9 | **Color palette 2** | 9 × RGB |
| `0x100` | 4B | Button type | `0x02` = standard |
| `0x104` | 4B | Button LED color | RGB + alpha |
| `0x108` | 8B | Button active mask | `01 01 01 01 01 01 01 00` |
| `0x138` | 1B | **Light mode ID** | 1=standard, 2=off, 3=breathing, 4=neon… |
| `0x139` | 1B | Unknown | `0x07` in all captures |

### Light mode ID table

| ID | Mode |
|----|------|
| 1 | standard |
| 2 | off |
| 3 | breathing |
| 4 | neon |
| 5 | wave |
| 6 | key-reaction |
| 7 | trailing |
| 8 | drag |
| 9 | slide |
| 10 | yo-yo |
| 11 | marbles |
| 12 | flying-star |

### Button binding table (0x200–end)

**Stride: 0x6DB (1755 bytes) per entry. ~32 entries total.**

Each entry format: `[action_a] [action_b] [extra] 0x00 + FF×8 + zeros`

Known action codes:

| Code | Action |
|------|--------|
| `0x01` | LMB |
| `0x02` | RMB |
| `0x03` | MMB |
| `0x04` | Back |
| `0x05` | Forward |
| `0x06` | DPI+ |
| `0x07` | DPI- |
| `0x08` | DPI cycle |
| `0x0B` | Scroll Up |
| `0x0C` | Scroll Down |
| `0x19` | DPI lock (?) |

> This table contains the full **button remapping** data.
> Implementing `--button-remap` in the script requires capturing
> the corresponding EP3 packet 4 (button map, 32B) with custom bindings.

### DPI encoding difference (file vs USB)

```
File:  val = cpi // 50        (e.g. 800 CPI → 16)
USB:   reg = (cpi // 50) - 1  (e.g. 800 CPI → 15)
```

### Open questions / next steps

- **Single colors**: ctrl#6 b2 encodes color but mapping unknown.
  `(b2 + b6) & 0xFF == 0xE2` invariant holds. Difference between multicolor and white: `0x10`.
  Hypothesis: b2 = `0x75 - n*0x10` where n = palette index. Unverified.
  **Action**: capture pcap with each color selected in Windows UI (`btn_fix_color`).
- **EP3 F0/F1 role**: confirmed NOT used for single-color selection.
  Likely only controls the color cycle palette in rainbow/multicolor mode.
- `0x6C` in .pbin: polling rate index? Needs profiles with different polling rates.
  Value `5` in all captures — hypothesis: `{1:125, 2:250, 3:500, 4:1000, 5:?}`
- `0x139` in .pbin: always `7` — unknown role.
- `mode13`, `mode14`: captured in pcap, effect visually unidentified.
  `mode13` ctrl#6=`272d9dff383567f6`, `mode14` ctrl#6=`272b65fff0357676`.
