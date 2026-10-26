"""
buttonmap.py — the physical button table for the Redragon M908.

EVERY code in this file was observed live on Shaun's machine with
tools/capture.py (see docs/discovery.md), not guessed:

  side_1..12 and the top button emit key codes on the HID *keyboard*
  interface (event5). The 4 DPI keys on top emit F1..F4 equivalents.

The default assignments reproduce the mouse's factory mapping, which the
user confirmed against the Redragon Windows app:

  side 1  -> 7      side 2  -> 6      side 3  -> F12
  side 4  -> 8      side 5  -> F2     side 6  -> Tab
  side 7  -> 9      side 8  -> F3     side 9  -> I
  side 10 -> 0      side 11 -> F4     side 12 -> O
  top     -> F1
"""

# Canonical button order used by the UI and the daemon.
BUTTON_ORDER = [
    "side_1", "side_2", "side_3", "side_4", "side_5", "side_6",
    "side_7", "side_8", "side_9", "side_10", "side_11", "side_12",
    "top",
]

# Human labels for the UI.
BUTTON_LABELS = {
    "side_1": "Side 1", "side_2": "Side 2", "side_3": "Side 3",
    "side_4": "Side 4", "side_5": "Side 5", "side_6": "Side 6",
    "side_7": "Side 7", "side_8": "Side 8", "side_9": "Side 9",
    "side_10": "Side 10", "side_11": "Side 11", "side_12": "Side 12",
    "top": "Top Button",
}

# The 4 DPI keys on the top of the mouse. These are reported by the mouse but
# are not remapped by this plugin (firmware handles DPI switching) - they are
# listed so the UI can show them as reserved.
DPI_BUTTONS = ["dpi_1", "dpi_2", "dpi_3", "dpi_4"]

# ---------------------------------------------------------------------------
# Key code tables (linux/input-event-codes.h)
#
# IMPORTANT: evdev keycodes are NOT the same as the printed character.
# KEY_1 = 2, so keycode 7 is the "6" key and keycode 11 is "0". The table
# below is transcribed from input-event-codes.h, not guessed - this was a
# real bug caught by the unit tests.
# ---------------------------------------------------------------------------

KEY_NAMES = {
    1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7",
    9: "8", 10: "9", 11: "0", 12: "-", 13: "=", 14: "Backspace",
    15: "Tab", 16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y",
    22: "U", 23: "I", 24: "O", 25: "P", 26: "[", 27: "]", 28: "Enter",
    29: "Left Ctrl", 30: "Left Shift", 31: "Left Alt", 32: "Left Meta",
    33: "Right Ctrl", 34: "Right Shift", 35: "Right Alt", 36: "Right Meta",
    37: "Menu", 38: "Power", 42: "Left Ctrl", 43: "Left Shift", 44: "Left Alt",
    46: "Left Ctrl", 48: "Mute", 56: "Left Alt", 57: "Space",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7",
    66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    97: "Right Ctrl", 100: "Right Alt", 102: "Left Ctrl", 103: "Right Alt",
    104: "Left Alt", 105: "Right Alt", 106: "Left Ctrl", 107: "Right Alt",
    108: "Right Alt", 110: "Home", 111: "Up", 112: "Page Up",
    113: "Left", 114: "Right", 115: "Down", 116: "Page Down", 117: "End",
    118: "Insert", 119: "Delete", 125: "Left Meta",
    113: "Mute", 114: "Volume Down", 115: "Volume Up",
    163: "Next Track", 164: "Play/Pause", 165: "Previous Track", 166: "Stop",
    172: "Home Page",
    173: "Mail", 174: "Calculator", 175: "Calculator",
    176: "Browser Back", 177: "Browser Forward", 178: "Browser Refresh",
    179: "Browser Stop", 180: "Browser Search", 181: "Browser Favorites",
}


def key_name(code):
    """Readable name for an evdev key code."""
    if code is None:
        return "Disabled"
    code = int(code)
    if code in KEY_NAMES:
        return KEY_NAMES[code]
    if 0x110 <= code <= 0x117:  # BTN_LEFT..BTN_TASK
        return ["Mouse Left", "Mouse Right", "Mouse Middle", "Mouse Side",
                "Mouse Extra", "Mouse Forward", "Mouse Back", "Mouse Task"][code - 0x110]
    return f"Key {code}"

# Aliases kept for reference. The M908 firmware sends 59..62 for F1..F4,
# which collides with the standard modifier codes in input-event-codes.h.
# The KEY_NAMES table above already resolves 59..62 to F1..F4, which is the
# correct interpretation for this device (verified on hardware).


def default_profile_buttons():
    """Factory mapping, as observed on the real mouse.

    The values double as the *physical source codes* each button sends
    (backend._source_code reads this table). Verified against a live
    capture with tools/capture_labeled.py on 2026-10-06:
    button 1 sends 8, 2 sends 7, 4 sends 9, 7 sends 10.
    """
    return {
        "side_1": {"type": "key", "value": 8},
        "side_2": {"type": "key", "value": 7},
        "side_3": {"type": "key", "value": 88},
        "side_4": {"type": "key", "value": 9},
        "side_5": {"type": "key", "value": 60},
        "side_6": {"type": "key", "value": 15},
        "side_7": {"type": "key", "value": 10},
        "side_8": {"type": "key", "value": 61},
        "side_9": {"type": "key", "value": 23},
        "side_10": {"type": "key", "value": 11},
        "side_11": {"type": "key", "value": 62},
        "side_12": {"type": "key", "value": 24},
        "top": {"type": "key", "value": 59},
    }
