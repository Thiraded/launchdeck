"""Head-less integration test for wc_core.

Covers the real API as it is wired today:
  * build_model() excludes group members from the top-level model (they live
    under their group), so we expand members via member_nodes() to test them.
  * A group has NO state of its own: purely the OR of its children's SELECTION.
  * Running state `[-]` is detected live from the process CommandLine.
  * enter_action() runs/kills members; LEFT_ALONE does nothing.

No real hamster needed — we spawn fake `cmd /k` workers whose CommandLine
carries a unique token, then kill them via core.kill_work().
"""
import os
import subprocess
import time

import wc_core as core

HERE = os.path.dirname(os.path.abspath(__file__))


def spawn_fake_worker(token: str, flag_path: str) -> None:
    """cmd /k whose CommandLine contains `token`, writes flag, idles ~10min."""
    inner = f'title {token} && echo RUN > "{flag_path}" && ping -n 600 127.0.0.1 >nul'
    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", "cmd", "/k", inner],
        creationflags=0x08000000,
    )


def make_fake_manifest():
    return {
        "version": 1,
        "groups": [
            {"id": "grp", "label": "Hamster combo", "members": ["a", "b", "c"]}
        ],
        "works": [
            {"id": "a", "label": "A start", "match": "wc-core-test-A", "bat": "a.bat", "detect": True},
            {"id": "b", "label": "B start", "match": "wc-core-test-B", "bat": "b.bat", "detect": True},
            {"id": "c", "label": "C start", "match": "wc-core-test-C", "bat": "c.bat", "detect": True},
        ],
    }


def expand(model):
    """All nodes that carry state: top-level model nodes + every group member."""
    out = list(model)
    for n in model:
        if n.kind == "group":
            out.extend(core.member_nodes(model, n))
    return out


def main():
    manifest = make_fake_manifest()
    model = core.build_model(manifest)
    assert model[0].kind == "group"
    members = core.member_nodes(model, model[0])
    assert len(members) == 3, f"expected 3 members, got {len(members)}"
    print("[ok] build_model: group present, 3 members expanded")

    # nothing running yet
    for m in members:
        assert not m.is_running(), f"{m.key} should not be running yet"
    print("[ok] nothing running initially")

    fa = os.path.join(HERE, "flag_a.tmp")
    fb = os.path.join(HERE, "flag_b.tmp")
    spawn_fake_worker("wc-core-test-A", fa)
    spawn_fake_worker("wc-core-test-B", fb)
    time.sleep(3.0)

    states = {n.key: (core.RUN if n.is_running() else core.OFF) for n in expand(model)}
    core.recompute_states(model, states)
    # group has no running state of its own; it is the OR of children's SELECTION
    assert states["grp"] == core.OFF, f"group must stay OFF, got {states['grp']}"
    assert states["a"] == core.RUN and states["b"] == core.RUN and states["c"] == core.OFF
    print("[ok] detection: members A,B RUN, C OFF; group stays OFF")

    # kill via group (Enter on a group that is RUN -> kill running members)
    acts = core.enter_action(core.RUN, model[0], model, states)
    assert all(a[0] == "kill" for a in acts), acts
    assert {a[1]["id"] for a in acts} == {"a", "b"}, acts
    for action, work in acts:
        core.kill_work(work)
    time.sleep(2.0)
    states2 = {n.key: (core.RUN if n.is_running() else core.OFF) for n in expand(model)}
    core.recompute_states(model, states2)
    assert states2["a"] == core.OFF and states2["b"] == core.OFF and states2["c"] == core.OFF
    print("[ok] kill via group -> all members OFF")

    # Space OFF->ON then Enter->run members
    s = {n.key: core.OFF for n in expand(model)}
    s["grp"] = core.next_on_space(s["grp"])
    assert s["grp"] == core.ON, "group should be ON after Space"
    acts = core.enter_action(core.ON, model[0], model, s)
    assert all(a[0] == "run" for a in acts), acts
    assert {a[1]["id"] for a in acts} == {"a", "b", "c"}, acts
    for action, work in acts:
        core.run_work(work)  # would start a.bat etc (not present -> no-op safe)
    print("[ok] Space OFF->ON, Enter->run members (a,b,c)")

    # LEFT_ALONE does nothing on Enter
    acts = core.enter_action(core.LEFT_ALONE, model[0], model, {model[0].key: core.LEFT_ALONE})
    assert acts == [], "LEFT_ALONE must do nothing"
    print("[ok] LEFT_ALONE does nothing on Enter")

    for f in (fa, fb):
        try:
            os.remove(f)
        except Exception:
            pass
    print("ALL TESTS PASS")


if __name__ == "__main__":
    main()
