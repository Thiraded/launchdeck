"""--self-test: builds a real Dashboard against the live manifest."""
from pathlib import Path
import time
import tkinter as tk

import launchdeck_core as core
from deck.ui import state
from deck.ui import theme
from deck.ui.app import Dashboard
from deck.ui.viewmodel import _row_view, _swap_adjacent, _unique_id, _work_to_form
from deck.ui.widgets import th_circle_btn


def self_test():
    """Smoke without clicks: scan + build the dashboard off-screen."""
    manifest = core.load_manifest()
    cls = core.scan_commandlines()
    print(f"self-test: {len(manifest.get('works', []))} works, "
          f"{len(manifest.get('groups', []))} groups, scan {len(cls)} lines")
    d = Dashboard()
    d.ensure()
    d.refresh()
    d.root.update_idletasks()
    print(f"self-test: dashboard rows: {len(d.list_frame.winfo_children())}")
    cv = d.list_frame.master
    assert cv.cget("scrollregion") not in ("", "0 0 0 0"), cv.cget("scrollregion")
    assert d.root.bind("<MouseWheel>"), "wheel binding missing (backlog #4)"
    print(f"self-test: scrollregion {cv.cget('scrollregion')} + wheel OK")
    w = next(x for x in manifest["works"] if x.get("id") == "hamster-clint")
    ed = d.open_editor(w)
    d.root.update_idletasks()
    assert ed is not None and ed.winfo_exists(), "editor did not build"
    d._close_popup(ed)
    print("self-test: editor (steps prefill) OK")
    ed0 = d.open_editor(None)
    d.root.update_idletasks()
    assert ed0 is not None and ed0.winfo_exists(), "new-task editor (fork) did not build"
    d._close_popup(ed0)
    man0 = core.load_manifest()
    f = _work_to_form(man0["works"][0], man0)
    assert f["label"].endswith(" copy")
    assert f["match"] == str(man0["works"][0].get("match", "") or "")
    assert f["steps"] == core.steps_to_text(man0["works"][0].get("steps") or [])
    print("self-test: fork prefill OK")
    _found2, _i2 = [d.list_frame], 0
    while _i2 < len(_found2):
        _found2.extend(_found2[_i2].winfo_children())
        _i2 += 1
    _hide_btns = [x for x in _found2
                  if isinstance(x, tk.Button) and x.cget("text") in ("Hide", "Show")]
    assert not _hide_btns, "no Hide/Show buttons anywhere (detached-only)"
    man = core.load_manifest()
    assert core.slug_group_id("Hamster combo", man) != "hamstercombo"
    assert core.slug_group_id("New Group", man) == "g-new-group"
    ged = d.open_group_editor(None)
    d.root.update_idletasks()
    assert ged is not None and ged.winfo_exists(), "group editor did not build"
    _found, _i = [ged], 0
    while _i < len(_found):
        _found.extend(_found[_i].winfo_children())
        _i += 1
    assert any(isinstance(_x, tk.Listbox) for _x in _found), "group editor needs the order list"
    d._close_popup(ged)
    print("self-test: group editor + slug OK")
    assert d.root.bind("<FocusOut>"), "popup dismiss binding missing (backlog #5)"
    d._maybe_autodismiss()  # hidden popup: must no-op, never raise
    assert d.visible is False
    print("self-test: popup dismiss wiring OK")
    assert core.parse_hotkey("ctrl+alt+1") == (0x3, 0x31)
    assert core.parse_hotkey("1") is None
    assert core.parse_hotkey("ctrl+f24") == (0x2, 0x87)
    assert core.canonical_hotkey("Ctrl + Alt + 1") == "ctrl+alt+1"
    assert core.hotkey_conflicts(
        {"works": [{"id": "a", "hotkey": "ctrl+alt+1"},
                   {"id": "b", "hotkey": "ctrl+alt+1"}]}) == {"ctrl+alt+1": ["a", "b"]}
    from launchdeck_tray import register_hotkey as _rh, unregister_hotkey as _uh
    hwnd = d.root.winfo_id()
    # A tk window has no wc handler: DefWindowProc's 0 must read as a
    # clean False (never a false-positive success).
    assert _rh(hwnd, 65001, 0x3, 0x87) is False
    assert _uh(hwnd, 65001) is False
    print("self-test: hotkey parse + marshal contract OK")
    assert d.root.overrideredirect(), "dashboard must be borderless"
    lv = d.open_log_viewer(w)
    d.root.update_idletasks()
    assert lv is not None and lv in d._popups
    st = d.open_settings()
    d.root.update_idletasks()
    assert st is not None and st in d._popups
    assert len(d._popups) == 2
    d._close_popups()
    assert d._popups == [] and not lv.winfo_exists() and not st.winfo_exists()
    d._ensure_hotkey()
    assert not getattr(d, "_hotkey_on", False)
    print("self-test: borderless + popup class + settings + hotkey ensure OK")
    assert theme._apply_palette("light") == "light"
    assert theme.TH_BG == theme.PALETTES["light"]["BG"]
    theme._apply_palette("dark")
    assert theme.TH_BG == theme.PALETTES["dark"]["BG"]
    print("self-test: theme palettes roundtrip OK")
    sh, _sbody = d._popup_shell("test shell")
    d.root.update_idletasks()
    assert sh.overrideredirect() and sh.winfo_exists(), "popup shell must be borderless"
    d._close_popup(sh)
    assert not sh.winfo_exists()
    print("self-test: borderless popup shell + close OK")
    cb = th_circle_btn(d.root, "▶", lambda: None, style="accent")
    assert len(cb.find_all()) == 2, "circle button must be oval+glyph"
    assert cb.cget("cursor") == "hand2"
    assert hasattr(cb, "recolor")
    cb.destroy()
    print("self-test: circle button OK")
    w = next(x for x in manifest["works"] if x.get("id") == "hamster-clint")
    lv = d.open_log_viewer(w)
    assert lv is not None and d._log_wins.get("hamster-clint") is lv
    assert d.open_log_viewer(w) is None  # toggle: second click closes
    assert "hamster-clint" not in d._log_wins and not lv.winfo_exists()
    print("self-test: log toggle (open/close, no duplicates) OK")
    d._pending["x-test"] = {"state": "starting", "expect": True,
                            "until": time.monotonic() + 20}
    d._act_run({"id": "x-test", "label": "X-Test"})
    assert d._pending.get("x-test", {}).get("state") == "starting", "guard must not clear pending"
    assert "already starting" in d.status_var.get()
    d._pending.pop("x-test", None)
    print("self-test: pending double-click guard OK")
    v = _row_view({"id": "a", "label": "A"}, set(), {})
    assert (v["sub"], v["icon_c"], v["running"]) == ("stopped", theme.TH_DIM, False)
    v = _row_view({"id": "a", "label": "A"}, {"a"}, {})
    assert (v["sub"], v["icon_c"], v["running"]) == ("running", theme.TH_GREEN, True)
    v = _row_view({"id": "a", "label": "A"}, set(),
                  {"a": {"state": "starting", "expect": True, "until": 0}})
    assert (v["sub"], v["sub_c"]) == ("starting…", theme.TH_ACCENT)
    print("self-test: row view-model OK")
    d.refresh()
    f1 = {k: r["frame"] for k, r in d._rows.items()}
    d.refresh()
    f2 = {k: r["frame"] for k, r in d._rows.items()}
    assert f1 and f1 == f2, "same layout must update in place (no rebuild)"
    print("self-test: in-place refresh OK")
    assert _swap_adjacent(["a", "b", "c"], "b", -1) == ["b", "a", "c"]
    assert _swap_adjacent(["a", "b", "c"], "b", +1) == ["a", "c", "b"]
    assert _swap_adjacent(["a", "b", "c"], "a", -1) == ["a", "b", "c"]
    assert _swap_adjacent(["a", "b", "c"], "c", +1) == ["a", "b", "c"]
    assert _swap_adjacent(["a"], "a", +1) == ["a"]
    assert _unique_id("w-a-copy", ["w-a-copy"]) == "w-a-copy-2"
    assert _unique_id("w-a-copy", ["x"]) == "w-a-copy"
    raw2 = core.MANIFEST.read_text(encoding="utf-8")
    try:
        gid0 = core.load_manifest()["groups"][0]["id"]
        was = gid0 in state.collapsed_groups()
        kids0 = d._group_heads[gid0]["kids"]
        d._toggle_group(gid0)
        assert (gid0 in state.collapsed_groups()) != was
        assert kids0.winfo_manager() == ("pack" if was else "")
        d._toggle_group(gid0)
        assert (gid0 in state.collapsed_groups()) == was
    finally:
        core.MANIFEST.write_text(raw2, encoding="utf-8")
        col = state.collapsed_groups()
        for _gid, _gr in d._group_heads.items():
            try:
                if _gid in col:
                    _gr["kids"].pack_forget()
                else:
                    _gr["kids"].pack(fill="x")
                _gr["tog"].itemconfig(_gr["tog"]._txt,
                                      text="▸" if _gid in col else "▾")
            except Exception:
                pass
        d.refresh()
    print("self-test: group accordion OK")
    raw = core.MANIFEST.read_text(encoding="utf-8")
    try:
        w0 = core.load_manifest()["works"][0]
        n0 = len(core.load_manifest()["works"])
        d._duplicate_work(w0)
        man1 = core.load_manifest()
        assert len(man1["works"]) == n0 + 1
        ids1 = [x["id"] for x in man1["works"]]
        at = ids1.index(w0["id"])
        got = man1["works"][at + 1]
        assert got["label"].endswith(" copy") and got["id"] != w0["id"]
        assert {k: v for k, v in got.items() if k not in ("id", "label")} == \
               {k: v for k, v in w0.items() if k not in ("id", "label")}
    finally:
        core.MANIFEST.write_text(raw, encoding="utf-8")
        d.refresh()
    print("self-test: duplicate (+byte-exact restore) OK")
    src = "".join(p.read_text(encoding="utf-8")
                  for p in Path(__file__).parent.glob("*.py"))
    assert 'man["works"]' + '.sort' not in src, \
        "editor save must not re-sort (custom order)"
    print("self-test: custom-order swap + no-autosort OK")
    d.root.destroy()
    print("SELF-TEST OK")
    return 0
