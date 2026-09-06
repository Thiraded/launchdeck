# History — moves, renames, incidents

## Home: Desktop -> `D:\WorkCombo` (2026-09-05)

The suite lived in `C:\Users\thira\OneDrive\Desktop` (a git repo pushing
to `Thiraded/Desktop`), mixed with unrelated files. Moved to
`D:\workcombo`: 30 files + `wc_logs/`, paths repointed (`wc_core.py`
now resolves next to itself with Desktop as legacy fallback),
`registry.json` / `works.json` / track-bats rewritten, `%~dp0` launchers
unchanged. Desktop keeps only the `wc.lnk` shortcut; `%LOCALAPPDATA%\
wc-bin` holds `wc` / `wctray` / `hermess` shims pointing at `D:`.
`hermess.bat` moved into the project (its shim updated); the 3 Hermes
config `.lnk`s stay on the Desktop by explicit order.

## Rename: `Thiraded/Desktop` -> `Thiraded/WorkCombo` (2026-09-05/06)

The GitHub repo was renamed; old URLs redirect. `D:` tracks
`Thiraded/WorkCombo@main`. Push history: `707be4d` (squashed snapshot
of the moved+evolved tree), then merge `9c77ea3` joining the pre-move
history (`-s ours`: tree stays current). Full old history browsable at
branch `archive/pre-move`. The local Desktop repo keeps the move commit
(`31a3ee0`) but must NOT push (its origin redirects to WorkCombo and
would collide — leave it local).

## The 23:54 revert (2026-09-05)

`D:` was bulk-overwritten with the pre-move tree (old paths, old bats,
foreign `.git` at `3d31430`) minutes after verification passed — almost
certainly from wiring up the freshly-renamed remote URL into `D:` in
the wrong direction. Recovered by: deleting the foreign `.git`,
re-applying every change from session history (`wc_core.py` + `gowc/`
had survived), re-verifying parity. Lesson: check `git log` +
filenames/mtimes (`hermess.bat` appearing out of nowhere was the tell)
before assuming the tree is yours; never pull a stale remote into a
newer working tree.

## Incidents that shaped the rules

- **2026-08-30 (x2):** infinite terminal spawn from a debug loop; loose
  kill pattern took Discord/browser/VS Code. -> machine-side-effect
  rule + DOWN-ONLY + token hygiene (see `kill-safety.md`).
- **2026-09-05:** ancestor-walk kill took the agent session + user apps.
  -> protected chain (see `kill-safety.md`).
- **2026-09-05/06:** Clint headless saga (windowless-but-running tree).
  -> headless doctrine (see `windows.md`).
- **2026-09-06:** Thai bytes in a browser tab CommandLine crashed scans
  under locale `cp1252`. -> utf-8+replace on every capture
  (see `verification.md`).

## Hide-path revert (2026-09-06)

`2ed9c4a` (launch-capture + X-disarm + `r` rebirth) made `h` hide worse
than the `9c77ea3`/`new-version` shape, so `wc_core.py` / `wc.py` /
`wctray.py` were reverted to `new-version` (+ kept utf-8+replace
hardening); Docs trimmed of capture/disarm/rebirth refs;
`wc_logs/*.log` untracked (`.track.bat` + `registry.json` stay tracked).
`hermess.bat` kept (live shim points at it).

## Rename: `Thiraded/WorkCombo` -> `Thiraded/wc-launcher` + public (2026-09-06)

Repo renamed and made public as a reusable launcher. `main` holds a
generic `works.json` (examples only) + `README.md`; real local paths live
on branch `personal`. Removed from tracking: 9 legacy `.bat` launchers
(batless config since the steps migration), `gowc.exe` (rebuild via
`go build` in `gowc/`), `spikes/` scratch, runtime files (`registry.json`,
`wc.settings.txt`, `wc_logs/*.track.bat` — local-only, git-ignored).
