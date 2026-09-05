# Requirements — standing product constraints

These do not regress. New work must satisfy all of them; if a task seems
to conflict with one, stop and ask instead of working around it.

## UI
- **Inline-tree UI**: one column, `SPACE` indentation for group members.
  Never a two-pane layout.
- `wc` is the entry point users launch (via `wc.bat` / Desktop `wc.lnk`).

## Launch
- Works launch via `.bat` files that open **VISIBLE** windows.
  Never hidden, never backgrounded.
- ONE window per work. The `.bat` itself is the window content
  (inline shape, see `bat-template.md`); `run_work` only hosts it
  via `start ""` (mandatory — without it the child shares wc's console).

## Detection
- Running state is detected **live** from process CommandLine
  (see `architecture.md`), matching the `.bat` basename or an explicit
  `match` token. Must exclude `powershell*` and the launcher's own PID.
- `WINDOWTITLE` / console `title` is unreliable for detection —
  backends clear or replace it (proven live: omniroute-cli window
  titled `''`). Title is window-*lookup* only, never a kill seed.

## Model
- `works.json` groups list members by `id`; a member must NOT also
  appear as a standalone top-level work (no duplication).
- A group has NO state of its own: selected <=> any child selected.

## Works
- GPT is split into **`GPT Web start`** (tunnel client) and
  **`GPT MCP start`** (MCP Inspector), uppercase labels.

## Dependencies
- Plain Python TUIs, stdlib only. `gowc.exe` is our own optional
  accelerator (Go stdlib only) with identical powershell fallbacks —
  never a hard dependency (see `gowc.md`).
