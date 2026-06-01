#!/usr/bin/env python3
import struct
import sys
from collections import Counter, defaultdict

FILE = "pcap/luom_g10_light.pcapng"

# ─────────────────────────── pcapng parser ───────────────────────────


def iter_epb(filepath):
    """Yield (timestamp_us, raw_packet_data) for every Enhanced Packet Block."""
    with open(filepath, "rb") as f:
        data = f.read()
    pos = 0
    while pos < len(data):
        if pos + 8 > len(data):
            break
        block_type, block_len = struct.unpack_from("<II", data, pos)
        if block_len < 12 or pos + block_len > len(data):
            break
        body = data[pos + 8 : pos + block_len - 4]
        if block_type == 0x00000006:  # EPB
            if len(body) >= 20:
                iface, ts_hi, ts_lo, cap_len, orig_len = struct.unpack_from(
                    "<IIIII", body
                )
                ts_us = (ts_hi << 32) | ts_lo
                pkt = body[20 : 20 + cap_len]
                yield ts_us, pkt
        pos += block_len


# ─────────────────────────── USBPcap header ──────────────────────────


def parse_usbpcap(data):
    if len(data) < 27:
        return None
    hdr_len = struct.unpack_from("<H", data, 0)[0]
    if hdr_len < 27 or hdr_len > len(data):
        return None
    (irp_id,) = struct.unpack_from("<Q", data, 2)
    (status,) = struct.unpack_from("<I", data, 10)
    (function,) = struct.unpack_from("<H", data, 14)
    (info,) = struct.unpack_from("<B", data, 16)
    (bus,) = struct.unpack_from("<H", data, 17)
    (device,) = struct.unpack_from("<H", data, 19)
    (ep_raw,) = struct.unpack_from("<B", data, 21)
    (transfer,) = struct.unpack_from("<B", data, 22)
    (data_len,) = struct.unpack_from("<I", data, 23)
    direction = "IN" if (info & 1) else "OUT"
    ep_num = ep_raw & 0x0F
    payload = data[hdr_len : hdr_len + data_len]
    return {
        "direction": direction,
        "ep": ep_num,
        "transfer": transfer,  # 1=Interrupt, 2=Control
        "data_len": data_len,
        "payload": payload,
    }


# ─────────────────────────── HID mouse report ────────────────────────

BTN_NAMES = {0: "LMB", 1: "RMB", 2: "MMB", 3: "BACK", 4: "FWD"}


def parse_mouse_hid(payload):
    if len(payload) < 4:
        return None
    buttons = payload[0]
    dx = struct.unpack_from("<b", payload, 1)[0]
    dy = struct.unpack_from("<b", payload, 2)[0]
    scroll = struct.unpack_from("<b", payload, 3)[0]
    return {"buttons": buttons, "dx": dx, "dy": dy, "scroll": scroll}


# ─────────────────────────── lighting frame id ───────────────────────


def identify_lighting_frame(payload):
    if len(payload) < 8:
        return "?"
    p = payload
    if p[0] == 0xFF and all(b == 0 for b in p[1:]):
        return "F7_COMMIT"
    if p[0] == 0xFF and p[4] == 0xFF:
        return "F0_COLOR1"
    if p[0] == 0x00 and p[1] == 0xFF:
        return "F1_COLOR2"
    if p[0] == 0x05 and p[1] == 0x09:
        return "F2_DPI"
    if p[0] == 0x01 and p[2] == 0xF0:
        return "F3_BTNMAP"
    if p[0] == 0x0B and p[2] == 0x00 and p[4] == 0x0D and len(p) > 28 and p[28] != 0:
        return "F4_TIMING"
    if all(b == 0 for b in p):
        return "F5_ZEROS"
    if p[0] == 0x0B and p[2] == 0x00 and p[4] == 0x0D:
        return "F6_TIMING2"
    return "UNKNOWN"


# ─────────────────────────── color name helper ───────────────────────


def rgb_name(r, g, b):
    if r == 0 and g == 0 and b == 0:
        return "Black/Off"
    if r == 255 and g == 0 and b == 0:
        return "Red"
    if r == 0 and g == 255 and b == 0:
        return "Green"
    if r == 0 and g == 0 and b == 255:
        return "Blue"
    if r == 255 and g == 255 and b == 0:
        return "Yellow"
    if r == 0 and g == 255 and b == 255:
        return "Cyan"
    if r == 255 and g == 0 and b == 255:
        return "Magenta"
    if r == 255 and g == 255 and b == 255:
        return "White"
    if r == 128 and g == 0 and b == 255:
        return "Purple"
    if r == 255 and g == 128 and b == 0:
        return "Orange"
    return f"#{r:02X}{g:02X}{b:02X}"


# ─────────────────────────── main ────────────────────────────────────


def main():
    print(f"Reading: {FILE}\n")
    packets = list(iter_epb(FILE))
    if not packets:
        print("No EPB packets found.")
        return

    t0 = packets[0][0]
    total_us = packets[-1][0] - t0
    print(f"{'=' * 60}")
    print(f"Total packets  : {len(packets)}")
    print(f"Duration       : {total_us / 1e6:.3f} s")
    print(f"{'=' * 60}\n")

    ep_counter = Counter()
    mouse_events = []
    prev_buttons = 0
    cumx = cumy = 0
    scroll_total = 0
    scroll_events = 0

    lighting_frames = []  # (ts_us, frame_type, payload)

    for ts_us, raw in packets:
        h = parse_usbpcap(raw)
        if h is None or h["data_len"] == 0:
            continue
        ep = h["ep"]
        direction = h["direction"]
        payload = h["payload"]
        ep_counter[(ep, direction)] += 1

        # EP1 IN → mouse HID
        if ep == 1 and direction == "IN" and h["transfer"] == 1:
            m = parse_mouse_hid(payload)
            if m is None:
                continue
            cumx += m["dx"]
            cumy += m["dy"]
            if m["scroll"]:
                scroll_total += m["scroll"]
                scroll_events += 1
            changed = m["buttons"] ^ prev_buttons
            for bit in range(5):
                if changed & (1 << bit):
                    state = "press" if (m["buttons"] & (1 << bit)) else "release"
                    mouse_events.append((ts_us - t0, state, BTN_NAMES[bit]))
            prev_buttons = m["buttons"]

        # EP3 OUT → lighting
        if ep == 3 and direction == "OUT" and h["transfer"] == 1:
            if len(payload) == 32:
                ftype = identify_lighting_frame(payload)
                lighting_frames.append((ts_us, ftype, bytes(payload)))

    # ── endpoint summary ──
    print("Endpoint breakdown:")
    for (ep, d), cnt in sorted(ep_counter.items()):
        print(f"  EP{ep} {d:3s}: {cnt} packets")

    # ── mouse analysis ──
    print(f"\n{'─' * 60}")
    print("MOUSE ANALYSIS")
    print(f"{'─' * 60}")
    click_counts = Counter()
    for _, state, btn in mouse_events:
        if state == "press":
            click_counts[btn] += 1
    print(f"Clicks: {dict(click_counts)}")
    print(f"Movement: X={cumx:+d}  Y={cumy:+d}")
    print(f"Scroll: {scroll_events} events  total={scroll_total:+d}")
    if mouse_events:
        print(f"\nButton events:")
        for rel_us, state, btn in mouse_events:
            print(f"  +{rel_us / 1e6:7.3f}s  {state:7s}  {btn}")

    # ── lighting session analysis ──
    print(f"\n{'─' * 60}")
    print("LIGHTING ANALYSIS")
    print(f"{'─' * 60}")
    print(f"Total EP3 lighting frames: {len(lighting_frames)}")

    # group into sessions (F0 → F7, gap < 500ms within session)
    sessions = []
    cur_session = []
    for i, (ts, ftype, payload) in enumerate(lighting_frames):
        if not cur_session:
            cur_session.append((ts, ftype, payload))
        else:
            gap = ts - cur_session[-1][0]
            if gap > 500_000:  # 500 ms gap = new session
                sessions.append(cur_session)
                cur_session = [(ts, ftype, payload)]
            else:
                cur_session.append((ts, ftype, payload))
    if cur_session:
        sessions.append(cur_session)

    print(f"Sessions identified: {len(sessions)}\n")

    for s_idx, sess in enumerate(sessions):
        ts_start = sess[0][0] - t0
        ts_end = sess[-1][0] - t0
        dur = sess[-1][0] - sess[0][0]
        frame_types = [f for _, f, _ in sess]

        f0_payload = next((p for _, f, p in sess if f == "F0_COLOR1"), None)
        f1_payload = next((p for _, f, p in sess if f == "F1_COLOR2"), None)

        print(
            f"Session {s_idx + 1:2d}: +{ts_start / 1e6:.3f}s → +{ts_end / 1e6:.3f}s  "
            f"({dur / 1e3:.1f} ms)  frames={len(sess)}"
        )
        print(f"  Frame types: {frame_types}")

        # Color table
        colors = []
        if f0_payload:
            for i in range(0, 27, 3):
                r, g, b = f0_payload[i], f0_payload[i + 1], f0_payload[i + 2]
                colors.append((r, g, b))
        if f1_payload:
            for i in range(0, 27, 3):
                r, g, b = f1_payload[i], f1_payload[i + 1], f1_payload[i + 2]
                colors.append((r, g, b))
        if colors:
            named = [rgb_name(r, g, b) for r, g, b in colors]
            unique = list(dict.fromkeys(named))  # preserve order, deduplicate
            print(f"  Colors: {unique}")

        if s_idx > 0:
            gap = sess[0][0] - sessions[s_idx - 1][-1][0]
            print(f"  Gap from prev: {gap / 1e3:.1f} ms")
        print()

    # ── ctrl#5/#6 variation table ──
    print(f"{'─' * 60}")
    print(
        "NOTE: ctrl packet variation (light mode selector) is in EP0 control transfers,"
    )
    print(
        "NOT in EP3 interrupt-out packets. EP3 color data is identical across all sessions."
    )
    print("See tshark analysis for ctrl#5 and ctrl#6 packet values per session.")


if __name__ == "__main__":
    main()
