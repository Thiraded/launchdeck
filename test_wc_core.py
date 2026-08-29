"""Head-less integration test for wc_core: build model, run fake workers,
detect via CommandLine match, kill, verify state machine. No real hamster needed."""
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


def main():
    model = core.build_model(make_fake_manifest())
    assert model[0].kind == "group"
    assert len(core.member_nodes(model, model[0])) == 3

    for n in model:
        assert not n.is_running(), f"{n.key} should not be running yet"
    print("[ok] nothing running initially")

    fa = os.path.join(HERE, "flag_a.tmp")
    fb = os.path.join(HERE, "flag_b.tmp")
    spawn_fake_worker("wc-core-test-A", fa)
    spawn_fake_worker("wc-core-test-B", fb)
    time.sleep(3.0)

    states = {n.key: (core.RUN if n.is_running() else core.OFF) for n in model}
    core.recompute_states(model, states)
    assert states["grp"] == core.RUN, f"group should be RUN, got {states['grp']}"
    assert states["a"] == core.RUN and states["b"] == core.RUN and states["c"] == core.OFF
    print("[ok] detection: group RUN when a member runs; C OFF")

    # kill via group
    acts = core.enter_action(core.RUN, model[0], model)
    assert all(a[0] == "kill" for a in acts), acts
    for action, work in acts:
        core.kill_work(work)
    time.sleep(2.0)
    states2 = {n.key: (core.RUN if n.is_running() else core.OFF) for n in model}
    core.recompute_states(model, states2)
    assert states2["grp"] == core.OFF, f"group should be OFF after kill, got {states2['grp']}"
    assert states2["a"] == core.OFF and states2["b"] == core.OFF
    print("[ok] kill via group -> all OFF")

    # Space OFF->ON then Enter->run members (spawn real fake workers again)
    s = {n.key: core.OFF for n in model}
    s["grp"] = core.next_on_space(s["grp"])
    assert s["grp"] == core.ON
    acts = core.enter_action(core.ON, model[0], model)
    assert all(a[0] == "run" for a in acts), acts
    for action, work in acts:
        core.run_work(work)  # would start a.bat etc (not present -> no-op safe)
    print("[ok] Space OFF->ON, Enter->run members")

    # LEFT_ALONE does nothing on Enter
    s3 = {n.key: core.LEFT_ALONE for n in model[:1]}
    acts = core.enter_action(core.LEFT_ALONE, model[0], model)
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
