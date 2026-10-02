---
title: 'Fix tray crash and reliable hide/restore lifecycle'
type: 'bugfix'
created: '2026-09-05'
status: 'done'
baseline_commit: '7076f30672c04be7bf0eeac09630e22e6c63af9b'
review_loop_iteration: 1
context: ['AGENTS.md']
---

> Superseded on 2026-10-02: the terminal frontend and console hide/restore
> integration described here have been removed. Keep this file as historical
> evidence for the old tray fix; current behavior is documented in `Docs/tray.md`.

<frozen-after-approval reason="human-owned intent â€” do not modify unless human renegotiates">

## Intent

**Problem:** The tray host repeatedly raises native access violations, leaves duplicate or ghost tray instances, and can fail to restore a hidden work window. The current implementation has incomplete Win32 prototypes, cross-thread window teardown, duplicate action consumers, and unsynchronized hidden-window state.

**Approach:** Repair the Win32 boundary and make the tray thread own its complete lifecycle, route UI actions through one consumer, and serialize hide/restore/sweep state transitions. Keep the existing dashboard, launcher manifest, visible work terminals, and downward-only kill safety model.

## Boundaries & Constraints

**Always:** Preserve unrelated working-tree changes. Keep work launches visible. Keep kill traversal downward-only and protected-process rules intact. Use exact, non-destructive tests that never kill or hide arbitrary user processes. Fail tray startup visibly in logs when Win32 initialization is incomplete.

**Historical ask-first rule:** any process termination, launcher removal,
manifest migration, or product rename required approval at the time this spec
was written. Current authorization comes from the user's 2026-10-02 request.

**Never:** Run the existing live-process integration test unattended; use broad process termination; discard existing edits; touch the pending bat migration, registry data, or hermes launcher rename.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Tray startup | 64-bit Python on Windows | All required prototypes initialize before window creation; one tray host becomes ready | Initialization failure returns unavailable and records the exact failure |
| Tray shutdown | Tk thread requests quit | Tray thread removes icons, destroys its own window, exits its message loop, and is joined | Timeout is logged and no cross-thread DestroyWindow call is made |
| Restore hidden work | Tracked valid HWNDs | Hide intent is cleared before restore; valid windows receive SW_RESTORE and are verified visible | Invalid HWNDs are pruned; state is retained when visibility cannot be confirmed |
| Monitor sweep | Sweep overlaps restore | A restored work is not re-hidden after the user requests Show | Shared hidden state is guarded by one lock |
| Tray action | Callback enqueues toggle/unpark/quit | Exactly one Tk-side dispatcher consumes and applies each action | Unknown actions are logged without crashing |

</frozen-after-approval>

## Code Map

- `launchdeck_tray.py` -- ctypes declarations, tray window, icon operations, and native message loop.
- `launchdeck_dashboard.py` -- dashboard, action dispatch, monitoring, and tray integration.
- `launchdeck_core.py` -- process discovery plus hidden HWND state and hide/show/sweep operations.
- `test_tray_foundation.py` -- new non-destructive unit tests using fakes/mocks only.

## Tasks & Acceptance

**Execution:**
- [x] `launchdeck_tray.py` -- make prototype setup atomic and correct; add tray-thread shutdown message; make lifecycle cleanup idempotent.
- [x] `launchdeck_dashboard.py` -- remove the second queue consumer and keep one deterministic dispatcher; retain current dashboard behavior.
- [x] `launchdeck_core.py` -- lock hidden state, clear hide intent before restore, validate HWNDs, use SW_RESTORE, and confirm post-command visibility without treating ShowWindowAsync return as success.
- [x] `test_tray_foundation.py` -- cover prototype initialization, shutdown routing, action dispatch, restore result semantics, invalid handles, and sweep/restore ordering without opening windows or killing processes.

**Acceptance Criteria:**
- The historical 64-bit tray setup had pointer-safe native handle prototypes and surfaced initialization failures.
- Given a live tray message loop, when the UI requests shutdown, then destruction runs on the tray thread and the worker exits without an access violation.
- Given one queued action, when the Tk dispatcher polls, then exactly one handler executes it.
- Given a work being restored while the monitor sweeps, when restore begins, then the sweep cannot re-hide that work.
- Given invalid or reused HWNDs, when Show is requested, then they are removed safely and no false restored count is reported.
- Given the current dirty worktree, when changes are reviewed, then bat files, registry.json, logs, and hermes launcher changes remain untouched.

## Spec Change Log

- 2026-09-05: Blind and edge-case review hardened HWND ownership, serialized hide/restore, tray-thread shutdown, icon cleanup, Explorer rebuild state, and action exception isolation.

## Design Notes

The tray window is thread-affine: the thread that creates it must also process its shutdown message and destroy it. Python-side state changes can be requested from other threads only through messages or queues. Hidden-window state has one lock and one authoritative state transition so the monitor cannot race a user restore.

## Verification

**Commands:**
- `python -m py_compile launchdeck_core.py launchdeck_tray.py launchdeck_dashboard.py test_tray_foundation.py` -- expected: no syntax errors.
- `python -m unittest -v test_tray_foundation.py` -- expected: all tests pass without creating a tray icon, opening a work terminal, hiding a real window, or terminating a process.
- `git diff --check` -- expected: no whitespace errors.

**Manual checks:**
- Historical live smoke opened the old dashboard, hid and showed one controlled work, then repeated; expected one icon, one process owner, and no new access-violation log.

## Suggested Review Order

**Reliable hide and restore state**

- Start with serialized, owner-validated hide state and confirmed visibility transitions.
  [`launchdeck_core.py`](launchdeck_core.py)

- Restore clears intent first and retains only windows still hidden.
  [`launchdeck_core.py`](launchdeck_core.py)

- Sweeps share each work lock so they cannot race a user restore.
  [`launchdeck_core.py`](launchdeck_core.py)

**Native tray lifecycle**

- Explorer rebuilds now keep availability truthful and recreate parked icons.
  [`launchdeck_tray.py`](launchdeck_tray.py)

- Shutdown is posted to the owner thread and reports timeout failures.
  [`launchdeck_tray.py`](launchdeck_tray.py)

- Secondary icon registration cleans both shell and GDI resources on failure.
  [`launchdeck_tray.py`](launchdeck_tray.py)

**Single action path and regression coverage**

- One Tk dispatcher isolates failed actions while continuing and rescheduling.
  [`launchdeck_dashboard.py`](launchdeck_dashboard.py)

- Mock-only tests cover lifecycle, handle reuse, cleanup, and queue failures.
  [`test_tray_foundation.py:33`](test_tray_foundation.py#L33)
