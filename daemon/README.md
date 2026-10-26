# m908d — the backend behind the Redragon M908 plugin

Version **1.0.0** (see [VERSION](VERSION)).

The daemon source ships **in this repository**, under `daemon/`, so the code that
runs on a user machine is byte-for-byte the code in the reviewed commit. There is
no external download, no second repository, no pip package, and no network fetch
at install time.

| File | Role | Lines |
| --- | --- | --- |
| `m908d` | entry point, systemd user unit, JSON control socket | 406 |
| `backend.py` | EVIOCGRAB of the keypad node plus uinput virtual keyboard | 325 |
| `buttonmap.py` | static table of the 13 button keycodes and key names | 115 |
| `profiles.py` | profile store under `~/.config/m908`, atomic JSON writes | 186 |

Python 3 standard library only. No third-party dependency, so there is nothing to
pin beyond these four files.

## Trust boundaries

### Privileges

* Runs as the **invoking user** through a systemd *user* unit
  (`systemd/m908d.service`). No root, no setuid bit, no polkit action, no
  capabilities, and no sudo anywhere in the code path.
* The unit is `PartOf=graphical-session.target`, so it lives and dies with the
  user session.

### Device access — exactly two nodes

1. **Read** the keypad interface of the mouse. The node is located by walking
   `/proc/bus/input/devices` for HID id `04D9:FC4D` and taking the entry whose
   handler list contains `kbd`. The daemon opens it `O_RDONLY`, takes
   `EVIOCGRAB` (an exclusive *read* grab, never a device write), and releases
   both on shutdown or crash. The grab is what stops raw button presses from
   reaching the compositor twice.
2. **Write** `/dev/uinput` to create one virtual keyboard named
   `Redragon M908 Remap`. It registers `EV_KEY` for keycodes 0-255 and the
   `BTN_*` mouse-button range, plus the `EV_REL`/`REL_X`/`REL_Y` bits that make
   libinput classify the device as a pointer. No motion is ever emitted: those
   bits exist only so a button mapped to `BTN_LEFT` arrives as a real click.

**The daemon never opens the hidraw or vendor interface of the mouse**, so it
cannot write to, reflash or reconfigure the hardware. `daemon/udev/99-m908.rules`
matches that: it grants the logged-in user access to `/dev/uinput` and to the
M908 input node through `uaccess`, and grants **no** hidraw access at all.

### Control socket

* Path `$XDG_RUNTIME_DIR/m908.sock` — a per-user runtime directory that is
  already 0700, so other users cannot reach the path.
* `AF_UNIX`, `SOCK_STREAM`, and the daemon sets the socket mode to **0600** after
  bind, so only the owning user (and root) can connect.
* Protocol: one JSON object per line in, one JSON object per line back. There is
  no auth token and none is needed: filesystem permissions are the boundary.
  Anything able to connect already runs as the same user and could edit the
  profile JSON directly.
* Operations: `status`, `profiles.list`, `profile.load`, `profile.new`,
  `profile.save`, `profile.rename`, `profile.delete`, `button.set`,
  `button.reset`, `button.capture`, `button.capture.poll`,
  `button.capture.cancel`, `capture`, `capture.poll`, `revert`, `debug.emit`.
  Every handler is a fixed `if op == …` branch. The socket cannot name a
  function, a path, a command or a shell.
* A 120 s per-connection timeout and an 8-deep accept backlog bound the cost of a
  stuck client.

### What it never does

* No network syscalls of any kind — no `AF_INET`, no DNS, no HTTP.
* No shell, no `subprocess`, no `os.system`. The profile schema cannot express a
  command: `profiles.validate()` accepts only `key`, `combo`, `mouse` and
  `disabled` action types, and the backend implements only those four.
* No input monitoring beyond the keypad node it grabbed. It does not read other
  keyboards, the pointer, or any other device.
* No telemetry, no update check, and no writes outside `~/.config/m908`.

### Data written

`~/.config/m908/profiles/<slug>.json` and `~/.config/m908/state.json`, written
with `tempfile.mkstemp` + `os.replace` + `fsync` so a crash cannot leave a half
written profile and a pre-created symlink cannot redirect the write. Unknown
fields already on disk are preserved on save.

## Install

There is deliberately no `curl | bash` one-liner and no install script. The
steps, in order:

1. Put the four Python files where the unit expects them: `m908d`, `backend.py`,
   `buttonmap.py` and `profiles.py` go into `~/.local/share/m908/`, with `m908d`
   kept executable. `m908d` imports its siblings from its own directory, so the
   four must stay together.
2. Place `systemd/m908d.service` in `~/.config/systemd/user/`, then enable and
   start the `m908d` user unit with the usual systemd user tooling. The plugin
   panel also has a restart button for it.
3. One-time, needs root, done by you rather than by a script: put
   `udev/99-m908.rules` in the system udev rules directory and reload the udev
   rules so `/dev/uinput` and the M908 input node are usable by your user.
   Replug the mouse afterwards. Without this step the daemon logs
   `no M908 keypad node found` or fails to open `/dev/uinput`, and exits cleanly
   without grabbing anything.

Nothing is installed system-wide. Uninstalling is deleting
`~/.local/share/m908`, the unit file, and (if you added it) the udev rule.
Profiles are left alone.

## Verifying a checkout

```bash
python3 daemon/tests/test_profiles.py          # profile store + key table
sha256sum daemon/m908d daemon/backend.py daemon/buttonmap.py daemon/profiles.py
```

The live daemon reports its build version in every `status` reply:

```json
{"op": "status"}  ->  {"ok": true, "version": "1.0.0", ...}
```

## Hardware facts this relies on

See [docs/discovery.md](docs/discovery.md): the 13 remappable buttons are exposed
by the mouse as **ordinary key events** on the keyboard HID interface, so
remapping is pure input-layer work — no vendor protocol, no firmware write, no
reverse-engineered hidraw frames. That is the whole reason this backend needs no
privileged hardware access.
