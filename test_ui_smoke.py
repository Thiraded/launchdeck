"""Build the real Dashboard (Tk, withdrawn) against a FAKE manifest.

No process scan, no launch, no manifest/registry writes: every core
entry point that could touch the machine or works.json is mocked.
Safe on a live machine (see Docs/verification.md).
"""
import copy
import unittest
from unittest import mock

import launchdeck_core as core
from deck.core import jobs as _jobs
# Never open/kill a real deck job from a test (isolated namespace).
_jobs.PREFIX = "Local\\launchdeck-test-%d-" % __import__("os").getpid()
from deck.ui import app, icons, state

FAKE = {
    "version": 1,
    "groups": [{"id": "g-demo", "label": "Demo", "members": ["web", "api"]}],
    "works": [
        {"id": "web", "label": "Web dev", "bat": "web.bat", "icon": "🌐",
         "run": "detached", "steps": [{"cmd": "npm run dev"}]},
        {"id": "api", "label": "API", "bat": "api.bat", "run": "detached"},
        {"id": "solo", "label": "Solo tool", "bat": "solo.bat",
         "icon": "terminal", "run": "detached"},
    ],
}


def _tree(w):
    out, i = [w], 0
    while i < len(out):
        out.extend(out[i].winfo_children())
        i += 1
    return out


class DashboardSmoke(unittest.TestCase):
    def setUp(self):
        man = copy.deepcopy(FAKE)
        patches = [
            mock.patch.object(core, "load_manifest", side_effect=lambda *a, **k: copy.deepcopy(man)),
            mock.patch.object(core, "save_manifest"),
            mock.patch.object(core, "scan_commandlines", return_value=[]),
            mock.patch.object(core, "scan_table", return_value=[]),
            mock.patch.object(core, "scan_available", return_value=False),
            mock.patch.object(core, "launch_work", side_effect=AssertionError("launch")),
            mock.patch.object(core, "kill_work", side_effect=AssertionError("kill")),
            mock.patch.object(state, "_running", {"web"}),
            mock.patch.object(state, "tray_host", None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.d = app.Dashboard()
        self.d.ensure()
        self.d.root.withdraw()
        self.addCleanup(self._teardown)

    def _teardown(self):
        try:
            self.d.root.destroy()
        except Exception:
            pass
        icons.clear_cache()

    def test_builds_rows_and_dialogs(self):
        d = self.d
        d.refresh()
        d.root.update_idletasks()
        self.assertEqual(set(d._rows), {"web", "api", "solo"})
        # in-place update path (same struct) must not raise or rebuild
        before = {k: v["frame"] for k, v in d._rows.items()}
        d.refresh()
        self.assertEqual(before, {k: v["frame"] for k, v in d._rows.items()})
        for opener in (lambda: d.open_editor(FAKE["works"][0]),
                       lambda: d.open_editor(None),
                       lambda: d.open_group_editor(None),
                       lambda: d.open_group_editor(FAKE["groups"][0]),
                       d.open_settings):
            win = opener()
            d.root.update_idletasks()
            if win is not None:
                self.assertTrue(win.winfo_exists())
                d._close_popup(win)

    def test_row_start_and_start_all_dispatch(self):
        """Per-row Start regressed once (a local named `state` shadowed the
        module -> UnboundLocalError on click). Drive both paths."""
        d = self.d
        d.refresh()
        with mock.patch.object(state, "toggle_start_stop",
                               return_value="started 'API'") as tss, \
                mock.patch("threading.Thread") as th:
            d._act_run(FAKE["works"][1])
            self.assertEqual(d._pending["api"]["state"], "starting")
            target = th.call_args.kwargs["target"]
            target(*th.call_args.kwargs["args"])
            tss.assert_called_once()
            d._pending.clear()
            d._act_all([FAKE["works"][1]], True)
            self.assertEqual(d._pending["api"]["state"], "starting")

    def test_no_local_shadows_a_module(self):
        import ast
        import symtable
        from pathlib import Path
        bad = []
        for p in Path("deck/ui").glob("*.py"):
            src = p.read_text(encoding="utf-8")
            mods = {"core"} | {a.asname or a.name for n in ast.walk(ast.parse(src))
                               if isinstance(n, ast.ImportFrom) and n.module == "deck.ui"
                               for a in n.names}

            def walk(t):
                if t.get_type() == "function":
                    bad.extend(f"{p.name}:{t.get_name()}:{s.get_name()}"
                               for s in t.get_symbols()
                               if s.get_name() in mods and (s.is_local() or s.is_parameter()))
                for c in t.get_children():
                    walk(c)
            walk(symtable.symtable(src, str(p), "exec"))
        self.assertEqual(bad, [])

    def test_log_viewer_opens(self):
        d = self.d
        with mock.patch.object(core, "work_log_path") as lp, \
                mock.patch.object(core, "work_display_log_path") as dp:
            lp.return_value = dp.return_value = core.HERE / "does-not-exist.log"
            d.open_log_viewer(FAKE["works"][0])
            d.root.update_idletasks()


class IconRenderer(unittest.TestCase):
    def test_every_asset_renders_with_ink(self):
        for name in icons.names():
            m = icons.mask(name, 20)
            self.assertEqual(len(m), 400, name)
            self.assertGreater(sum(m), 5, f"{name} rendered empty")
            self.assertTrue(all(0.0 <= a <= 1.0 for a in m), name)

    def test_png_is_valid_rgba(self):
        png = icons.compose("play", 16, "#FFFFFF", box=24, plate="#3E7BFA")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png[12:16], b"IHDR")
        self.assertEqual(int.from_bytes(png[16:20], "big"), 24)

    def test_glued_arc_flags_parse(self):
        # 'a.5.5 0 011 1' style: flags glued to the next number
        subs = icons._path_points("M0 0a1 1 0 011 1")
        self.assertAlmostEqual(subs[0][0][-1][0], 1.0)
        self.assertAlmostEqual(subs[0][0][-1][1], 1.0)

    def test_legacy_glyphs_and_emoji_map_to_icons(self):
        from deck.ui import widgets
        self.assertEqual(widgets.icon_name("🗑"), "trash-2")
        self.assertEqual(widgets.icon_name("\U0001f3ae"), "gamepad-2")
        self.assertEqual(widgets.icon_name("server"), "server")
        self.assertIsNone(widgets.icon_name("🦄"))  # text fallback


if __name__ == "__main__":
    unittest.main()
