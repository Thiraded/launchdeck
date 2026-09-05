# Status — current state and open gates (2026-09-06)

## Live right now

- hamster-server: RUNNING (relaunched by user after the full-close test).
- omniroute-cli / omniroute-web: detection-positive only — their tokens
  match a Brave tab URL, no killable tree (`dry_run` empty). Cosmetic;
  do not "fix" by broadening tokens (see `kill-safety.md` rule 5).
- No TUIs running (wc.py / wctray all closed for a clean slate).
- hamster-clint / hamsterquest / mr-* / gpt-mcp: stopped.

## Verified working (human-confirmed)

- Kill closes the whole window (3-pass + WM_CLOSE), incl. the Clint
  cases that used to leave zombie terminals.
- Full-close drill: server + wctray pair terminated cleanly.
- Go path: 12-38x faster scans, 0 content mismatches, guards hold
  (no self, no Brave in kill sets).

## Open gates (need a human at the keyboard)

1. Start a work fresh -> `h` must find its window immediately
   (launch-capture + title + retry all landed since the last test).
2. Stop -> window must vanish entirely.
3. `r` on a headless case -> one-press rebirth.
4. The original `wc.bat` smoke: Space -> `[X]`, Enter kills `[-]`,
   Enter launches stopped (§8 standing gate).
5. `test_wc_core.py` — blocked until no live works are running.

## Known issues (accepted, documented)

- Pre-existing orphans (no tokens, default titles) can't be attributed
  — never auto-touched. One known: invisible `cmd` from the PARK era.
  Say the word and it's closed by HWND.
- wc.py has no respawn sweep (wctray does) — a dev server forking a
  fresh console after minimize leaves it visible.
- WT-manual runs: window actions guarded out, process kill only.
- `registry.json` churns at runtime (launch/hwnd tracking) — normal.
