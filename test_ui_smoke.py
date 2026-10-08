"""Build the real Dashboard (Tk, withdrawn) against a FAKE manifest.

No process scan, no launch, no manifest/registry writes: every core
entry point that could touch the machine or works.json is mocked.
Safe on a live machine (see Docs/verification.md).
"""
import copy
from types import SimpleNamespace
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
            mock.patch.object(state, "hotkey_host", None),
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
            if getattr(self.d, "_speed_dial", None) is not None:
                self.d._speed_dial.destroy()
        except Exception:
            pass
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
        # deck/core too: the core split hit it (`steps`/`manifest` locals).
        for p in [*Path("deck/ui").glob("*.py"), *Path("deck/core").glob("*.py")]:
            src = p.read_text(encoding="utf-8")
            mods = {"core"} | {a.asname or a.name for n in ast.walk(ast.parse(src))
                               if isinstance(n, ast.ImportFrom)
                               and n.module in ("deck.ui", "deck.core")
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

    def test_desktop_launcher_click_toggles_and_drag_moves_anchor(self):
        d = self.d
        launcher = d.launcher
        self.assertIsNotNone(launcher)
        self.assertFalse(launcher.visible)
        self.assertTrue(launcher.window.overrideredirect())
        self.assertTrue(launcher.window.attributes("-topmost"))
        toggle, moved = mock.Mock(), mock.Mock()
        launcher.on_toggle, launcher.on_move = toggle, moved
        press = SimpleNamespace(x_root=200, y_root=220)
        launcher._on_press(press)
        launcher._on_release(press)
        toggle.assert_called_once_with()
        moved.assert_not_called()

        before = launcher.position()
        launcher._on_press(press)
        launcher._on_drag(SimpleNamespace(x_root=220, y_root=250))
        launcher._on_release(SimpleNamespace(x_root=220, y_root=250))
        self.assertEqual(launcher.position(), (before[0] + 20, before[1] + 30))
        self.assertEqual(moved.call_count, 1)
        self.assertEqual(toggle.call_count, 1)

    def test_dashboard_geometry_tracks_desktop_launcher(self):
        d = self.d
        launcher = d.launcher
        sw = launcher.window.winfo_screenwidth()
        # Place the hidden button in the upper-left quadrant so the popup
        # must align its left edge and open below the button.
        launcher._set_position(sw // 4, 40, notify=False)
        d._place_near_launcher()
        geometry = d.root.geometry()
        self.assertIn(f"+{launcher.position()[0]}+", geometry)

    def test_launcher_click_closes_dashboard_and_all_tracked_popups(self):
        d = self.d
        first, _body = d._popup_shell("first")
        second, _body2 = d._popup_shell("second")
        d._track_popup(first)
        d._track_popup(second)
        d._log_wins["web"] = first
        d.visible = True
        d.launcher.on_toggle = d.toggle
        click = SimpleNamespace(x_root=100, y_root=100)
        d.launcher._on_press(click)
        d.launcher._on_release(click)
        self.assertFalse(d.visible)
        self.assertEqual(d._popups, [])
        self.assertEqual(d._log_wins, {})
        self.assertFalse(first.winfo_exists())
        self.assertFalse(second.winfo_exists())

    def test_topmost_enforcement(self):
        d = self.d
        launcher = d.launcher
        self.assertIsNotNone(launcher)
        launcher.enforce_topmost()
        d._keep_root_topmost()
        with mock.patch("deck.ui.launcher.enforce_win32_topmost") as m_launcher, \
                mock.patch("deck.ui.app.enforce_win32_topmost") as m_app:
            launcher.enforce_topmost()
            m_launcher.assert_called_with(launcher.window)
            d.visible = True
            d._keep_root_topmost()
            m_app.assert_called_with(d.root)

    def test_launcher_right_click_context_menu(self):
        d = self.d
        launcher = d.launcher
        self.assertIsNotNone(launcher)
        cb = mock.Mock()
        launcher.on_context_menu = cb
        click_r = SimpleNamespace(x_root=150, y_root=180)
        launcher._on_r_press(click_r)
        launcher._on_r_release(click_r)
        cb.assert_called_once_with(150, 180)

        with mock.patch.object(d, "open_away_prompt") as m_prompt:
            with mock.patch("tkinter.Menu.tk_popup"):
                d.show_launcher_menu(100, 100)
                # Ensure the menu was built and has items
                self.assertIsNotNone(d._launcher_menu)
                self.assertGreater(d._launcher_menu.index("end"), 0)
                # Verify VS Code option exists in menu labels
                labels = [d._launcher_menu.entrycget(i, "label")
                          for i in range(d._launcher_menu.index("end") + 1)
                          if d._launcher_menu.type(i) == "command"]
                self.assertTrue(any("VS Code" in lbl for lbl in labels))

    def test_open_vscode(self):
        d = self.d
        with mock.patch("subprocess.Popen") as m_popen:
            d.open_vscode()
            m_popen.assert_called_once()
            args = m_popen.call_args[0][0]
            self.assertIn(str(core.HERE), args)

    def test_away_prompt_and_overlay_lifecycle(self):
        d = self.d
        from deck.ui import away
        # 1. Open prompt dialog
        prompt_win = d.open_away_prompt()
        self.assertIsNotNone(prompt_win)
        self.assertTrue(prompt_win.winfo_exists())
        self.assertIn(prompt_win, d._popups)

        # 2. Show away overlay directly with custom message
        ov = d.show_away_overlay("ไปกินข้าว 30 นาที")
        self.assertIsNotNone(ov)
        self.assertEqual(ov.message, "ไปกินข้าว 30 นาที")
        self.assertTrue(ov.window.winfo_exists())
        self.assertTrue(ov.window.overrideredirect())
        self.assertTrue(ov.window.attributes("-topmost"))

        # 3. Dismiss overlay
        ov.dismiss()
        self.assertTrue(ov._closing)
        # Flush after loop to complete fade out / destroy
        d.root.update()
        self.assertFalse(ov.window.winfo_exists())

        # 4. Test responsive overlay with short and long texts
        ov_short = d.show_away_overlay("7-11")
        self.assertTrue(ov_short.window.winfo_exists())
        ov_short.dismiss()

        ov_long = d.show_away_overlay("ฟังยุ ร้องเรียกเหมียวๆเดี๋ยวก็มา นั่งรอสักครู่")
        self.assertTrue(ov_long.window.winfo_exists())
        ov_long.dismiss()
        d.root.update()

    def test_speed_dial_toggle(self):
        d = self.d
        launcher = d.launcher
        self.assertIsNotNone(launcher)
        self.assertIsNone(d._speed_dial)
        # 1. Open speed dial
        d.toggle_speed_dial()
        self.assertIsNotNone(d._speed_dial)
        self.assertTrue(d._speed_dial.visible)
        self.assertTrue(d._speed_dial.window.winfo_exists())
        self.assertTrue(d._speed_dial.exit_window.winfo_exists())
        self.assertEqual(getattr(launcher, "_icon_name", "zap"), "x")
        d.root.update()
        # 2. Close speed dial
        d.toggle_speed_dial()
        self.assertFalse(d._speed_dial.visible)
        self.assertEqual(getattr(launcher, "_icon_name", "zap"), "zap")

    def test_sticky_note_persistence(self):
        import pathlib
        import tempfile
        d = self.d
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_path = pathlib.Path(tmp_dir) / "sticky_notes.json"
            with mock.patch("deck.ui.stickynote.NOTES_FILE", test_path):
                # Open sticky note
                note = d.toggle_sticky_note()
                self.assertIsNotNone(note)
                self.assertTrue(note.window.winfo_exists())
                self.assertTrue(note.window.attributes("-topmost"))
                # Type and save text
                note.txt.delete("1.0", "end")
                note.txt.insert("1.0", "My persistent task 123")
                note._save_content()
                # Close
                note.close()
                self.assertFalse(note.window.winfo_exists())
                # Re-open and verify text was loaded
                note2 = d.toggle_sticky_note()
                content = note2.txt.get("1.0", "end-1c")
                self.assertIn("My persistent task 123", content)
                note2.close()

    def test_tool_dialogs(self):
        d = self.d
        # Projects dialog
        win_p = d.open_projects()
        self.assertTrue(win_p.winfo_exists())
        d._close_popup(win_p)

        # Localhost Manager dialog
        with mock.patch("deck.ui.localhost_mgr.scan_listening_ports", return_value={3000: {"pid": 9999, "name": "node.exe"}}):
            win_lm = d.open_localhost_manager()
            self.assertTrue(win_lm.winfo_exists())
            d._close_popup(win_lm)

    def test_multi_sticky_notes_and_titles(self):
        import pathlib
        import tempfile
        d = self.d
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_path = pathlib.Path(tmp_dir) / "sticky_notes.json"
            with mock.patch("deck.ui.stickynote.NOTES_FILE", test_path):
                note = d.toggle_sticky_note()
                self.assertIsNotNone(note)
                self.assertEqual(note.title_var.get(), "Note 1")
                note.title_var.set("Project Tasks")
                sibling = d._sticky_mgr._on_new_note(note)
                self.assertIsNotNone(sibling)
                self.assertTrue(sibling.window.winfo_exists())
                self.assertEqual(sibling.title_var.get(), "Note 2")
                d._sticky_mgr.toggle()
                self.assertFalse(note.window.winfo_exists())
                self.assertFalse(sibling.window.winfo_exists())

    def test_dashboard_floating_and_escape(self):
        d = self.d
        d.show()
        self.assertTrue(d.visible)
        pos_before = (d.root.winfo_x(), d.root.winfo_y())
        # Moving launcher does not pull or move the dashboard
        d.launcher._set_position(120, 120, notify=True)
        d._launcher_moved()
        self.assertEqual((d.root.winfo_x(), d.root.winfo_y()), pos_before)
        # Can open speed dial while dashboard is open
        d.toggle_speed_dial()
        self.assertTrue(d._speed_dial.visible)
        self.assertTrue(d.visible)
        d.toggle_speed_dial()
        d.hide()
        self.assertFalse(d.visible)






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
