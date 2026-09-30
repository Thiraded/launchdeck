"""Job Object launch/stop, end to end through core.run_work / kill_work.

Spawns ONLY its own children (python / node sleepers) inside jobs in an
isolated namespace (`Local\\launchdeck-test-<pid>-*`); every kill is a
job-membership kill re-checked with IsProcessInJob, so nothing else on
the machine can be hit. Still opt-in, per Docs/verification.md:

    set LAUNCHDECK_SPAWN_TESTS=1 && python -m unittest test_jobs
"""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import launchdeck_core as core
from deck.core import jobs

jobs.PREFIX = "Local\\launchdeck-test-%d-" % os.getpid()

# node, not python: Store Python (WindowsApps) is re-launched through
# package activation and lands OUTSIDE the job. Real works run node.
TREE = """const { spawn } = require('child_process');
spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
console.log('tree up'); setInterval(() => {}, 1000);
"""
GRACE = """const fs = require('fs'); const m = process.argv[2];
process.on('SIGBREAK', () => { fs.writeFileSync(m, 'clean'); process.exit(0); });
console.log('node up'); setInterval(() => {}, 1000);
"""


def _alive(pid):
    import ctypes
    k = ctypes.WinDLL("kernel32")
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
    k.CloseHandle(ctypes.c_void_p(h))
    return code.value == 259


def _wait(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


@unittest.skipUnless(os.name == "nt" and os.environ.get("LAUNCHDECK_SPAWN_TESTS") == "1",
                     "spawns processes: opt in with LAUNCHDECK_SPAWN_TESTS=1")
@unittest.skipUnless(shutil.which("node"), "node not installed")
class JobLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ld-jobs-"))
        self.reg = mock.patch.object(core, "REGISTRY", self.tmp / "registry.json")
        self.reg.start()
        self.works = []

    def tearDown(self):
        for w in self.works:  # never leave a child behind, whatever failed
            h = jobs._open(w["id"])
            if h:
                jobs._k32.TerminateJobObject(h, 1)
                _wait(lambda: not jobs._pids(h), 3)  # log handles close
            for p in (core.work_log_path(w),
                      os.path.join(os.path.dirname(core.__file__), "wc_logs",
                                   core.gen_bat_name(w))):
                for _ in range(20):  # a just-killed child may still hold the log
                    try:
                        os.remove(p)
                        break
                    except FileNotFoundError:
                        break
                    except OSError as e:
                        last = e
                        time.sleep(0.1)
                else:
                    print("tearDown could not remove", p, last)
        self.reg.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _work(self, name, steps, **vars_):
        w = {"id": f"zz-jobtest-{os.getpid()}-{name}", "label": f"jobtest {name}",
             "run": "detached", "detect": True, "steps": steps, "vars": vars_}
        self.works.append(w)
        return w

    def test_tree_is_contained_and_stopped(self):
        script = self.tmp / "tree.js"
        script.write_text(TREE)
        w = self._work("tree", [{"cmd": 'cd /d "%TMPD%"'}, {"cmd": "node tree.js"}],
                        TMPD=str(self.tmp))
        self.assertTrue(jobs.eligible(w))
        self.assertTrue(core.run_work(w))
        self.assertTrue(_wait(lambda: len(core.kill_work(w, dry_run=True) or []) >= 3))
        members = core.kill_work(w, dry_run=True)   # cmd + node + grandchild
        self.assertTrue(core.is_running(w))
        t0 = time.monotonic()
        self.assertIsNone(core.kill_work(w))
        took = time.monotonic() - t0
        self.assertTrue(_wait(lambda: not any(_alive(p) for p in members), 3))
        self.assertFalse(core.is_running(w))
        self.assertNotIn(w["id"], core._load_registry())
        self.assertLess(took, jobs.STOP_GRACE_S + 2)

    def test_node_gets_ctrl_break_and_exits_clean(self):
        (self.tmp / "grace.js").write_text(GRACE)
        marker = self.tmp / "marker.txt"
        w = self._work("node", [{"cmd": 'cd /d "%TMPD%"'},
                                {"cmd": 'node grace.js "%MARK%"'}],
                       TMPD=str(self.tmp), MARK=str(marker))
        self.assertTrue(core.run_work(w))
        self.assertTrue(_wait(lambda: "node up" in Path(core.work_log_path(w)).read_text(
            errors="replace")))
        t0 = time.monotonic()
        self.assertIsNone(core.kill_work(w))
        self.assertEqual(marker.read_text(), "clean")   # graceful, not forced
        self.assertLess(time.monotonic() - t0, 2.0)

    def test_restarted_deck_reopens_job_by_name(self):
        script = self.tmp / "tree.js"
        script.write_text(TREE)
        w = self._work("reopen", [{"cmd": 'cd /d "%TMPD%"'}, {"cmd": "node tree.js"}],
                        TMPD=str(self.tmp))
        self.assertTrue(core.run_work(w))
        self.assertTrue(_wait(lambda: jobs.managed(w["id"])))
        # Simulate a deck restart: drop every handle this process holds.
        jobs._k32.CloseHandle(jobs._handles.pop(w["id"]))
        self.assertTrue(jobs.managed(w["id"]), "job name died with the deck's handle")
        self.assertIsNone(core.kill_work(w))

    def test_never_seed_member_is_neither_counted_nor_killed(self):
        script = self.tmp / "tree.js"
        script.write_text(TREE)
        w = self._work("never", [{"cmd": 'cd /d "%TMPD%"'}, {"cmd": "node tree.js"}],
                        TMPD=str(self.tmp))
        self.assertTrue(core.run_work(w))
        self.assertTrue(_wait(lambda: len(jobs.members(w["id"])) >= 3))
        spared = [p for p in jobs.members(w["id"]) if jobs._names([p]).get(p) == "node.exe"]
        # Treat node like a browser the work opened. A browser is a GUI
        # process (no console event reaches it), so skip CTRL_BREAK and
        # check the FORCED path: it must never TerminateProcess a never-seed.
        with mock.patch.object(jobs, "ctrl_break", return_value=True):
            self.assertEqual(jobs.stop(w["id"], never=frozenset({"node.exe"}), grace=0), [])
        self.assertTrue(spared and all(_alive(p) for p in spared))
        self.assertFalse(jobs.managed(w["id"], frozenset({"node.exe"})))


if __name__ == "__main__":
    unittest.main()
