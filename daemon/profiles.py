"""
profiles.py — profile store for the M908 manager.

Profiles are JSON files in ~/.config/m908/profiles/<slug>.json.
The active profile name lives in ~/.config/m908/state.json.

Design rules from the build spec:
  - atomic writes (temp file + rename)
  - unknown fields preserved on load/save (forward compatibility)
  - writes never touch the device
"""

import json
import os
import re
import tempfile

from buttonmap import BUTTON_ORDER, default_profile_buttons

CONFIG_DIR = os.path.expanduser("~/.config/m908")
PROFILE_DIR = os.path.join(CONFIG_DIR, "profiles")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

SCHEMA = 1

SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def slugify(name):
    slug = SLUG_RE.sub("-", str(name).strip().lower()).strip("-.")
    return slug or "profile"


def ensure_dirs():
    os.makedirs(PROFILE_DIR, exist_ok=True)


def profile_path(slug):
    return os.path.join(PROFILE_DIR, f"{slug}.json")


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_buttons(slug):
    """Read just the button map from a profile, tolerating a bad file.

    Used when creating a profile from a base: a corrupt base must not stop the
    new profile being created.
    """
    try:
        src = load(slug)
    except (FileNotFoundError, ValueError, OSError):
        return None
    buttons = src.get("buttons")
    return buttons if isinstance(buttons, dict) and buttons else None


def new_profile(name, base=None):
    """Create a profile. If base is given, copy its button map."""
    ensure_dirs()
    slug = slugify(name)
    path = profile_path(slug)
    if os.path.exists(path):
        raise FileExistsError(f"profile already exists: {slug}")

    buttons = default_profile_buttons()
    if base:
        src_buttons = _read_buttons(base)
        if src_buttons:
            buttons = dict(src_buttons)

    data = {
        "schema": SCHEMA,
        "name": name,
        "buttons": buttons,
        "dpi": None,
        "polling_hz": None,
        "lift_off": None,
        "rgb": None,
        "macros": {},
        "match": {"window_class": None},
    }
    _atomic_write_json(path, data)
    return slug


def load(slug):
    path = profile_path(slug)
    if not os.path.exists(path):
        raise FileNotFoundError(slug)
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"malformed profile: {slug}")
    data.setdefault("schema", SCHEMA)
    data.setdefault("buttons", {})
    return data


def save(slug, data):
    """Save, preserving any unknown top-level fields already on disk."""
    ensure_dirs()
    path = profile_path(slug)
    merged = dict(data)
    if os.path.exists(path):
        try:
            old = load(slug)
            for k, v in old.items():
                merged.setdefault(k, v)  # forward compatibility
        except (ValueError, OSError):
            pass
    merged["schema"] = SCHEMA
    _atomic_write_json(path, merged)
    return merged


def list_profiles():
    ensure_dirs()
    out = []
    for fn in sorted(os.listdir(PROFILE_DIR)):
        if fn.endswith(".json"):
            slug = fn[:-5]
            try:
                data = load(slug)
                out.append({"slug": slug, "name": data.get("name", slug)})
            except (ValueError, OSError):
                out.append({"slug": slug, "name": slug})
    return out


def delete(slug):
    path = profile_path(slug)
    if os.path.exists(path):
        os.unlink(path)
        return True
    return False


def get_active():
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh).get("active", "default")
    except (OSError, ValueError):
        return None


def set_active(slug):
    ensure_dirs()
    _atomic_write_json(STATE_FILE, {"active": slug})


def validate(data):
    """Basic structural validation. Returns list of problems."""
    problems = []
    if not isinstance(data, dict):
        return ["profile is not an object"]
    buttons = data.get("buttons")
    if buttons is not None and not isinstance(buttons, dict):
        problems.append("buttons must be an object")
        return problems
    for bid, action in (buttons or {}).items():
        if bid not in BUTTON_ORDER:
            continue  # unknown buttons preserved, not an error
        if not isinstance(action, dict):
            problems.append(f"{bid}: action must be an object")
            continue
        atype = action.get("type")
        # Only the action types the backend implements. Deliberately no
        # "command"/"macro": the daemon never executes anything, so a profile
        # must not be able to express a command.
        if atype not in ("key", "combo", "disabled", "mouse"):
            problems.append(f"{bid}: unknown action type {atype!r}")
    return problems
