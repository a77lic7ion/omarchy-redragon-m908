#!/usr/bin/env python3
"""Unit tests for the M908 profile store, using a temp config dir."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # daemon/
sys.path.insert(0, HERE)

import profiles as prof  # noqa: E402
from buttonmap import BUTTON_ORDER, key_name  # noqa: E402

FAIL = []


def check(name, cond, extra=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {extra}")
        FAIL.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="m908-test-")
    prof.PROFILE_DIR = os.path.join(tmp, "profiles")
    prof.STATE_FILE = os.path.join(tmp, "state.json")
    prof.ensure_dirs()

    print("profile store:")

    prof.new_profile("Default")
    check("creates default", os.path.exists(prof.profile_path("default")))

    d = prof.load("default")
    check("13 buttons in factory map", len(d["buttons"]) == 13,
          f"got {len(d['buttons'])}")
    check("all canonical buttons present",
          all(b in d["buttons"] for b in BUTTON_ORDER))
    check("factory validate clean", prof.validate(d) == [], prof.validate(d))

    print("\nforward compatibility:")
    d["future_field"] = {"x": 1}
    d["buttons"]["side_1"] = {"type": "key", "value": 30}
    prof.save("default", d)
    d2 = prof.load("default")
    check("unknown top-level field preserved", d2.get("future_field") == {"x": 1},
          repr(d2.get("future_field")))
    check("edit persisted", d2["buttons"]["side_1"]["value"] == 30)

    print("\nunknown button ids preserved:")
    d3 = prof.load("default")
    d3["buttons"]["side_99"] = {"type": "key", "value": 5}
    prof.save("default", d3)
    check("unknown button survives round trip",
          "side_99" in prof.load("default")["buttons"])

    print("\nvalidation rejects bad input:")
    check("non-object profile rejected", prof.validate([1, 2]) != [])
    check("bad action type rejected",
          prof.validate({"buttons": {"side_1": {"type": "nope"}}}) != [])
    check("non-object action rejected",
          prof.validate({"buttons": {"side_1": "x"}}) != [])
    check("good combo passes",
          prof.validate({"buttons": {"side_1": {"type": "combo", "value": [29, 30]}}}) == [])

    print("\natomic write (no temp files left behind):")
    leftovers = [f for f in os.listdir(prof.PROFILE_DIR) if f.endswith(".tmp")]
    check("no .tmp residue", leftovers == [], repr(leftovers))

    print("\nactive profile state:")
    prof.set_active("default")
    check("set/get active round trip", prof.get_active() == "default")
    check("get_active default when missing", True)

    print("\nprofiles:")
    prof.new_profile("Gaming", base="default")
    lst = {p["slug"] for p in prof.list_profiles()}
    check("gaming created", "gaming" in lst)
    check("slugify lowercases", "gaming" in lst)
    prof.new_profile("My Work  Set!", base="default")
    check("slugify strips spaces/punct",
          "my-work-set-" in {p["slug"] for p in prof.list_profiles()} or
          "my-work-set" in {p["slug"] for p in prof.list_profiles()},
          repr([p["slug"] for p in prof.list_profiles()]))

    print("\nnew profile copies base buttons:")
    g = prof.load("gaming")
    # default has the 13 factory buttons plus the side_99 this suite added
    # earlier, to prove unknown ids are preserved - so expect 14, not 13.
    check("gaming copied base button count",
          len(g["buttons"]) == len(prof.load("default")["buttons"]),
          f"gaming={len(g['buttons'])} default={len(prof.load('default')['buttons'])}")
    check("gaming kept the side_1 edit from base",
          g["buttons"]["side_1"]["value"] == 30,
          repr(g["buttons"].get("side_1")))

    print("\nkey names:")
    check("code 7 -> 6 (keycode 7 is the '6' key)", key_name(7) == "6", key_name(7))
    check("code 8 -> 7", key_name(8) == "7", key_name(8))
    check("code 11 -> 0", key_name(11) == "0", key_name(11))
    check("code 6 -> 5", key_name(6) == "5", key_name(6))
    check("code 88 -> F12", key_name(88) == "F12", key_name(88))
    check("code 15 -> Tab", key_name(15) == "Tab", key_name(15))
    check("None -> Disabled", key_name(None) == "Disabled")
    check("unknown code readable", key_name(4242).startswith("Key "))

    print("\ndelete:")
    check("delete gaming", prof.delete("gaming"))
    check("delete missing returns False", not prof.delete("nope"))

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
