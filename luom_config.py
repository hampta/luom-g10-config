#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

import usb.core
import usb.util

STATE_FILE = os.path.expanduser("~/.config/luom_g10.json")

DEFAULT_CPI = [300, 500, 900, 1400, 2400, 4800]


def save_state(
    active_dpi,
    cpi_list,
    button_map,
    dpi_count=None,
    key_response=None,
    polling_rate=None,
    lift_off=None,
    light_mode=None,
    standard_color=None,
    custom_color=None,
):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(
            {
                "active_slot": active_dpi,  # 0-indexed (None = slot 1)
                "cpi": cpi_list,
                "button_map": button_map,
                "dpi_count": dpi_count,  # 1-7 (None = 7)
                "key_response": key_response,  # 0-11 (None = 11 = 100ms)
                "polling_rate": polling_rate,  # 125/250/500/1000 (None = 1000)
                "lift_off": lift_off,  # 1/2/3 (None = 2)
                "light_mode": light_mode,  # mode name string (None = "standard")
                "standard_color": standard_color,  # "multicolor" | "white" | etc
                "custom_color": custom_color,  # hex string RRGGBB or None
            },
            f,
            indent=2,
        )


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


BUTTON_ACTIONS = {
    "left": "0100f000",
    "right": "0100f100",
    "middle": "0100f200",
    "forward": "0100f400",
    "backward": "0100f300",
    "dpi": "07000100",
    "disabled": "00000000",
}
DEFAULT_BUTTON_MAP = ["left", "right", "middle", "forward", "backward", "dpi"]


def print_state():
    state = load_state()
    if state is None:
        print("No saved state found. Apply a config first with --default or --dpi.")
        return
    slot = state.get("active_slot")
    cpi = state.get("cpi", DEFAULT_CPI)
    active_idx = slot if slot is not None else 0
    n_slots = state.get("dpi_count") or 7
    kr_display = state.get("key_response") or 11
    MS_MAP = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 100]
    poll = state.get("polling_rate") or 1000
    lod = state.get("lift_off") or 2
    lm = state.get("light_mode") or "standard"
    sc = state.get("standard_color")
    cc = state.get("custom_color")
    bmap = state.get("button_map")

    # Backward compatibility with old swap_lr state
    if not bmap:
        swap = state.get("swap_lr", False)
        bmap = (
            ["right", "left", "middle", "forward", "backward", "dpi"]
            if swap
            else DEFAULT_BUTTON_MAP
        )

    print(f"Active DPI slot : {active_idx + 1}  (index {active_idx})")
    print(f"Enabled slots   : {n_slots} of 7")
    print(f"CPI per slot    : {cpi}")
    print(f"Active CPI      : {cpi[active_idx] if active_idx < len(cpi) else '?'}")
    print(
        f"Key response    : {MS_MAP[kr_display]} ms  (level {kr_display}, 0=1ms fastest, 11=100ms default)"
    )
    print(f"Polling rate    : {poll} Hz")
    print(f"Lift-off dist   : LOD {lod}  (1=low, 3=high)")
    light_str = lm
    if cc:
        light_str += f"  (custom color: #{cc})"
    elif sc:
        light_str += f"  (color: {sc})"
    print(f"Light mode      : {light_str}")
    print(f"Button map      : {bmap}")


VID = 0x04D9
PID = 0xA09F


class LUOMMouse:
    def __init__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            print(
                "Error: LUOM G10 / Hator Pulsar (04d9:a09f) not found.", file=sys.stderr
            )
            sys.exit(1)

        self.detached_interfaces = []
        for i in range(3):
            if self.dev.is_kernel_driver_active(i):
                try:
                    self.dev.detach_kernel_driver(i)
                    self.detached_interfaces.append(i)
                except usb.core.USBError:
                    pass
        self.dev.set_configuration()

    def ctrl(self, data_hex):
        data = bytes.fromhex(data_hex)
        self.dev.ctrl_transfer(0x21, 0x09, 0x0300, 2, data)
        time.sleep(0.01)

    def out(self, data_hex):
        if isinstance(data_hex, str):
            data = bytes.fromhex(data_hex)
        else:
            data = data_hex
        self.dev.write(0x03, data, timeout=1000)
        time.sleep(0.01)

    def cleanup(self):
        usb.util.dispose_resources(self.dev)
        for i in self.detached_interfaces:
            try:
                self.dev.attach_kernel_driver(i)
            except usb.core.USBError:
                pass

    def apply_config(
        self,
        button_map=None,
        dpi_list=None,
        force_dpi=None,
        active_dpi=None,
        dpi_count=None,
        key_response=None,
        polling_rate=None,
        lift_off=None,
        light_mode=None,
        standard_color=None,
        custom_color=None,
    ):
        print("Applying configuration...")
        # Resolve the CPI list we're actually writing, for state persistence
        if force_dpi is not None:
            effective_cpi = [force_dpi] * 6
        elif dpi_list:
            effective_cpi = list(dpi_list) + [dpi_list[-1]] * (6 - len(dpi_list))
        else:
            effective_cpi = list(DEFAULT_CPI)

        # Preamble ctrl packets
        # ctrl#1: polling rate selector (default = 1000 Hz)
        polling_packets = {
            125: "272b85ff30d57676",
            250: "272ba5ffd0d57676",
            500: "272bd5ff00d57676",
            1000: "272bddffe8d57676",  # default
        }
        # ctrl#0 (fixed), ctrl#1 (lift-off overrides preamble byte), ctrl#2 (fixed), ctrl#3 (polling)
        self.ctrl("2727d5fff4e57676")
        # ctrl#1: LOD3 uses different preamble byte
        if lift_off == 3:
            self.ctrl("252db5fff8eae6ee")  # LOD3: b[2]=0xb5, b[6]=0xe6
        else:
            self.ctrl("252d75fff8ea26ee")  # LOD1,2 or default
        self.ctrl("272bd5ffe8ed7676")
        self.ctrl(
            polling_packets.get(
                polling_rate if polling_rate is not None else 1000,
                polling_packets[1000],
            )
        )

        # The 5th ctrl packet selects the active DPI slot.
        # ctrl pkt #9 selects max number of enabled DPI slots (1-7, default=7).
        # Both tables share the same byte[4]; byte[2] of pkt#9 = slot_b2 - offset.
        # Derived from PCAP "dpi levels" + "dpi levels count".
        dpi_slot_packets = {
            0: "272b6dffe8257676",  # Slot 1
            1: "272b65ff00257676",  # Slot 2
            2: "272b7dfff8257676",  # Slot 3
            3: "272b75ffd0257676",  # Slot 4
            4: "272b4dffc8257676",  # Slot 5
            5: "272b45ffe0257676",  # Slot 6
            6: "272b5dffd8257676",  # Slot 7
        }
        dpi_count_packets = {
            1: "272b1dffe85576b6",  # 1 active slot
            2: "272b15ff005576b6",  # 2 active slots
            3: "272bedfff85576b6",  # 3 active slots
            4: "272be5ffd05576b6",  # 4 active slots
            5: "272bfdffc85576b6",  # 5 active slots
            6: "272bf5ffe05576b6",  # 6 active slots
            7: "272acdffd85576b6",  # 7 active slots (default)
        }

        p5_ctrl = (
            dpi_slot_packets.get(active_dpi, dpi_slot_packets[0])
            if active_dpi is not None
            else dpi_slot_packets[0]
        )

        self.ctrl(p5_ctrl)

        # ctrl#5 = light mode selector (LED on/off + effect type)
        # ctrl#6 = effect parameters (speed, pattern variant)
        # Derived from PCAP "luom g10-light.pcapng" (14 sessions = 14 mode/param combos)
        # S1=Standard(default), S2=Off(ctrl#5 changes), S3-S13=Breathing→Flying star
        LIGHT_MODES = {
            # name:             (ctrl5,                  ctrl6)
            "standard": ("272b85049842556e", "272afdffe83577f6"),  # S1 (default)
            "off": ("272b6dfff03d7676", "272afdffe83577f6"),  # S2
            "breathing": ("272b85049842556e", "272b2dff0035668e"),  # S3
            "neon": ("272b85049842556e", "272dcdffe83567f6"),  # S4
            "wave": ("272b85049842556e", "272dd5fff834f68e"),  # S5
            "key-reaction": ("272b85049842556e", "272dadffc83567f6"),  # S6
            "trailing": ("272b85049842556e", "272dadffd034f68e"),  # S7
            "drag": ("272b85049842556e", "272b35ffe0356686"),  # S8 drag-back-forth
            "slide": ("272b85049842556e", "272b0dffd8356686"),  # S9
            "yo-yo": ("272b85049842556e", "272d0dff2835e7f6"),  # S10
            "marbles": ("272b85049842556e", "272dbdff30357ff6"),  # S11
            "flying-star": ("272b85049842556e", "272d8dff40357ff6"),  # S12
            # "mode13": ("272b85049842556e", "272d9dff383567f6"),  # S13 (unidentified)
            # "mode14": ("272b85049842556e", "272b65fff0357676"),  # S14 (unidentified)
        }

        # Standard mode color variants (verified from luom g10-light-2.pcapng).
        # For single-color: ctrl#6 = 272b65ffe8357d6e (b2=0x65) is FIXED for all colors.
        # ctrl#5 encodes the actual color (see SINGLE_COLOR table below).
        STANDARD_COLOR_CTRL6 = {
            "multicolor": "272b75ffe8356d6e",  # b2=0x75 b6=0x6D (rainbow palette)
            "rainbow": "272b75ffe8356d6e",  # alias
        }

        ctrl5_pkt, ctrl6_pkt = LIGHT_MODES.get(
            light_mode or "standard", LIGHT_MODES["standard"]
        )
        # Standard mode color selection.
        # PROTOCOL (verified from luom g10-colors.pcapng):
        #   - ctrl#5 encodes the color (different per color)
        #   - ctrl#6 = 272b65ffe8357d6e (fixed for ALL single-color modes)
        #   - multicolor/rainbow = standard ctrl#5 + ctrl#6 b2=0x75
        #
        # Single-color ctrl#5 lookup (from pcap captures):
        SINGLE_COLOR = {
            # color: ctrl#5 packet
            "white": "272b85049842556e",  # standard ctrl#5 (verified: white/default)
            "red": "272d4d04a03c6f8e",  # pcap session 1 (~red)
            "green": "272bc5ff703d8596",  # pcap session 2 (~green)
            "blue": "27293dffe843b67e",  # pcap session 3 (~blue)
            # cyan / magenta / yellow / gray: need pcap captures
        }
        SINGLE_COLOR_CTRL6 = "272b65ffe8357d6e"  # b2=0x65, fixed for all single colors

        if light_mode is None or light_mode == "standard":
            if custom_color is not None:
                # HACK: to achieve arbitrary RGB, we use multicolor mode
                # and fill the entire rainbow palette with the same color.
                ctrl5_pkt = LIGHT_MODES["standard"][0]
                ctrl6_pkt = STANDARD_COLOR_CTRL6["multicolor"]
                print(
                    f"  custom-color: RGB {custom_color} → using multicolor palette hack"
                )
            elif standard_color is not None:
                sc_norm = standard_color.lower()
                if sc_norm in ("multicolor", "rainbow"):
                    pass  # already set correctly from LIGHT_MODES
                elif sc_norm in SINGLE_COLOR:
                    ctrl5_pkt = SINGLE_COLOR[sc_norm]
                    ctrl6_pkt = SINGLE_COLOR_CTRL6
                    print(
                        f"  standard-color: {sc_norm} → ctrl#5={ctrl5_pkt}  ctrl#6={ctrl6_pkt}"
                    )
                else:
                    print(
                        f"  Warning: unknown standard-color '{standard_color}', using default"
                    )
        self.ctrl(ctrl5_pkt)
        self.ctrl(ctrl6_pkt)
        self.ctrl("272a8dfff05d7636")

        # Packet 1: RGB color slot 1 (rainbow cycle palette, 9 × RGB)
        # Only used in multicolor mode. Device ignores this in single-color mode.
        p1 = bytearray(
            bytes.fromhex(
                "ff000000ff000000ffffff00ff00ff00ffffff8000ffffff0000000000000000"
            )
        )
        if custom_color is not None:
            r, g, b = custom_color
            for i in range(9):
                p1[i * 3] = r
                p1[i * 3 + 1] = g
                p1[i * 3 + 2] = b

        self.out(p1)
        self.ctrl("272a85ffe85d7636")

        # Packet 2: RGB color slot 2
        # ctrl pkt #9 = DPI count selector (how many DPI slots are active)
        self.out("00ff000000ffff0000ffff0000ffffff00ffffffffffffff0000000000000000")
        count_ctrl = dpi_count_packets.get(
            dpi_count if dpi_count is not None else 7, dpi_count_packets[7]
        )
        self.ctrl(count_ctrl)

        # Packet 3: DPI registers
        # Encoding: reg = (cpi // 50) - 1  →  cpi = (reg + 1) * 50
        # Default: 300, 500, 900, 1400, 2400, 4800 CPI
        #          0x05 0x09 0x11 0x1b  0x2f  0x5f
        # bytes[6:8] = 0xbd 0x5f (active-level metadata, always keep consresptant)
        p3 = bytearray(32)
        p3[6] = 0xBD
        p3[7] = 0x5F
        if force_dpi is not None:
            val = max(0, (force_dpi // 50) - 1) & 0xFF
            for i in range(6):
                p3[i] = val
        elif dpi_list:
            for i in range(min(len(dpi_list), 6)):
                p3[i] = max(0, (dpi_list[i] // 50) - 1) & 0xFF
            for i in range(len(dpi_list), 6):
                p3[i] = p3[len(dpi_list) - 1] if len(dpi_list) > 0 else 0
        else:
            p3[0:6] = bytes.fromhex("0509111b2f5f")

        self.out(p3)
        self.ctrl("272d55ffe86d7876")

        # Packet 4: button mapping
        # 32 bytes = 8 button slots (4 bytes each)
        if button_map is None:
            button_map = DEFAULT_BUTTON_MAP

        btn_hex = ""
        for i in range(6):
            action = button_map[i] if i < len(button_map) else DEFAULT_BUTTON_MAP[i]
            btn_hex += BUTTON_ACTIONS.get(action, BUTTON_ACTIONS["disabled"])

        # Slots 7 and 8 are fixed unused buttons on this model
        btn_hex += "0700010007000200"
        self.out(btn_hex)

        # Packet 5: timing/debounce (0x0B ms debounce, 0x0D ms motion)
        self.out("0b0000000d000000000000000000000000000000000000000400010004000200")
        self.ctrl("272d2dff006d7876")

        # Packet 6: reserved (all zeros)
        self.out("0000000000000000000000000000000000000000000000000000000000000000")

        # Packet 7: scroll config
        self.out("0b0000000d000000000000000000000000000000000000000000000000000000")
        self.ctrl("272bf5fff85d76d6")

        # Packet 8: commit/apply
        self.out("ff00000000000000000000000000000000000000000000000000000000000000")

        # ctrl#13 = key response + lift-off distance (encoded jointly)
        # key_response: 12 levels, b4=0x00 always, lookup defines b1/b2/b6/b7
        # lift_off LOD1: adds +0x08 to b2, sets b4=0xe8 (verified from pcap formula)
        # lift_off LOD2,3: no change to ctrl#13
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
        kr_idx = key_response if key_response is not None else 11
        kr_idx = max(0, min(11, kr_idx))
        b1, b2, b6, b7 = KR_TABLE[kr_idx]
        b4 = 0x00
        if lift_off == 1:
            b2 = (b2 + 0x08) & 0xFF
            b4 = 0xE8
        ctrl13 = bytes([0x27, b1, b2, 0xFF, b4, 0xFD, b6, b7])
        self.ctrl(ctrl13.hex())
        self.ctrl("272c6d024022ccd6")
        self.ctrl("272bb5fff0057676")

        # Persist state so --get works without USB access
        cc_hex = "%02X%02X%02X" % tuple(custom_color) if custom_color else None
        save_state(
            active_dpi,
            effective_cpi,
            button_map,
            dpi_count,
            key_response,
            polling_rate,
            lift_off,
            light_mode,
            standard_color,
            cc_hex,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hator Pulsar / LUOM G10 Configuration Tool"
    )
    parser.add_argument(
        "--get", action="store_true", help="Print last applied configuration"
    )
    parser.add_argument("--default", action="store_true", help="Apply default config")
    parser.add_argument(
        "--remap",
        nargs="+",
        metavar="ACTION",
        help=f"Remap physical buttons 1 to 6 in order. Allowed actions: {', '.join(BUTTON_ACTIONS.keys())}",
    )
    # Deprecated, kept for backward compatibility (hidden from help)
    parser.add_argument("--swap-lr", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--dpi",
        type=int,
        nargs=6,
        metavar="N",
        help="Set 6 CPI levels in multiples of 50 (e.g. 300 500 900 1400 2400 4800)",
    )
    parser.add_argument(
        "--force-dpi",
        type=int,
        metavar="CPI",
        help="Force all 6 slots to same CPI (multiple of 50, max 12800)",
    )
    parser.add_argument(
        "--active-dpi",
        type=int,
        metavar="INDEX",
        help="Set active DPI slot index (0 to 6)",
    )
    parser.add_argument(
        "--key-response",
        type=int,
        metavar="MS",
        choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 100],
        help="Key debounce time in ms: 1-10 (1ms steps), 20, or 100 (default)",
    )
    parser.add_argument(
        "--polling-rate",
        type=int,
        metavar="HZ",
        choices=[125, 250, 500, 1000],
        help="Polling rate in Hz: 125, 250, 500, or 1000 (default)",
    )
    parser.add_argument(
        "--lift-off",
        type=int,
        metavar="LEVEL",
        choices=[1, 2, 3],
        help="Lift-off distance: 1=low, 2=medium (default), 3=high",
    )
    LIGHT_MODE_CHOICES = [
        "standard",
        "off",
        "breathing",
        "neon",
        "wave",
        "key-reaction",
        "trailing",
        "drag",
        "slide",
        "yo-yo",
        "marbles",
        "flying-star",
        # "mode13",
        # "mode14",
    ]
    parser.add_argument(
        "--light-mode",
        metavar="MODE",
        choices=LIGHT_MODE_CHOICES,
        help=("Light effect: " + ", ".join(LIGHT_MODE_CHOICES)),
    )
    parser.add_argument(
        "--standard-color",
        metavar="COLOR",
        choices=["multicolor", "rainbow", "white", "red", "green", "blue"],
        default=None,
        help=(
            "Color for --light-mode standard. "
            "multicolor/rainbow = full rainbow cycle (default). "
            "Single colors (ctrl#5 verified from pcap): white, red, green, blue. "
            "Others (cyan/magenta/yellow/gray) need more pcap captures."
        ),
    )
    parser.add_argument(
        "--color",
        metavar="RRGGBB",
        default=None,
        help=(
            "Arbitrary single LED color for standard mode (hex RGB, e.g. FF6600). "
            "HACK: The device doesn't support custom RGB natively, so this uses "
            "multicolor mode and fills the entire cycle palette with your color."
        ),
    )
    parser.add_argument(
        "--dpi-count",
        type=int,
        metavar="N",
        choices=range(1, 8),
        help="Number of active DPI slots the DPI button cycles through (1-7, default 7)",
    )
    args = parser.parse_args()

    if args.get:
        print_state()
        sys.exit(0)

    if len(sys.argv) <= 1:
        parser.print_help()
        sys.exit(1)

    effective_standard_color = args.standard_color
    effective_custom_color = None

    if args.color is not None:
        raw = args.color.lstrip("#")
        if len(raw) != 6:
            print(f"Error: --color must be hex RRGGBB (6 chars), got '{args.color}'")
            sys.exit(1)
        try:
            effective_custom_color = (
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
            )
        except ValueError:
            print(f"Error: --color invalid hex '{args.color}'")
            sys.exit(1)
    else:
        # If color not provided, we will fall back to saved custom_color below
        pass

    # Load saved state to preserve configuration that wasn't specified on CLI
    saved = load_state() or {}

    if effective_standard_color is None:
        effective_standard_color = saved.get("standard_color")

    if args.color is None:
        cc_saved = saved.get("custom_color")
        if cc_saved:
            try:
                effective_custom_color = (
                    int(cc_saved[0:2], 16),
                    int(cc_saved[2:4], 16),
                    int(cc_saved[4:6], 16),
                )
            except (ValueError, IndexError):
                pass

    effective_dpi = args.dpi if args.dpi is not None else saved.get("cpi")
    effective_active_dpi = (
        args.active_dpi if args.active_dpi is not None else saved.get("active_slot")
    )
    effective_dpi_count = (
        args.dpi_count if args.dpi_count is not None else saved.get("dpi_count")
    )
    effective_polling_rate = (
        args.polling_rate
        if args.polling_rate is not None
        else saved.get("polling_rate")
    )
    effective_lift_off = (
        args.lift_off if args.lift_off is not None else saved.get("lift_off")
    )
    effective_light_mode = (
        args.light_mode if args.light_mode is not None else saved.get("light_mode")
    )

    # Handle button_map logic
    effective_bmap = args.remap
    if effective_bmap is None:
        if args.swap_lr:
            effective_bmap = ["right", "left", "middle", "forward", "backward", "dpi"]
        else:
            effective_bmap = saved.get("button_map")
            if not effective_bmap:
                # migrate from old swap_lr state
                if saved.get("swap_lr"):
                    effective_bmap = [
                        "right",
                        "left",
                        "middle",
                        "forward",
                        "backward",
                        "dpi",
                    ]
                else:
                    effective_bmap = DEFAULT_BUTTON_MAP

    # Validate custom button mapping
    if effective_bmap is not None:
        for action in effective_bmap:
            if action not in BUTTON_ACTIONS:
                print(
                    f"Error: Unknown button action '{action}'. Allowed: {', '.join(BUTTON_ACTIONS.keys())}"
                )
                sys.exit(1)

    mouse = LUOMMouse()
    try:
        kr = args.key_response
        kr_idx = (
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 100].index(kr)
            if kr is not None
            else saved.get("key_response")
        )
        mouse.apply_config(
            button_map=effective_bmap,
            dpi_list=effective_dpi,
            force_dpi=args.force_dpi,
            active_dpi=effective_active_dpi,
            dpi_count=effective_dpi_count,
            key_response=kr_idx,
            polling_rate=effective_polling_rate,
            lift_off=effective_lift_off,
            light_mode=effective_light_mode,
            standard_color=effective_standard_color,
            custom_color=effective_custom_color,
        )
        print("Configuration applied successfully.")
    finally:
        mouse.cleanup()
