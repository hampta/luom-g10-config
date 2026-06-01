# LUOM G10 Configuration Tool

Reverse-engineered CLI configurator for the **LUOM G10** mouse (Holtek `0x04D9:0xA09F`).
Protocol fully decoded from USBPcap captures. No Windows driver needed.

## Requirements

- Python 3.8+
- `pyusb` → `pip install pyusb`
- Linux: `sudo` or udev rule for USB access

## Usage

```bash
# Show last applied config (no USB needed)
python3 luom_config.py --get

# Apply default factory config
sudo python3 luom_config.py --default

# Full example
sudo python3 luom_config.py \
  --polling-rate 1000 \
  --lift-off 2 \
  --key-response 4 \
  --light-mode breathing \
  --dpi 400 800 1600 3200 6400 12800 \
  --dpi-count 4 \
  --active-dpi 1
```

## Options

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--dpi` | 6 × N (mult of 50) | 300 500 900 1400 2400 4800 | CPI per slot |
| `--force-dpi` | N | — | All 6 slots same CPI |
| `--active-dpi` | 0–6 | 0 | Active slot index |
| `--dpi-count` | 1–7 | 7 | How many slots the DPI button cycles |
| `--polling-rate` | 125/250/500/1000 | 1000 | Hz |
| `--lift-off` | 1/2/3 | 2 | Lift-off distance (1=low, 3=high) |
| `--key-response` | 1–10,20,100 | 100 | Debounce time in ms |
| `--light-mode` | see below | standard | LED effect |
| `--swap-lr` | flag | off | Swap L/R buttons |

### Light modes

`standard`, `off`, `breathing`, `neon`, `wave`, `key-reaction`,
`trailing`, `drag`, `slide`, `yo-yo`, `marbles`, `flying-star`

> **Note:** Mode–ctrl packet mapping is derived from pcap captures.
> `mode13`/`mode14` are unidentified and commented out pending verification.

## State persistence

Config is saved to `~/.config/luom_g10.json` on every write.
`--get` reads from this file (device is write-only over USB).

## Protocol notes

- VID `0x04D9`, PID `0xA09F` (Holtek Semiconductor)
- Configuration: EP3 OUT, 8 × 32-byte interrupt-out burst + 16 EP0 ctrl packets
- HID reports: EP1 IN, 7 bytes @ 125–1000 Hz
- DPI encoding: `reg = (cpi // 50) - 1`
- `lift_off LOD1` applies `+0x08` offset to key-response ctrl packet b2, sets b4=`0xE8`
- All ctrl packets share a `(b2 + b4) & 0xFF` checksum scheme

## Files

| File | Description |
|------|-------------|
| `luom_config.py` | Main CLI tool |
