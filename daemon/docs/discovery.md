# Phase 0 Discovery — Redragon M908 on Omarchy

Date: 2026-09-19
Machine: Arch Linux, Hyprland/Wayland, Omarchy

## 1. Device identification

| Field | Value |
|---|---|
| Marketing name | Redragon M908 Impact (per `lsusb` string) |
| VID:PID | `04d9:fc4d` |
| Vendor | Holtek Semiconductor, Inc. |
| bcdDevice | 1.52 |
| bNumInterfaces | 3 |
| Bus | 003 |

### Interfaces

| # | hidraw | Class/Subclass/Protocol | evdev | Purpose |
|---|---|---|---|---|
| 0 | hidraw0 | 3/1/2 (Mouse) | `event4`, `mouse0` | Pointer, REL axes |
| 1 | hidraw1 | 3/1/1 (Keyboard) | `event5`, `kbd` | **Side button keypad** |
| 2 | hidraw2 | 3/0/0 (None/vendor) | `event6`, `event7` | Consumer control + vendor protocol |

Interface 1 is the separate keyboard-style interface the side buttons use, as the PRD predicted.

### `/sys` identity

```
HID_ID=0003:000004D9:0000FC4D
HID_NAME=USB Gaming Mouse
HID_PHYS=usb-0000:00:14.0-5.2/input0..2
```

## 2. evdev capabilities of the side-button interface

Interface 1 (`event5`) KEY bitmask: `0x1000000000003` →

- bit 0 `KEY_RESERVED`
- bit 1 `KEY_ESC`
- bit 2 `KEY_1`
- bit 48 (unmapped in kernel headers — vendor code)

**This is not a number row.** Only 3 keys are declared at the HID descriptor level even though the
mouse has 12 side buttons. The remaining buttons are not exposed as standard HID keys.

### Interpretation

The declared set (`ESC`, `1`, and an unmapped bit 48) does **not** match the Windows app's default
number-row mapping shown in the user's screenshot. This is consistent with one of:

- (a) the side keypad sends raw HID reports that the kernel's `hid-generic` driver only partially decodes, or
- (b) the mouse uses a vendor protocol over interface 2 to describe its own button layout, and
  interface 1 only leaks a default subset.

**TODO: unverified** — which of (a) or (b) is true. Requires an `evtest` session with the mouse
pressed, and/or the Windows capture in Milestone 5.

## 3. Existing driver research

### libratbag / piper — installed but device unsupported

- `ratbagctl` and `piper` are installed (`/usr/sbin/`), but `ratbagctl` currently fails with
  `ModuleNotFoundError: No module named 'evdev'` (Arch packages `python-evdev` separately; it is
  available in `extra` but not installed).
- `ratbagctl list` therefore cannot run yet.
- **libratbag has NO device entry for `04d9:fc4d`.** The only Redragon-adjacent file is
  `marsgaming-mm4.device` which matches `usb:04d9:fa58` — a different PID, same Holtek vendor ID.

### CRITICAL FINDING: the Mars Gaming driver is a Holtek 04d9 protocol driver

libratbag ships a full, MIT-licensed protocol implementation at
`src/driver-marsgaming/` (libratbag 3.0.x). Its device match lives in a `.device` **data file**
(`DeviceMatch=usb:04d9:fa58`), not in C code — meaning the protocol is generic to the Holtek 04d9
family and adding a device entry is a data-only change.

Protocol observed in `marsgaming-query.c` (byte sequences copied verbatim, not invented):

```
request : 02 03 <cmd> <profile> <cmd2> 00 fa fa
reply   : feature report, first byte = report id, byte[1]=0x03 (READ), byte[2]=<cmd>
```

| Command | Request bytes after header | Read report id | Structure |
|---|---|---|---|
| current profile | `02 03 43 00 01 00 fa fa` | `0x02` | 16 B |
| resolutions/DPI | `02 03 4f <p> 2a 00 fa fa` | `0x03` | 64 B (6 stages) |
| buttons | `02 03 90 <p> 4d 00 fa fa` | `0x04` | 1024 B (up to 253) |
| polling rate | `02 03 48\|<p> 00 01 00 fa fa` | `0x02` | 16 B |
| LED | `02 03 f1 <p> 06 00 fa fa` | `0x04` | 16 B |

Report types: `0x02` = WRITE, `0x03` = READ, `0x04` = unknown, `0x06` = unknown.

Button action opcodes (`marsgaming-buttons.h`) — note these map almost 1:1 onto the actions the PRD
requires, including macros and combos:

```
0x01 left  0x02 right  0x03 middle  0x04 back  0x05 fwd
0x08 DPI cycle-up  0x09 DPI-  0x0a DPI+  0x0d profile switch
0x0e media / disable  0x0f combo key  0x10 single key  0x11 macro  0x12 fire N-times
```

Source: https://github.com/libratbag/libratbag (MIT). A local clone for reference was made at
`/tmp/lbprobe/libratbag` (read-only, throwaway).

### Other candidates checked

- `openrgb` — NOT installed. Would be the route for RGB.
- `solaar` — NOT installed, and is Logitech-only, irrelevant here.
- No Redragon M908-specific open-source driver was found by search. The Mars Gaming Holtek driver is
  the strongest existing lead.

## 4. Read-only probe — BLOCKED on permissions

A read-only probe (`/tmp/m908probe/probe_readonly.py`) was written using the byte sequences above.
It issues **only** report type `0x03` (READ) and never a write report, firmware or bootloader command.

Result:

```
PERMISSION DENIED on /dev/hidraw2
```

`/dev/hidraw*` are `crw------- root root`. The user is in groups `shaun, input, wheel` but the
`input` group grant does not cover `hidraw` nodes on this kernel. A udev rule with `TAG+="uaccess"`
is required — **this is the sudo-gated step**, and the probe cannot proceed without it.

## 5. Backend decision

**Deferred pending the probe.** The decision tree:

1. Run the read-only probe. If `byte[1]==0x03` and `byte[2]==0x4f/0x90`, the M908 speaks the Holtek
   protocol → **HardwareBackend is viable**, and the cheapest route is a libratbag `.device` file
   plus Piper for UI, rather than a bespoke daemon.
2. If the probe returns garbage or an error, fall back to **SoftwareBackend** (evdev/uinput
   remapping) and mark DPI/polling/RGB as unsupported.

Either way the PRD's rule applies: no write to the device until a verified read, a config backup in
`~/.config/m908/backup/`, and a working `--dry-run`.

## 6. What is verified vs not

**Verified on this machine:**
- VID:PID, interface count, hidraw mapping, evdev capabilities (all quoted above)
- libratbag has no `04d9:fc4d` entry
- the Mars Gaming driver's exact command byte sequences (read from source)
- `openrgb` and `python-evdev` are not installed

**Not verified:**
- Whether the M908 accepts the Holtek protocol (blocked on udev permissions)
- The mouse's real button count and each button's evdev code (needs `evtest` while pressing)
- Whether the Windows app writes config to onboard memory or only to the running app
- RGB hardware support and its protocol
- Actual DPI range/limits (screenshot suggests max 12400, stages 500–6200)

## 7. Next action required from the user

Run this (needs sudo):

```bash
sudo tee /etc/udev/rules.d/99-m908.rules >/dev/null <<'EOF'
# Redragon M908 Impact (Holtek 04d9:fc4d) — vendor protocol + side-button keypad
KERNEL=="hidraw*", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="fc4d", TAG+="uaccess"
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

Then unplug and replug the mouse. After that the read-only probe can run and the backend decision
in section 5 can be made.
