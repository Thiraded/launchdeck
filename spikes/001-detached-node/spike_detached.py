"""SPIKE 001: detached (docker-style) node worker on Windows.

Validates, with a THROWAWAY scratch process (never a real work):
  1. CREATE_NO_WINDOW launch -> truly zero HWNDs (no console to lose)
  2. stdout lands in a log file (the future `docker logs`)
  3. token still matches in CommandLine (detection unchanged)
  4. exact-PID structural kill (children of OUR pid only, never token sweep)

Run:  python -u spikes/001-detached-node/spike_detached.py
"""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import wc_core as c

TOKEN = "wc-spike-detached-9f37"
LOG = os.path.join(tempfile.gettempdir(), "wc_spike_001.log")
for p in (LOG,):
    try:
        os.remove(p)
    except OSError:
        pass

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (" -- " + str(detail) if detail else ""))


# 1. launch detached -------------------------------------------------------
with open(LOG, "w", encoding="utf-8", errors="replace") as lf:
    proc = subprocess.Popen(
        ["cmd.exe", "/c",
         "echo hello-%s && ping -n 25 127.0.0.1 >nul" % TOKEN],
        stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=c._NO_WINDOW)
root = proc.pid
time.sleep(3)

# our tree: root + descendants (structural, from parent map)
tree = {root}
kids = {}
for pid, ppid, _n, _cmd in c.scan_table():
    kids.setdefault(ppid, []).append(pid)
stack = [root]
while stack:
    for ch in kids.get(stack.pop(), []):
        if ch not in tree:
            tree.add(ch)
            stack.append(ch)

# 2. zero HWNDs (ALL top-level windows, visible or not) -----------------------
import ctypes
u = ctypes.windll.user32
u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                       ctypes.POINTER(ctypes.c_ulong)]
owned = []


@ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
def cb(h, _):
    o = ctypes.c_ulong(0)
    u.GetWindowThreadProcessId(h, ctypes.byref(o))
    if o.value in tree:
        owned.append(int(h))
    return 1


u.EnumWindows(cb, 0)
_c = cb  # keep callback alive
check("zero-HWND (windowless)", not owned, "owned=%r tree=%r" % (owned, sorted(tree)))

# 3. log capture -------------------------------------------------------------
with open(LOG, encoding="utf-8", errors="replace") as lf:
    body = lf.read()
check("log-capture", ("hello-" + TOKEN) in body, repr(body[:60]))

# 4. token detection ----------------------------------------------------------
cls = c.scan_commandlines()
check("token-detect", any(TOKEN in (l or "") for l in cls))

# 5. exact-PID kill ------------------------------------------------------------
me = os.getpid()
names = {p: n for p, _pp, n, _cm in c.scan_table()}
victims = [p for p in tree if p != me]
for p in victims:
    try:
        subprocess.run(["taskkill.exe", "/F", "/PID", str(p)],
                       capture_output=True, timeout=10,
                       creationflags=c._NO_WINDOW)
    except Exception as e:
        print("kill pid %r: %r" % (p, e))
time.sleep(2)
alive = [p for p in victims
         if any(pp == p for pp, _pp2, _n2, _c2 in c.scan_table())]
check("exact-kill", not alive, "still-alive=%r" % alive)

print("RESULT:", "ALL PASS" if all(results) else "FAILURES PRESENT")
sys.exit(0 if all(results) else 1)
