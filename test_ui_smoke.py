"""Build the real Dashboard (Tk, withdrawn) against a FAKE manifest.

No process scan, no launch, no manifest/registry writes: every core
entry point that could touch the machine or works.json is mocked.
Safe on a live machine (see Docs/verification.md).
"""
import copy
import unittest
from unittest import mock

import launchdeck_core as core
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
            mock.patch.object(core, "hidden_work_ids", return_value=set()),
            mock.patch.object(core, "is_work_hidden", return_value=False),
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

    def test_log_viewer_opens(self):
        d = self.d
        with mock.patch.object(core, "work_log_path") as lp, \
                mock.patch.object(core, "work_display_log_path") as dp:
            lp.return_value = dp.return_value = core.HERE / "does-not-exist.log"
            d.open_log_viewer(FAKE["works"][0])
            d.root.update_idletasks()


if __name__ == "__main__":
    unittest.main()
