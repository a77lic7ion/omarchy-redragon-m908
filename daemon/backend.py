"""
backend.py — SoftwareBackend for the M908.

Grabs the mouse's HID keyboard interface (event5) with EVIOCGRAB and
re-emits every key event through a virtual uinput keyboard, applying the
profile's button map on the way.

Why this works without the vendor protocol: the side buttons are exposed to
Linux as *ordinary key codes* on a dedicated keyboard interface (verified in
docs/discovery.md). So remapping is pure input-layer work.

Only stdlib is used - the uinput ioctls and event struct are declared here
rather than pulling in python-evdev.

Safety rules honoured:
  - never writes to the mouse (no hidraw access at all)
  - releases EVIOCGRAB and drops the uinput device on exit or crash
  - releases every virtual key on shutdown so nothing gets stuck down
"""

import ctypes
import errno
import fcntl
import os
import select
import struct
import termios
import time

# ---------------------------------------------------------------------------
# ioctl constants
# ---------------------------------------------------------------------------

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_NONE = 0
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(direction, typechar, nr, size):
    return (
        (direction << _IOC_DIRSHIFT)
        | (ord(typechar) << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


EVIOCGRAB = _IOC(_IOC_WRITE, "E", 0x90, 4)  # int
# _IO(type, nr) == _IOC(_IOC_NONE, type, nr, 0). Using _IOC_READ here
# produces a different request number and the kernel rejects it with EINVAL.
UI_DEV_CREATE = _IOC(_IOC_NONE, "U", 1, 0)
UI_DEV_DESTROY = _IOC(_IOC_NONE, "U", 2, 0)
UI_SET_EVBIT = _IOC(_IOC_WRITE, "U", 100, 4)
UI_SET_KEYBIT = _IOC(_IOC_WRITE, "U", 101, 4)
UI_SET_RELBIT = _IOC(_IOC_WRITE, "U", 102, 4)

# input_event struct on x86_64: __kernel_ulong_t time; time; u16 type; u16 code; s32 value
EV_SIZE = struct.calcsize("llHHi")

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y, REL_WHEEL, REL_HWHEEL = 0x00, 0x01, 0x08, 0x06

UINPUT_MAX_NAME = 80
BUS_VIRTUAL = 0x06
UINPUT_VERSION = 5

# struct input_id { __u16 bustype, vendor, product, version; }
class input_id(ctypes.Structure):
    _fields_ = [
        ("bustype", ctypes.c_ushort),
        ("vendor", ctypes.c_ushort),
        ("product", ctypes.c_ushort),
        ("version", ctypes.c_ushort),
    ]


# struct uinput_setup (linux/uinput.h, modern UI_DEV_SETUP path):
#   struct input_id id; char name[80]; __u32 ff_effects_max;
class uinput_setup(ctypes.Structure):
    _fields_ = [
        ("id", input_id),
        ("name", ctypes.c_char * UINPUT_MAX_NAME),
        ("ff_effects_max", ctypes.c_uint32),
    ]


# UI_DEV_SETUP is _IOW('U', 3, struct uinput_setup) - the struct size is part
# of the request number, so it has to be computed after the class is defined.
UI_DEV_SETUP = _IOC(_IOC_WRITE, "U", 3, ctypes.sizeof(uinput_setup))


def _emit(fd, evtype, code, value):
    now = time.time()
    sec = int(now)
    usec = int((now - sec) * 1_000_000)
    data = struct.pack("llHHi", sec, usec, evtype, code, value)
    os.write(fd, data)


class SoftwareBackend:
    """Grab the mouse's keypad interface and re-emit remapped keys."""

    def __init__(self, event_node, log=None):
        self.event_node = event_node
        self.log = log or (lambda *a: None)
        self.src_fd = None
        self.uinput_fd = None
        self.grabbed = False
        self.mapping = {}
        self.held = set()      # virtual keys currently down (to release on exit)
        self.capture_cb = None
        self._dev = None

    # -- device discovery ---------------------------------------------------

    @staticmethod
    def find_keypad_node():
        """Locate the M908's keyboard interface event node.

        The mouse exposes 3 HID interfaces; the one carrying KEY events is
        the keypad the side buttons emit on. Selected by HID ID + presence
        of a kbd handler, so replugging into a different port is fine.
        """
        try:
            txt = open("/proc/bus/input/devices").read()
        except OSError:
            return None
        best = None
        for block in txt.split("\n\n"):
            if "04D9:FC4D" not in block.upper():
                continue
            handlers = name = ""
            for line in block.splitlines():
                if line.startswith("H: Handlers="):
                    handlers = line.split("=", 1)[1]
                elif line.startswith("N: Name="):
                    name = line.split('"')[1]
            is_kbd = "kbd" in handlers
            for tok in handlers.split():
                if not tok.startswith("event"):
                    continue
                if is_kbd and best is None:
                    best = (tok, name)
                elif is_kbd:
                    pass
        return best[0] if best else None

    # -- lifecycle ----------------------------------------------------------

    def open_source(self):
        path = f"/dev/input/{self.event_node}"
        self.src_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.src_fd, EVIOCGRAB, 1)
        self.grabbed = True
        self.log(f"grabbed {path}")
        return True

    def open_uinput(self):
        self.uinput_fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.uinput_fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.uinput_fd, UI_SET_EVBIT, EV_SYN)
        # REL axes make libinput classify this as a pointer as well, so a
        # button mapped to BTN_LEFT/RIGHT/etc. is delivered as a real click.
        # Nothing ever emits motion on them.
        fcntl.ioctl(self.uinput_fd, UI_SET_EVBIT, EV_REL)
        for code in (REL_X, REL_Y):
            try:
                fcntl.ioctl(self.uinput_fd, UI_SET_RELBIT, code)
            except OSError:
                pass
        for code in list(range(0, 256)) + list(range(0x110, 0x118)):
            try:
                fcntl.ioctl(self.uinput_fd, UI_SET_KEYBIT, code)
            except OSError:
                pass
        dev = uinput_setup()
        dev.id.bustype = BUS_VIRTUAL
        dev.id.vendor = 0x04D9
        dev.id.product = 0xFC4D
        dev.id.version = UINPUT_VERSION
        dev.name = b"Redragon M908 Remap"
        dev.ff_effects_max = 0
        self._dev = dev
        fcntl.ioctl(self.uinput_fd, UI_DEV_SETUP, dev)
        fcntl.ioctl(self.uinput_fd, UI_DEV_CREATE)
        self.log("uinput virtual keyboard created")
        return True

    def close(self):
        # release anything still held so the desktop doesn't see stuck keys
        if self.uinput_fd is not None:
            for code in list(self.held):
                try:
                    _emit(self.uinput_fd, EV_KEY, code, 0)
                except OSError:
                    pass
            self.held.clear()
            try:
                _emit(self.uinput_fd, EV_SYN, SYN_REPORT, 0)
            except OSError:
                pass
            try:
                fcntl.ioctl(self.uinput_fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.uinput_fd)
            self.uinput_fd = None

        if self.src_fd is not None:
            if self.grabbed:
                try:
                    fcntl.ioctl(self.src_fd, EVIOCGRAB, 0)
                except OSError:
                    pass
                self.grabbed = False
            os.close(self.src_fd)
            self.src_fd = None
        self.log("released grab and virtual device")

    # -- mapping ------------------------------------------------------------

    def set_mapping(self, buttons):
        """buttons: {"side_1": {"type": "key", "value": 7}, ...}"""
        # invert: physical source code -> action
        self.mapping = {}
        for bid, action in (buttons or {}).items():
            if not isinstance(action, dict):
                continue
            src = self._source_code(bid)
            if src is None:
                continue
            atype = action.get("type")
            if atype in ("key", "mouse"):
                code = action.get("value")
                if code is not None:
                    self.mapping[src] = ("key", int(code), None)
            elif atype == "combo":
                codes = [int(c) for c in (action.get("value") or []) if c]
                if codes:
                    self.mapping[src] = ("combo", codes, None)
                else:
                    self.mapping[src] = ("none", None, None)
            elif atype == "disabled":
                self.mapping[src] = ("none", None, None)

    @staticmethod
    def _source_code(btn_id):
        from buttonmap import default_profile_buttons
        btn = default_profile_buttons().get(btn_id)
        if not isinstance(btn, dict):
            return None
        code = btn.get("value")
        return int(code) if code is not None else None

    # -- event pump ---------------------------------------------------------

    def pump(self, timeout=0.2):
        if self.src_fd is None:
            time.sleep(timeout)
            return
        try:
            ready, _, _ = select.select([self.src_fd], [], [], timeout)
        except (OSError, ValueError):
            return
        if not ready:
            return
        try:
            data = os.read(self.src_fd, EV_SIZE * 64)
        except (BlockingIOError, OSError):
            return

        for i in range(0, len(data) - EV_SIZE + 1, EV_SIZE):
            _t, _ts, evtype, code, value = struct.unpack_from("llHHi", data, i)
            if evtype != EV_KEY:
                continue
            if value == 2:
                continue  # ignore autorepeat
            down = value == 1

            if self.capture_cb and down and self.capture_cb(code):
                continue

            action = self.mapping.get(code)
            if action is None:
                # not one of our buttons - pass it straight through
                self._emit(EV_KEY, code, value)
                continue

            kind, target, _extra = action
            if kind == "none":
                continue
            if kind == "combo":
                if value == 1:
                    for code_ in target:
                        self._emit(EV_KEY, code_, 1)
                        self.held.add(code_)
                else:
                    for code_ in reversed(target):
                        self._emit(EV_KEY, code_, 0)
                        self.held.discard(code_)
                continue
            if kind == "key":
                self._emit(EV_KEY, target, value)
                if value == 1:
                    self.held.add(target)
                else:
                    self.held.discard(target)

    def _emit(self, evtype, code, value):
        if self.uinput_fd is None:
            return
        try:
            _emit(self.uinput_fd, evtype, code, value)
            _emit(self.uinput_fd, EV_SYN, SYN_REPORT, 0)
        except OSError:
            pass
