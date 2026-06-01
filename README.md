# LUOM G10 Configuration Tool

Reverse-engineered CLI configurator for the **LUOM G10** (Hator Pulsar 2 Pro) mouse (Holtek `0x04D9:0xA09F`).  
Protocol fully decoded from USBPcap captures. No Windows driver or proprietary software needed.

---

## Status

- [x] DPI — 6 slots (×50, ≤12800 CPI)
- [x] Active DPI slot (0–6)
- [x] DPI slot count (1–7)
- [x] Polling rate (125 / 250 / 500 / 1000 Hz)
- [x] Lift-off distance (3 levels)
- [x] Key debounce (1–10 / 20 / 100 ms)
- [x] Light modes (12 effects)
- [x] Standard color variant (`multicolor`, `white`, `red`, `green`, `blue`)
- [x] RGB solid color customization (`--color RRGGBB`) via multicolor palette hack
- [x] Button remapping (`--remap`) for standard keys + DPI
- [x] Config persistence (`~/.config/luom_g10.json`)
- [x] Factory defaults (`--default`)
- [ ] `mode13`, `mode14` — captured from pcap, effect unidentified
- [ ] Multimedia / Macro button mapping (requires Windows pcap captures)
- [ ] Windows / macOS support
- [x] Firmware read-back (verified: hardware does not support reading)

---



## Supported Devices

| Product | VID | PID |
|---------|-----|-----|
| LUOM G10 | `0x04D9` | `0xA09F` |
| Hator Pulsar 2 Pro (rebrand) | `0x04D9` | `0xA09F` |

---

## Requirements

- Python **3.8+**
- [`pyusb`](https://github.com/pyusb/pyusb)
- `libusb-1.0` system library
- Linux: `sudo` or a udev rule for raw USB access

---

## Installation

### 1. Install system dependency

```bash
# Debian / Ubuntu / Mint
sudo apt install libusb-1.0-0

# Arch / Manjaro
sudo pacman -S libusb

# Fedora / RHEL
sudo dnf install libusb1
```

### 2. Install Python package

```bash
pip install pyusb
```

Or inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyusb
```

### 3. Clone the repository

```bash
git clone https://github.com/hampta/luom-g10-config.git
cd luom-g10-config
```

### 4. USB access — choose one option

#### Option A — run with sudo (quick)

Prefix every command with `sudo`.

#### Option B — udev rule (recommended, passwordless)

Create `/etc/udev/rules.d/99-luom-g10.rules`:

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="a09f", MODE="0666", GROUP="plugdev"
```

Reload rules and replug the mouse:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Add yourself to the `plugdev` group if needed:

```bash
sudo usermod -aG plugdev $USER
# Log out and back in for the group to take effect
```

---

## Usage

### Read last applied config (no USB needed)

```bash
python3 luom_config.py --get
```

Example output:

```
Active DPI slot : 1  (index 0)
Enabled slots   : 4 of 7
CPI per slot    : [400, 800, 1600, 3200, 6400, 12800]
Active CPI      : 400
Key response    : 4 ms  (level 3, 0=1ms fastest, 11=100ms default)
Polling rate    : 1000 Hz
Lift-off dist   : LOD 2  (1=low, 3=high)
Light mode      : breathing
Button map      : ['left', 'right', 'middle', 'forward', 'backward', 'dpi']
```

### Apply factory defaults

```bash
sudo python3 luom_config.py --default
```

### Full example

```bash
sudo python3 luom_config.py \
  --polling-rate 1000 \
  --lift-off 2 \
  --key-response 4 \
  --light-mode breathing \
  --dpi 400 800 1600 3200 6400 12800 \
  --dpi-count 4 \
  --active-dpi 1
```

### Force all DPI slots to one value

```bash
sudo python3 luom_config.py --force-dpi 1600
```

### Set static LED color and adjust brightness

The mouse firmware only has fixed preset colors. To achieve an arbitrary static RGB color, this tool uses a clever hack: it sets the mouse to "multicolor" (rainbow) mode, but fills the entire 9-slot rainbow palette with your chosen color.

```bash
# Bright Orange
sudo python3 luom_config.py --color FF6600

# Dim Orange (brightness is controlled by the RGB hex value itself!)
sudo python3 luom_config.py --color 401A00

# Built-in firmware red
sudo python3 luom_config.py --standard-color red
```

### Button Remapping

You can remap the 6 physical buttons (Left, Right, Middle, Forward, Backward, DPI) to any of the supported actions. Provide the actions in physical button order (1 through 6).

**Supported actions:** `left`, `right`, `middle`, `forward`, `backward`, `dpi`, `disabled`.

```bash
# Example: Swap Left and Right clicks (Southpaw mode)
sudo python3 luom_config.py --remap right left middle forward backward dpi

# Example: Make the DPI button act as a "Forward" button
sudo python3 luom_config.py --remap left right middle forward backward forward

# Example: Disable the side buttons (Forward/Backward)
sudo python3 luom_config.py --remap left right middle disabled disabled dpi
```

---

## Options Reference

| Flag | Type | Allowed values | Default | Description |
|------|------|----------------|---------|-------------|
| `--get` | flag | — | — | Print last saved config (no USB required) |
| `--default` | flag | — | — | Apply factory defaults |
| `--dpi` | 6 × int | multiples of 50, ≤ 12800 | 300 500 900 1400 2400 4800 | CPI for each of the 6 slots |
| `--force-dpi` | int | multiple of 50, ≤ 12800 | — | Set all 6 slots to the same CPI |
| `--active-dpi` | int | 0 – 6 | 0 | Active DPI slot index (0-based) |
| `--dpi-count` | int | 1 – 7 | 7 | How many slots the DPI button cycles through |
| `--polling-rate` | int | 125, 250, 500, 1000 | 1000 | Report rate in Hz |
| `--lift-off` | int | 1, 2, 3 | 2 | Lift-off distance (1 = low, 3 = high) |
| `--key-response` | int | 1–10, 20, 100 | 100 | Button debounce time in ms |
| `--light-mode` | str | see below | `standard` | LED lighting effect |
| `--standard-color` | str | `multicolor`, `white`, `red`, `green`, `blue` | `multicolor` | Use a built-in firmware color preset for standard mode |
| `--color` | hex | `RRGGBB` (e.g., `FF0000`) | — | Set a custom static RGB color (and adjust brightness) using the multicolor hack |
| `--remap` | list | see below | (default map) | Remap physical buttons 1-6 in order. Allowed: `left`, `right`, `middle`, `forward`, `backward`, `dpi`, `disabled` |

### Light modes

| Value | Effect |
|-------|--------|
| `standard` | Static rainbow (default) |
| `off` | LED off |
| `breathing` | Slow breathing |
| `neon` | Neon pulse |
| `wave` | Color wave |
| `key-reaction` | Reacts to button clicks |
| `trailing` | Trail on movement |
| `drag` | Drag back-and-forth |
| `slide` | Slide effect |
| `yo-yo` | Yo-yo bounce |
| `marbles` | Marbles pattern |
| `flying-star` | Flying star |

> `mode13` and `mode14` are captured from pcap but unidentified — commented out pending verification.

---

## State Persistence

Config is written to `~/.config/luom_g10.json` after every successful apply.  
`--get` reads from this file — **the device is write-only over USB** and cannot be queried back.

Example saved state:

```json
{
  "active_slot": 0,
  "cpi": [400, 800, 1600, 3200, 6400, 12800],
  "button_map": ["left", "right", "middle", "forward", "backward", "dpi"],
  "dpi_count": 4,
  "key_response": 3,
  "polling_rate": 1000,
  "lift_off": 2,
  "light_mode": "breathing"
}
```

---

## Protocol Notes

| Property | Value |
|----------|-------|
| VID / PID | `0x04D9` / `0xA09F` (Holtek Semiconductor) |
| Config channel | EP3 OUT — 8 × 32-byte interrupt-out burst |
| Control packets | 16 EP0 HID class `SET_REPORT` packets |
| HID reports | EP1 IN, 7 bytes @ 125–1000 Hz |
| DPI encoding | `reg = (cpi // 50) - 1` |
| Checksum | `(b2 + b4) & 0xFF` per control packet |

Key protocol quirks:

- **LOD 1** — adds `+0x08` offset to `ctrl#13 b2`, sets `b4 = 0xE8`
- **LOD 3** — uses a different preamble byte in `ctrl#1` (`0xb5` vs `0x75`)
- **Light mode** — encoded in `ctrl#5` + `ctrl#6`; EP3 color data is identical across all modes
- **Active DPI slot** (`ctrl#5`) and **DPI count** (`ctrl#9`) share `byte[4]`

---

## Files

| File | Description |
|------|-------------|
| `luom_config.py` | Main CLI configuration tool |
| `analyze_light.py` | Developer tool: parse and analyze USBPcap `.pcapng` captures |
| `pcap/` | Raw pcap captures used for protocol reverse engineering |

### analyze_light.py

Developer/research tool. Parses `pcap/luom_g10_light.pcapng` and prints:

- Endpoint breakdown (EP1 HID vs EP3 lighting frames)
- Mouse click / movement / scroll events
- Lighting sessions grouped by 500 ms gap, with frame type identification
- Color table extracted from EP3 interrupt-out frames

```bash
python3 analyze_light.py
```

> Requires the pcap file. Not needed for normal mouse configuration.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Error: LUOM G10 ... not found` | Mouse not plugged in, or wrong VID/PID. Verify with `lsusb \| grep 04d9`. |
| `USBError: [Errno 13] Access denied` | Run with `sudo` or apply the udev rule (see §4). |
| `ModuleNotFoundError: usb` | Run `pip install pyusb`. |
| `libusb not found` | Install `libusb-1.0-0` (apt) / `libusb` (pacman) / `libusb1` (dnf). |
| Settings lost after reboot | Expected — re-apply with `luom_config.py`. Mouse stores config internally on write. |
| `--get` shows stale values | State file is from a previous session. Re-apply config to sync. |
