import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import launchdeck_core as core
from deck.core import jobs as _jobs
# Never open/kill a real deck job from a test (isolated namespace).
_jobs.PREFIX = "Local\\launchdeck-test-%d-" % __import__("os").getpid()
import launchdeck
from deck.ui import instance, state, tray as ui_tray


class Fn:
    def __init__(self, fn):
        self.fn = fn
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.fn(*args)


class FakeUser32:
    def __init__(self, owners):
        self.owners = owners
        self.GetWindowThreadProcessId = Fn(self._owner)
        self.IsWindowVisible = Fn(lambda _hwnd: 1)
        self.EnumWindows = Fn(self._enum)

    def _owner(self, hwnd, out):
        out._obj.value = self.owners.get(hwnd, 0)
        return 1

    def _enum(self, callback, _param):
        for hwnd in self.owners:
            callback(hwnd, 0)
        return 1


class KillSafetyTests(unittest.TestCase):
    def test_console_action_uses_one_scan_and_reports_blocked_stop(self):
        work = {"id": "demo", "label": "Demo"}
        node = SimpleNamespace(key="demo", kind="work", work=work)
        with mock.patch.object(launchdeck.core, "scan_commandlines",
                               return_value=["demo command"]), \
                mock.patch.object(launchdeck.core, "scan_available",
                                  return_value=True), \
                mock.patch.object(launchdeck.core, "is_running",
                                  return_value=True), \
                mock.patch.object(launchdeck.core, "kill_work",
                                  return_value=[123]):
            result = launchdeck.act_on_selected([node], {"demo": core.ON})
        self.assertIn("STOP BLOCKED: Demo (PIDs 123)", result)

    def test_console_action_does_not_launch_when_scan_is_unavailable(self):
        work = {"id": "demo", "label": "Demo"}
        node = SimpleNamespace(key="demo", kind="work", work=work)
        with mock.patch.object(launchdeck.core, "scan_commandlines",
                               return_value=[]), \
                mock.patch.object(launchdeck.core, "scan_available",
                                  return_value=False), \
                mock.patch.object(launchdeck.core, "launch_work") as launch:
            result = launchdeck.act_on_selected([node], {"demo": core.ON})
        self.assertIn("STATUS UNKNOWN: Demo", result)
        launch.assert_not_called()

    def test_dashboard_does_not_claim_a_blocked_stop_succeeded(self):
        work = {"id": "demo", "label": "Demo"}
        with mock.patch.object(core, "scan_commandlines",
                               return_value=["demo command"]), \
                mock.patch.object(core, "scan_available", return_value=True), \
                mock.patch.object(core, "is_running", return_value=True), \
                mock.patch.object(core, "kill_work", return_value=[123]):
            result = state.toggle_start_stop(work)
        self.assertIn("stop blocked 'Demo' (PIDs 123)", result)

    def test_dashboard_does_not_start_when_process_scan_is_unavailable(self):
        work = {"id": "demo", "label": "Demo"}
        with mock.patch.object(core, "scan_commandlines", return_value=[]), \
                mock.patch.object(core, "scan_available", return_value=False), \
                mock.patch.object(core, "launch_work") as launch:
            result = state.toggle_start_stop(work)
        self.assertIn("status unavailable", result)
        launch.assert_not_called()

    def test_broad_executable_token_refuses_to_kill(self):
        table = [
            (200, 1, "cmd.exe", "cmd.exe /c unrelated.bat"),
            (201, 200, "node.exe", "node unrelated.js"),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core.subprocess, "run") as run:
            result = core.kill_work(
                {"id": "target", "match": "cmd", "detect": True},
                dry_run=True,
            )
        self.assertEqual(result, [])
        run.assert_not_called()

    def test_path_detection_does_not_match_sibling_directory(self):
        self.assertFalse(core.is_running(
            {"id": "demo", "match": "D:\\apps\\demo"},
            ["node D:\\apps\\demo-old\\server.js"],
        ))

    def test_ambiguous_matching_roots_are_refused(self):
        table = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\apps\\demo-worker.bat"),
            (300, 1, "cmd.exe", "cmd.exe /c D:\\other\\demo-worker.bat"),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core.subprocess, "run") as run:
            result = core.kill_work(
                {"id": "demo", "match": "demo-worker"},
                dry_run=True,
            )
        self.assertEqual(result, [])
        run.assert_not_called()

    def test_registered_launch_root_wins_over_other_matching_processes(self):
        table = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (201, 200, "node.exe", "node D:\\apps\\demo.js"),
            (300, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (301, 300, "node.exe", "node D:\\apps\\other.js"),
        ]
        registry = {
            "demo": {
                "pid": 200,
                "runner": "D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat",
            }
        }
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value=registry):
            result = core.kill_work(
                {"id": "demo", "steps": [{"cmd": "node demo.js"}]},
                dry_run=True,
            )
        self.assertEqual(result, [200, 201])

    def test_runner_token_does_not_union_another_identity_token(self):
        table = [
            (200, 1, "cmd.exe",
             "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (201, 200, "node.exe", "node D:\\apps\\demo.js"),
            (300, 1, "cmd.exe", "cmd.exe /c D:\\other\\start.bat"),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}):
            result = core.kill_work(
                {"id": "demo", "steps": [{"cmd": "node demo.js"}],
                 "match": "D:\\apps\\demo.js",
                 "vars": {"APPDIR": "D:\\other"}},
                dry_run=True,
            )
        self.assertEqual(result, [200, 201])

    def test_duplicate_generated_runner_roots_are_one_work_identity(self):
        table = [
            (200, 1, "cmd.exe",
             "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (201, 200, "node.exe", "node D:\\apps\\demo.js"),
            (300, 1, "cmd.exe",
             "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (301, 300, "node.exe", "node D:\\apps\\demo.js"),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}):
            result = core.kill_work(
                {"id": "demo", "steps": [{"cmd": "node demo.js"}]},
                dry_run=True,
            )
        self.assertEqual(result, [200, 201, 300, 301])

    def test_runner_can_add_manual_project_root_but_not_env_file_reference(self):
        table = [
            (200, 1, "cmd.exe",
             "cmd.exe /c D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat"),
            (201, 200, "node.exe", "node D:\\apps\\demo\\runner.js"),
            (300, 1, "node.exe", "node D:\\apps\\demo\\server.js"),
            (400, 1, "node.exe",
             "node --env-file=D:\\apps\\demo\\.env D:\\other\\app.js"),
        ]
        registry = {
            "demo": {
                "pid": 200,
                "runner": "D:\\launchdeck\\wc_logs\\launchdeck-gen-demo.bat",
            }
        }
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value=registry):
            result = core.kill_work(
                {"id": "demo", "steps": [{"cmd": "node demo.js"}],
                 "match": "D:\\apps\\demo"},
                dry_run=True,
            )
        self.assertEqual(result, [200, 201, 300])

    def test_sibling_processes_under_one_dev_parent_are_one_work(self):
        table = [
            (100, 1, "node.exe", "node scripts/dev.mjs"),
            (200, 100, "node.exe", "node D:\\apps\\demo\\web.js"),
            (300, 100, "node.exe", "node D:\\apps\\demo\\server.js"),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}):
            result = core.kill_work(
                {"id": "demo", "match": "D:\\apps\\demo"},
                dry_run=True,
            )
        self.assertEqual(result, [200, 300])

    def test_codex_working_directory_process_is_never_a_seed(self):
        table = [
            (200, 1, "node.exe",
             '"C:\\Users\\thira\\...\\cua_node\\bin\\node.exe" '
             'trusted-worker.js D:\\HammonQuest'),
        ]
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value={}):
            result = core.kill_work(
                {"id": "hamstermap", "match": "D:\\HammonQuest"},
                dry_run=True,
            )
        self.assertEqual(result, [])

    def test_pid_reuse_is_rejected_before_force_kill(self):
        initial = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\demo.bat"),
            (201, 200, "node.exe", "node demo.js"),
        ]
        after_wait = [
            (200, 1, "cmd.exe", "cmd.exe /c unrelated.bat"),
            (201, 200, "node.exe", "node demo.js"),
        ]
        scans = iter([initial, after_wait])
        taskkills = []
        with mock.patch.object(core, "scan_table", side_effect=lambda: next(scans)), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core, "close_work_windows", return_value=0), \
                mock.patch.object(core, "_gowc_available", return_value=False), \
                mock.patch.object(core.time, "sleep"), \
                mock.patch.object(core.subprocess, "run",
                                  side_effect=lambda args, **_kw: taskkills.append(args)):
            result = core.kill_work(
                {"id": "demo", "match": "D:\\launchdeck\\demo.bat"},
                dry_run=False,
            )
        self.assertIsNone(result)
        self.assertEqual(taskkills,
                         [["taskkill.exe", "/PID", "200"],
                          ["taskkill.exe", "/PID", "201"]])

    def test_reparented_descendant_is_force_killed_after_root_exits(self):
        initial = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\demo.bat"),
            (201, 200, "node.exe", "node demo.js"),
        ]
        # A surviving child can be re-parented after its wrapper exits.  Its
        # own identity is unchanged, so it remains a safe target.
        after_wait = [
            (201, 1, "node.exe", "node demo.js"),
        ]
        taskkills = []
        with mock.patch.object(core, "scan_table",
                               side_effect=[initial, after_wait,
                                            [(999, 1, "other.exe", "other")]]), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core, "close_work_windows", return_value=0), \
                mock.patch.object(core, "_gowc_available", return_value=False), \
                mock.patch.object(core.time, "sleep"), \
                mock.patch.object(core.subprocess, "run",
                                  side_effect=lambda args, **_kw: taskkills.append(args)), \
                mock.patch.object(core, "clear_hidden_work"), \
                mock.patch.object(core, "unregister"):
            result = core.kill_work(
                {"id": "demo", "match": "D:\\launchdeck\\demo.bat"},
                dry_run=False,
            )
        self.assertIsNone(result)
        self.assertEqual(taskkills,
                         [["taskkill.exe", "/PID", "200"],
                          ["taskkill.exe", "/PID", "201"],
                          ["taskkill.exe", "/F", "/PID", "201"]])

    def test_registered_pid_must_still_be_the_recorded_runner(self):
        table = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\other\\demo.bat"),
            (201, 200, "node.exe", "node D:\\other\\demo.js"),
        ]
        registry = {
            "demo": {
                "pid": 200,
                "runner": "D:\\launchdeck\\demo.bat",
            }
        }
        with mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_load_registry", return_value=registry), \
                mock.patch.object(core.subprocess, "run") as run:
            result = core.kill_work(
                {"id": "demo", "match": "demo",
                 "bat": "D:\\launchdeck\\demo.bat"},
                dry_run=True,
            )
        self.assertEqual(result, [])
        run.assert_not_called()

    def test_surviving_descendant_is_force_killed_after_root_exits(self):
        initial = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\demo.bat"),
            (201, 200, "node.exe", "node demo.js"),
        ]
        after_wait = [
            (201, 200, "node.exe", "node demo.js"),
        ]
        taskkills = []
        with mock.patch.object(core, "scan_table",
                               side_effect=[initial, after_wait,
                                            [(999, 1, "other.exe", "other")]]), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core, "close_work_windows", return_value=0), \
                mock.patch.object(core, "_gowc_available", return_value=False), \
                mock.patch.object(core.time, "sleep"), \
                mock.patch.object(core.subprocess, "run",
                                  side_effect=lambda args, **_kw: taskkills.append(args)), \
                mock.patch.object(core, "clear_hidden_work"), \
                mock.patch.object(core, "unregister"):
            result = core.kill_work(
                {"id": "demo", "match": "D:\\launchdeck\\demo.bat"},
                dry_run=False,
            )
        self.assertIsNone(result)
        self.assertEqual(taskkills,
                         [["taskkill.exe", "/PID", "200"],
                          ["taskkill.exe", "/PID", "201"],
                          ["taskkill.exe", "/F", "/PID", "201"]])

    def test_failed_force_sweep_is_reported_and_registry_is_kept(self):
        initial = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\demo.bat"),
            (201, 200, "node.exe", "node demo.js"),
        ]
        taskkills = []
        with mock.patch.object(core, "scan_table",
                               side_effect=[initial, initial, initial]), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core, "close_work_windows", return_value=0), \
                mock.patch.object(core, "_gowc_available", return_value=False), \
                mock.patch.object(core.time, "sleep"), \
                mock.patch.object(core.subprocess, "run",
                                  side_effect=lambda args, **_kw: taskkills.append(args)), \
                mock.patch.object(core, "clear_hidden_work") as clear_hidden, \
                mock.patch.object(core, "unregister") as unregister:
            result = core.kill_work(
                {"id": "demo", "match": "D:\\launchdeck\\demo.bat"},
                dry_run=False,
            )
        self.assertEqual(result, [200, 201])
        self.assertEqual(taskkills,
                         [["taskkill.exe", "/PID", "200"],
                          ["taskkill.exe", "/PID", "201"],
                          ["taskkill.exe", "/F", "/PID", "200"],
                          ["taskkill.exe", "/F", "/PID", "201"]])
        clear_hidden.assert_not_called()
        unregister.assert_not_called()

    def test_empty_revalidation_blocks_force_kill(self):
        initial = [
            (200, 1, "cmd.exe", "cmd.exe /c D:\\launchdeck\\demo.bat"),
        ]
        taskkills = []
        with mock.patch.object(core, "scan_table",
                               side_effect=[initial, []]), \
                mock.patch.object(core, "_load_registry", return_value={}), \
                mock.patch.object(core, "close_work_windows", return_value=0), \
                mock.patch.object(core.time, "sleep"), \
                mock.patch.object(core.subprocess, "run",
                                  side_effect=lambda args, **_kw: taskkills.append(args)), \
                mock.patch.object(core, "clear_hidden_work") as clear_hidden, \
                mock.patch.object(core, "unregister") as unregister:
            result = core.kill_work(
                {"id": "demo", "match": "D:\\launchdeck\\demo.bat"},
                dry_run=False,
            )
        self.assertEqual(result, [200])
        self.assertEqual(taskkills, [["taskkill.exe", "/PID", "200"]])
        clear_hidden.assert_not_called()
        unregister.assert_not_called()

    def test_window_owner_walk_stops_before_explorer(self):
        owners = {100: 200, 101: 300}
        table = [
            (200, 300, "worker.exe", "worker TARGETTOKEN"),
            (300, 1, "explorer.exe", "explorer.exe"),
        ]
        api = FakeUser32(owners)
        with mock.patch.object(ctypes, "windll", SimpleNamespace(user32=api)):
            found = core._hwnds_for_pids({200}, table)
        self.assertEqual(found, [100])

    def test_find_work_hwnds_never_climbs_into_ide_or_explorer(self):
        # Manual run inside a VSCode terminal: node -> cmd -> powershell ->
        # Code.exe -> explorer.exe. Only the cmd host may join the owners.
        owners = {100: 20, 101: 30, 102: 50, 103: 60, 104: 70}
        table = [
            (10, 20, "node.exe", r"node D:\proj\server.js"),
            (20, 30, "cmd.exe", r"cmd /c npm run dev"),
            (30, 50, "powershell.exe", "powershell"),
            (50, 60, "Code.exe", "Code.exe"),
            (60, 1, "explorer.exe", "explorer.exe"),
            (70, 50, "Code.exe", "Code.exe --type=renderer"),
        ]
        work = {"id": "proj", "label": "Proj", "match": r"D:\proj"}
        api = FakeUser32(owners)
        with mock.patch.object(ctypes, "windll", SimpleNamespace(user32=api)), \
                mock.patch.object(core, "scan_table", return_value=table), \
                mock.patch.object(core, "_title_hwnds_guarded", return_value=[]):
            found = core.find_work_hwnds(work)
        self.assertEqual(found, [100])

    def _materialize(self, work):
        import tempfile
        d = tempfile.mkdtemp()
        with mock.patch.object(core.os.path, "abspath",
                               return_value=os.path.join(d, "x.py")):
            path = core.materialize_steps(work)
        with open(path, encoding="utf-8", newline="") as f:
            return path, f.read()

    def test_generated_bat_escapes_label_and_guards_cd(self):
        work = {"id": "inj", "label": "A & calc | x > y %PATH%",
                "steps": [{"cmd": 'cd /d "D:\\nope"'}, {"cmd": "npm run dev"},
                          {"cmd": 'mkdir "D:\\l" 2>nul'}]}
        _path, text = self._materialize(work)
        lines = text.split("\r\n")
        self.assertIn("title A ^& calc ^| x ^> y %%PATH%%", lines)
        self.assertIn('cd /d "D:\\nope" || goto :deck_cd_failed', lines)
        self.assertIn('mkdir "D:\\l" 2>nul', lines)  # not guarded
        self.assertIn(":deck_cd_failed", lines)
        self.assertLess(lines.index("exit /b 0"), lines.index(":deck_cd_failed"))
        self.assertFalse(text.startswith("@chcp"))

    def test_generated_bat_non_ascii_switches_codepage(self):
        _path, text = self._materialize(
            {"id": "th", "label": "งาน", "steps": [{"cmd": "echo ok"}]})
        self.assertTrue(text.startswith("@chcp 65001 >nul\r\n"))

    def test_generated_bat_not_rewritten_when_unchanged(self):
        work = {"id": "same", "label": "Same", "steps": [{"cmd": "echo ok"}]}
        path, _ = self._materialize(work)
        os.utime(path, (1, 1))
        self._materialize(work)
        self.assertEqual(os.stat(path).st_mtime, 1)

    def test_enter_action_refuses_to_launch_on_failed_scan(self):
        work = {"id": "w", "label": "W", "match": "tok-xyz"}
        node = core.Node("w", "W", "work", work=work)
        with mock.patch.object(core, "_scan_table_gowc", return_value=None), \
                mock.patch.object(core, "_scan_table_ps", return_value=[]):
            self.assertEqual(core.enter_action(core.ON, node, [node]), [])

    def test_recompute_states_scans_once(self):
        manifest = {"groups": [{"id": "g", "label": "G",
                                "members": ["a", "b", "c"]}],
                    "works": [{"id": x, "label": x, "match": f"tok-{x}-zz"}
                              for x in "abc"]}
        model = core.build_model(manifest)
        rows = [(9, 1, "node.exe", "node tok-a-zz")]
        with mock.patch.object(core, "scan_table", return_value=rows) as scan:
            core._SCAN_STATE.ok = True
            states = {"a": core.OFF, "b": core.OFF, "c": core.RUN}
            core.recompute_states(model, states)
        self.assertEqual(scan.call_count, 1)
        self.assertEqual((states["a"], states["b"], states["c"]),
                         (core.RUN, core.OFF, core.OFF))

    def test_tray_menu_run_is_queued_not_executed(self):
        tray = ui_tray.WorkTray.__new__(ui_tray.WorkTray)
        tray._menu_ids = {5000: ("w1", "run")}
        with mock.patch.object(state, "work_by_id",
                               return_value={"id": "w1"}), \
                mock.patch.object(state, "toggle_start_stop") as tss, \
                mock.patch.object(state, "actions") as q:
            tray._on_menu(5000)
        tss.assert_not_called()
        q.put.assert_called_once_with(("run", "w1"))

    def test_single_instance_mutex_second_owner_exits(self):
        dash = instance
        name = f"Local\\launchdeck-test-{os.getpid()}"
        with mock.patch.object(dash, "_INSTANCE_MUTEX", name), \
                mock.patch.object(dash, "_instance_handle", None):
            dash.ensure_single_instance(timeout_s=0)
            self.assertTrue(dash._instance_handle)
            with mock.patch.object(dash.os, "_exit",
                                   side_effect=SystemExit) as ex, \
                    mock.patch.object(dash.time, "sleep"):
                with self.assertRaises(SystemExit):
                    dash.ensure_single_instance(timeout_s=0)
            ex.assert_called_once_with(0)
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(dash._instance_handle))

    def test_kill_window_pass_does_not_close_hosting_shell(self):
        owners = {100: 200, 101: 300}
        table = [
            (200, 300, "worker.exe", "worker TARGETTOKEN"),
            (300, 1, "cmd.exe", "cmd.exe /k user-shell"),
        ]
        api = FakeUser32(owners)
        with mock.patch.object(ctypes, "windll", SimpleNamespace(user32=api)):
            found = core._hwnds_for_pids({200}, table,
                                         include_ancestors=False)
        self.assertEqual(found, [100])

    def test_empty_gowc_scan_falls_back_to_powershell(self):
        ps_rows = [(10, 1, "cmd.exe", "cmd.exe /c demo.bat")]
        with mock.patch.object(core, "_gowc_available", return_value=True), \
                mock.patch.object(core.subprocess, "run",
                                  return_value=SimpleNamespace(returncode=0, stdout="")), \
                mock.patch.object(core, "_scan_table_ps", return_value=ps_rows) as fallback:
            result = core.scan_table()
        self.assertEqual(result, ps_rows)
        fallback.assert_called_once_with()

    def test_scan_commandlines_excludes_launcher_pid(self):
        rows = [
            (os.getpid(), 1, "python.exe", "python launchdeck.py target"),
            (20, 1, "node.exe", "node target.js"),
        ]
        with mock.patch.object(core, "scan_table", return_value=rows):
            self.assertEqual(core.scan_commandlines(), ["node target.js"])

    def test_launch_failure_is_not_reported_as_started(self):
        core._launch_times.pop("demo", None)
        work = {"id": "demo", "steps": [{"cmd": "echo demo"}]}
        with mock.patch.object(core, "run_work", return_value=None), \
                mock.patch.object(core, "register") as register:
            result = core.launch_work(work)
        self.assertIsNone(result)
        self.assertEqual(core._launch_times.get("demo"), [])
        register.assert_not_called()

    def test_launch_cap_is_per_work_rate_not_lifetime(self):
        for wid in ("a1", "b1"):
            core._launch_times.pop(wid, None)
        with mock.patch.object(core, "run_work", return_value=True):
            ok = [core.launch_work({"id": "a1", "steps": [{"cmd": "x"}]})
                  for _ in range(core.LAUNCH_BURST + 1)]
            other = core.launch_work({"id": "b1", "steps": [{"cmd": "x"}]})
            # Old entries age out of the window -> the work can start again.
            core._launch_times["a1"] = [
                t - core.LAUNCH_WINDOW_S for t in core._launch_times["a1"]]
            again = core.launch_work({"id": "a1", "steps": [{"cmd": "x"}]})
        self.assertTrue(all(ok[:core.LAUNCH_BURST]))
        self.assertIsNone(ok[-1])
        self.assertIsNotNone(other)
        self.assertIsNotNone(again)

    def test_registry_updates_do_not_lose_keys(self):
        import tempfile
        import threading
        with tempfile.TemporaryDirectory() as d:
            reg = core.Path(d) / "registry.json"
            with mock.patch.object(core, "REGISTRY", reg):
                ths = [threading.Thread(
                    target=core.register, args=({"id": f"w{i}"},))
                    for i in range(20)]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join()
                data = core._load_registry()
        self.assertEqual(sorted(data), sorted(f"w{i}" for i in range(20)))

    def test_scan_available_is_per_thread(self):
        import threading
        with mock.patch.object(core, "_scan_table_gowc", return_value=None), \
                mock.patch.object(core, "_scan_table_ps",
                                  return_value=[(1, 0, "x.exe", "x")]):
            core.scan_table()
        seen = []

        def other():
            with mock.patch.object(core, "_scan_table_gowc", return_value=None), \
                    mock.patch.object(core, "_scan_table_ps", return_value=[]):
                core.scan_table()
            seen.append(core.scan_available())

        t = threading.Thread(target=other)
        t.start()
        t.join()
        self.assertEqual(seen, [False])
        self.assertTrue(core.scan_available())


if __name__ == "__main__":
    unittest.main()
