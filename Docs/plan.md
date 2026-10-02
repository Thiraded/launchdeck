# Plan — งานที่เหลือทั้งหมด + ความรู้ที่ session ใหม่ต้องมี

> อัปเดต 2026-10-02: มี UI เดียว คำสั่ง `launchdeck` เปิด Dashboard และยกเลิก
> หน้าจอ terminal เดิมแล้ว เนื้อหา handoff เดิมด้านล่างคงไว้เฉพาะส่วนที่ยังมีผล
> งานที่กำลังรันยังถือพาธ runtime เก่าไว้จนกว่าจะหยุดตามปกติ ดู `Docs/status.md`
> ก่อนย้ายไฟล์ runtime
>
> เขียน 2026-10-01 ตอนจบ session ที่ทำ Phase 0 → Phase 1 (Job Object) + แยก core
> เป้าหมาย: เปิด session ใหม่แล้วอ่านไฟล์นี้ไฟล์เดียว (+ `AGENTS.md`) ก็รู้เท่ากับ
> session เดิม ว่าอะไรทำแล้ว อะไรยังไม่ได้พิสูจน์ อะไรคือกับดัก และต้องทำอะไรต่อ
> ตามลำดับไหน อัปเดตไฟล์นี้ทุกครั้งที่ปิดงานชิ้นใดชิ้นหนึ่ง (ติ๊ก `[x]` + วันที่)

## 0. เริ่ม session ใหม่ให้ทำตามนี้ก่อน

1. อ่าน `AGENTS.md` (index + กฎเหล็ก) → `Docs/status.md` → ไฟล์นี้
2. `git log --oneline -10` ต้องเห็น commit ตามหัวข้อ 3 ถ้ามี commit ใหม่กว่า
   ให้อ่าน diff ก่อนเชื่อไฟล์นี้
3. `git status` ต้อง clean (`works.json`, `registry.json`, `launchdeck_logs/` ถูก gitignore
   เป็นของเครื่อง user ห้าม commit)
4. ถามตัวเองก่อนแตะเครื่องจริงทุกครั้ง: (1) PID/ชื่อ/path ที่โดน (2) เป็นของ user
   ได้ไหม (3) มั่นใจแค่ไหนว่าโดนแค่เป้าหมาย ไม่ชัวร์ = หยุดแล้วถาม
5. รัน test ชุดปลอดภัย (หัวข้อ 10.1) ให้ผ่านก่อนแก้อะไร จะได้รู้ baseline
6. ตอบ user เป็นภาษาไทย กระชับ ไม่ใช้ em dash ไม่ใช้ตัวหนาเยอะ

## 1. โปรเจกต์นี้คืออะไร และ user ต้องการอะไร

- LaunchDeck = ตัวเปิด/ปิด dev server และแอปของ user บน Windows ขับด้วย
  `works.json` (groups + works) repo อยู่ที่ `D:\launchdeck`, remote
  `Thiraded/launchdeck@main`
- มี UI เดียว: คำสั่ง `launchdeck` เรียก `launchdeck.bat` ซึ่งเปิด dashboard
  (`launchdeck_dashboard.py` → `deck/ui/`, รันด้วย pythonw, hotkey Alt+W)
- ทุก work รันแบบ `"run": "detached"` = ไม่มีหน้าต่าง output ลง
  `launchdeck_logs/<id>.log` แล้ว log viewer ใน dashboard tail สีให้
- user: พูดไทย เป็นเจ้าของเครื่อง ใช้งานจริงทุกวัน (work รันค้างอยู่ตลอด)
  ขอให้ review หาจุดผิดออกแบบ แล้วให้ "ทำให้สมบูรณ์และเร็วขึ้นมาก" ให้อำนาจรื้อ
  สถาปัตยกรรมได้ ขอ UI สวยด้วย SVG แทนตัวอักษร และขอแยกไฟล์ลด god class
- ข้อจำกัดถาวร (`Docs/requirements.md`): stdlib only (ห้าม Pillow/pywin32/psutil),
  UI เป็น tree คอลัมน์เดียว ห้ามสองแพน, launchdeck-helper.exe เป็นตัวเร่งแบบ optional เท่านั้น

## 2. กฎที่ห้ามละเมิด (สรุป อ่านตัวเต็มใน Docs)

- **The one rule** (`AGENTS.md`, `Docs/kill-safety.md`): ก่อนคำสั่งใดที่แตะเครื่องจริง
  ต้องเขียน PID/ชื่อ/path, โอกาสเป็นแอป user, ความมั่นใจ ถ้าสงสัยโชว์ kill list ก่อน
- **DOWN ONLY** สำหรับ legacy kill: ไม่เดินขึ้นหา ancestor, protected set = ตัวเรา +
  ancestor ทั้งหมด, `powershell*` ไม่ถูก kill, ไม่ใช้ `/T`, ไม่ใช้ WINDOWTITLE
- **NEVER-seed GUI**: brave, chrome, msedge, firefox, opera, vivaldi, arc, explorer,
  discord, slack, teams (`detect._NEVER_SEED_GUI`) ห้ามเป็นเป้าหมาย kill ทั้ง legacy
  และ job
- **Test policy** (`Docs/verification.md`): ห้ามรัน test ที่ spawn process
  (`test_launchdeck_core.py`) บนเครื่อง user ถ้าไม่ได้รับอนุญาตชัดเจนและไม่มี work รัน
  `test_jobs.py` มีข้อยกเว้นเป็น "PROPOSED" รอ user อนุมัติ (ดูหัวข้อ 8)
- git: commit เมื่อ user ขอ/อนุมัติแผนแล้วเท่านั้น, stage ทีละไฟล์, ไม่ force push,
  ท้าย commit ใส่ `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## 3. ประวัติ session นี้ (commit ตามลำดับ)

| commit | เรื่อง |
|--------|--------|
| `d505de7` | Phase 0: named mutex แทน election (uv-venv twin), atomic registry/manifest + lock, MAX_LAUNCHES→burst 5/60s, guard `find_work_hwnds`, scan_available เป็น thread-local, scan ครั้งเดียวต่อการตัดสินใจ, tray menu async, .bat escape/`cd` guard/chcp, launchdeck-helper 1.1.0 |
| `7f35439` | แยก `launchdeck_dashboard.py` (2,520 บรรทัด) → `deck/ui/*` + ตัว render SVG แบบ stdlib |
| `7357009` | Redesign: ไอคอน SVG ทุกปุ่ม, DPI awareness, ปุ่ม hover-ghost/danger/accent |
| `fe9ee32` | แก้ Start รายตัวพัง (local `state` ชื่อชน module) + ไอคอนของ work จริง |
| `a1b5273` | Phase 1: work ที่ step เป็น terminal ล้วนรันใน Job Object |
| `7ed61b3` | ลบ hide/show/park/sweep + ปุ่ม `h` ก่อนยกเลิกหน้าจอ terminal |
| `c936668` | แยก `launchdeck_core.py` (2,200) → facade 90 บรรทัด + `deck/core/*` |

ของที่แก้นอก git: `works.json` เปลี่ยนแค่ field `icon` (สำรอง
`launchdeck_logs/works.json.bak-icons`) และ memory ที่
`C:\Users\thira\.claude\projects\D--launchdeck\memory\`

## 4. สภาพโค้ดตอนนี้ (แผนที่)

### 4.1 Core (`deck/core/`, facade = `launchdeck_core.py`)

| ไฟล์ | บรรทัด | หน้าที่ |
|------|------:|--------|
| `common.py` | 12 | `HERE` (repo root = `parents[2]`), `_NO_WINDOW` |
| `manifest.py` | 120 | load/save works.json, settings, hotkey parse, slug group |
| `store.py` | 127 | registry.json, `_atomic_write_text`, `_StateMutex` (`Local\launchdeck-state`) |
| `steps.py` | 221 | steps/vars → `launchdeck_logs/launchdeck-gen-<id>.bat`, log path, editor text |
| `ansi.py` | 53 | SGR → (text, color) สำหรับ log viewer |
| `detect.py` | 370 | scan_table (launchdeck-helper หรือ powershell), token, `is_running` (ถาม job ก่อน) |
| `jobs.py` | 274 | Job Object: spawn/members/stop/ctrl_break |
| `kill.py` | 475 | `kill_work`: job ก่อน, ไม่ใช่ job ใช้ legacy 3 pass |
| `windows.py` | 298 | หา/ปิดหน้าต่าง (Alt+F4 pass ของ legacy) |
| `model.py` | 150 | Node/tree + selection state helpers |
| `launch.py` | 195 | `run_work`, `launch_work` (burst cap), `poll_launch` |

กลไก facade: `core.X` อ่าน/เขียนถูกส่งต่อไป module ที่เป็นเจ้าของ `X`
(`_OWNER` สร้างจาก AST ตอน import) `__setattr__` เก็บค่าเดิมเป็น stack ใน
`_PRIOR`, `__delattr__` pop คืน เพราะ `mock.patch` ถือว่าชื่อนั้นไม่ใช่ local
ของ facade เลยคืนค่าด้วย delattr ดังนั้น `mock.patch.object(core, "scan_table")`
ยังไปถึง `kill_work` ได้ ข้อควรรู้:
- `jobs` ไม่อยู่ใน `_OWNER` (ชื่อ generic เช่น `stop`, `spawn`) ใช้ `core.jobs.X`
  หรือ `from deck.core import jobs`
- ชื่อซ้ำข้าม module จะ `ImportError` ตอน import facade (ตั้งใจ)
- default argument ถูกผูกตอน def: `load_manifest(path=MANIFEST)` การ patch
  `core.MANIFEST` ไม่เปลี่ยน default (เป็นแบบนี้มาตั้งแต่ก่อนแยก)
- ใน `deck/core` เรียกข้าม module แบบ qualify เสมอ (`detect.scan_table`) ห้าม
  `from deck.core.detect import scan_table` ไม่งั้น patch ไม่ถึง
- `detect.py`, `model.py` import `manifest as manifest_mod` เพราะ `manifest`
  เป็นชื่อ parameter สาธารณะ

### 4.2 Dashboard (`deck/ui/`, entry = `launchdeck_dashboard.py` 20 บรรทัด)

| ไฟล์ | บรรทัด | หน้าที่ |
|------|------:|--------|
| `main.py` | ~45 | `main()`: `--self-test`, mutex, `dpi.enable()`, WorkTray, monitor thread, Dashboard |
| `app.py` | 531 | `Dashboard` (mixins ด้านล่าง), `_poll` 250ms, `_handle_action`, `_rebuild`, `_place_near_tray` |
| `worklist.py` | 319 | สร้างแถว/อัปเดตแถวในที่ (ไม่ rebuild ทั้งหน้า) |
| `actions.py` | 265 | `_act_run`, `_act_all`, restart, delete, `_act_async` + `_pending` |
| `editors.py` | 479 | task/group/settings editor (popup class เดียวกัน) |
| `logviewer.py` | 113 | tail log 1s, สี ANSI, URL คลิกได้ |
| `tray.py` | 99 | `WorkTray` + เมนูคลิกขวา (Win32 menu ยังใช้ emoji dot) |
| `state.py` | 131 | `log`, `actions` queue, `_running`, `monitor_loop` (3s), `toggle_start_stop` |
| `theme.py` | 78 | palette, `ICON_CHOICES` (17 ชื่อ), `EMOJI_ICON` (emoji เก่า → ชื่อ) |
| `widgets.py` | 223 | `th_button(icon=)`, `th_circle_btn` (Label+image), `icon_label` |
| `icons.py` | 507 | rasterizer SVG pure-python → PNG → `tk.PhotoImage` (cache) |
| `dpi.py` | ~30 | `SetProcessDpiAwareness(1)`, `px()` |
| `viewmodel.py` | 81 | `_row_view`, `_work_to_form` (pure, test ได้) |
| `selftest.py` | 196 | `--self-test` headless |
| `instance.py` | ~40 | mutex `Local\launchdeck-dashboard` |

กฎ UI: import `state`, `theme` เป็น module (`state.log`, `theme.TH_X`) เพราะ
`_apply_palette` rebind ผ่าน `globals()` และ test patch ที่ module
`assets/icons/*.svg` = 33 ไฟล์สไตล์ Lucide (เขียนเองเพราะ network ถูกบล็อก, ISC
LICENSE อยู่ในโฟลเดอร์) ชื่อไอคอนที่ปุ่มใช้: play(fill) stop trash-2 pencil
rotate-cw file-text chevron-down/right/up x settings plus folder-plus zap ...

### 4.3 อื่นๆ

- `launchdeck_tray.py` (1,009): primitive tray/hotkey ด้วย ctypes (reference)
  `register_hotkey` marshal ไป tray thread ด้วย SendMessageTimeout 2s
- `launchdeck-helper/` + `launchdeck-helper.exe` 1.1.0: `scan` (exit 1 เมื่อ snapshot พัง), `kill`
  (`dead`/`denied` แยกกัน)
- `test_*.py`: kill_safety (~33), tray_foundation (~10), ui_smoke (~9),
  jobs (4, opt-in), launchdeck_core (spawn จริง, ห้ามรันถ้าไม่ได้รับอนุญาต)

### 4.4 works.json ของ user (10 works)

| id | steps | job? | หมายเหตุ |
|----|-------|:----:|---------|
| hamster-clint | cd APPDIR && npm run dev (vite :5175) | ใช่ | icon app-window |
| hamster-server | cd && npm run dev (nodemon/tsx) | ใช่ | `D:\HamsterWorld-new-version\server` |
| hamster-server-2 | cd && npm run dev | ใช่ | `D:\HamsterWorld\server` |
| hamsterquest | cd && npm run dev | ใช่ | `D:\Hamsquest` |
| hamstermap | cd && npm run dev | ใช่ | `D:\HammonQuest` (ระวัง Codex worker อ้าง path นี้) |
| mr-unity | app: Unity Hub.exe --projectPath | ไม่ | GUI handoff |
| mr-vscode | app: Code.exe --user-data-dir ... | ไม่ | instance แยกด้วย user-data-dir |
| omniroute-cli | mkdir + `omniroute > %OLOG%` | ใช่ | มี `log` key ของตัวเอง |
| omniroute-web | app: Brave `.lnk` | ไม่ | อันตรายสุดถ้าใส่ job (จับ Brave ทั้งตัว) |
| gpt-mcp | cd && npx inspector ... | ใช่ | อาจเปิดเบราว์เซอร์เข้า job (ถูกกันด้วย never-seed) |

mr-unity, mr-vscode, gpt-mcp ใช้ `D:\Midnight-Rider` ร่วมกัน (legacy kill เคยเสี่ยง
ฆ่าข้าม work ดูหัวข้อ 7 ข้อ B6)

## 5. กับดักที่เจอจริงใน session นี้ (อย่าตกซ้ำ)

1. **local ชื่อชน module → UnboundLocalError** ตอนแยก UI `_act_run` มี local
   `state = "starting"` ทำให้ `state.running_snapshot()` ในฟังก์ชันเดียวกันพัง
   ทุกคลิก (error ถูกกลืน, Start ทีละตัวใช้ไม่ได้ แต่ Start all ใช้ได้เพราะไปอีกทาง)
   ตอนแยก core เจอซ้ำกับ `steps` (run_work) และ `manifest` (หลายฟังก์ชัน)
   กัน: `test_ui_smoke.DashboardSmoke.test_no_local_shadows_a_module` (symtable
   ตรวจ `deck/ui` + `deck/core`) ทุกครั้งที่ย้ายโค้ดหรือเพิ่ม import module ให้รัน
2. **ชื่อ named job ตายเมื่อ handle สุดท้ายปิด** แม้ process ใน job ยังรัน
   → `jobs.spawn` DuplicateHandle ของ job ใส่ไว้ใน root child ชื่อจึงอยู่ตราบที่
   root (cmd.exe ของ .bat) ยังอยู่ ถ้า root ตายก่อนลูก (เช่น .bat จบแต่ node ยังรัน)
   และ deck ปิดไปแล้ว ชื่อจะหาย → ตกไปใช้ legacy detection (ดูงาน J3)
3. **Store Python (WindowsApps) หลุดออกจาก job** ผ่าน package activation
   test จึงใช้ node เป็นลูก ห้ามเขียน test job รอบ `sys.executable`
4. **CTRL_BREAK ส่งไปทั้ง console group** (ทุก process ที่ต่อ console เดียวกัน)
   รวมถึง process ที่เราตั้งใจ "ไม่ kill" ถ้ามันเป็น console app เบราว์เซอร์เป็น GUI
   จึงไม่โดน แต่อย่าคิดว่า never-seed ปลอดภัยจาก CTRL_BREAK ถ้าเป็น console app
5. **subprocess list → cmd quoting พัง** `list2cmdline` ใส่ `\"` ซึ่ง cmd ไม่รู้จัก
   ถ้าจะส่ง `cmd /d /s /c "a && b"` ให้ส่งเป็น string เดียว
6. **ส่ง CTRL_BREAK จาก deck เองไม่ได้** deck เป็น pythonw ไม่มี console และถ้า
   attach console ตัวเองจะรับ event ด้วย → ใช้ helper process (`jobs._SENDER`)
   ที่ FreeConsole/AttachConsole(pid)/SetConsoleCtrlHandler(handler คืน TRUE)/
   GenerateConsoleCtrlEvent(1, group) helper ใช้ `python.exe` ข้าง pythonw
7. **Python 3.12 scope**: list/dict/set comprehension inline (PEP 709) แต่
   generator expression ยังมี scope ของตัวเอง, default arg/lambda default
   ประเมินใน scope นอก ทำให้ symtable scan ต้องจัดการเอง
8. **cp1252 console** print ไทย/emoji พัง ใช้ `PYTHONIOENCODING=utf-8`
9. **test เขียนไฟล์ลง `launchdeck_logs/` จริง** เคยเกิดตอน patch `os.path.abspath` ไม่มีผล
   แล้ว ตอนนี้ test ใช้ `mock.patch.object(core, "HERE", tmp)` ตรวจหลังรัน test
   เสมอว่าไม่มีไฟล์ `zz-*`, `launchdeck-gen-inj/same/th.bat` ค้าง
10. **teardown ลบ log ไม่ได้** เพราะ child ที่เพิ่งถูกฆ่ายังถือ handle → retry loop
11. **Tk บน Windows ไม่มี antialias ใน Canvas polygon** จึงเขียน rasterizer เอง
    (`icons.py`) render ~2.5 ms/ไอคอนแบบ cold, cache ตาม (root, name, size, color)
    ต้อง `icons.clear_cache()` หลัง destroy root (ทำใน `_rebuild` แล้ว)
12. **network ถูกบล็อก** (curl github/unpkg ไม่ได้) ไอคอนเขียนเองทั้งหมด
13. **heredoc ใน bash ที่มี backslash** (`Local\launchdeck`) หลุด escape บ่อย
    แก้ไฟล์ด้วย str_replace หรือสคริปต์ Python ที่ใช้ `chr(92)`
14. **mock.patch กับ facade**: ต้องมี `_PRIOR` stack ไม่งั้นออกจาก patch แล้ว
    ฟังก์ชันจริงหาย (เคยเจอ AttributeError ตอน `__exit__`)
15. **สิ่งที่อย่าไป "แก้"**: omniroute-cli/web ขึ้นว่ารันเพราะ URL แท็บใน Brave
    (cosmetic, ห้ามขยาย token), orphan cmd จากยุค PARK ห้ามแตะอัตโนมัติ

## 6. ตรวจสอบบนเครื่องจริง (ต้องมีคนอยู่หน้าเครื่อง) — ทำก่อนงานใหม่ทั้งหมด

ยังไม่เคยพิสูจน์บนของจริงเลย ต้องให้ user ทำ (หรือทำด้วยกัน) ตามลำดับ:

- [ ] L1 user Quit deck ตัวเก่าจากเมนู tray (ห้ามใช้ Restart ของตัวเก่า: ตัวเก่า
      อาจยังเป็นยุค port-lock ส่วนตัวใหม่ใช้ mutex สองตัวมองไม่เห็นกัน) แล้วเปิด
      `launchdeck.bat` ตรวจ `launchdeck_logs/launchdeck-tray.log` ว่ามี "deck ready"
- [ ] L2 Alt+W เปิด/ปิด dashboard ได้ (ครั้งแรกหลังเปิด DPI awareness)
- [ ] L3 หน้าตา: ที่ 100% แล้วลอง 125/150% (Settings > Display) ไอคอนคม ไม่ล้น
- [ ] L4 Start ทีละตัวจาก dashboard (bug `state` ที่แก้ใน `fe9ee32`) และ Start all
- [ ] L5 **Job แรกของจริง**: Stop hamster-clint ที่รันด้วยวิธีเก่าก่อน (legacy path)
      แล้ว Start ใหม่จาก deck ตัวใหม่ → ตรวจ read-only ว่าอยู่ใน job:
      `python -c "import launchdeck_core as c; print(c.kill_work(c.work_by_id(c.load_manifest(),'hamster-clint'), dry_run=True))"`
      ได้เป็นรายการ PID: ดูชื่อด้วย `jobs._names(pids)` ต้องเป็น cmd + node (npm) + node
      (vite) (+ esbuild) ไม่มีชื่ออื่นแปลก
- [ ] L6 Stop hamster-clint → ควรหยุด < 1 วินาที, port 5175 ว่าง, log มีบรรทัดปิด
      ของ vite (ถ้า graceful) และ `registry.json` ไม่มี key นี้แล้ว
- [ ] L7 Quit deck ขณะ hamster-clint รัน → เปิด deck ใหม่ → แถวยังขึ้น running
      (reopen job ตามชื่อ) → Stop ได้
- [ ] L8 ทำ L5-L6 กับ work ที่ปิดยาก: hamster-server (nodemon + tsx = หลายชั้น),
      omniroute-cli (มี log ของตัวเอง), gpt-mcp (npx, ดูว่าเปิดเบราว์เซอร์ไหม ถ้าเปิด
      และ Brave ยังไม่ได้เปิดอยู่ก่อน ให้เช็คว่า Stop ไม่ปิด Brave)
- [ ] L9 work แบบ app (mr-unity, mr-vscode, omniroute-web) ยังใช้ legacy: Start/Stop
      ได้เหมือนเดิม Stop ของ omniroute-web ต้องไม่ปิด Brave ของ user
- [x] L10 หน้าจอ terminal ถูกยกเลิก 2026-10-02; `launchdeck` เปิด dashboard UI เท่านั้น
- [ ] L11 bump ผลลง `Docs/status.md` (ย้ายจาก "pending live check" เป็น "Verified")

ถ้า L5 ได้รายการ PID ที่มีชื่อแปลก (ไม่ใช่ cmd/conhost/node/esbuild) → หยุด
ห้าม Stop ให้โชว์ user ก่อน

## 7. บัค/จุดอ่อนที่ยังค้าง (จาก review รอบแรก + ที่เจอภายหลัง)

รหัส B = จาก review ต้นฉบับ (12 บัค) สถานะตอนนี้:

| # | เรื่อง | สถานะ |
|---|--------|-------|
| B1 | uv-venv twin / election | แก้แล้ว (mutex) รอ L1 |
| B2 | registry/manifest หาย key | แก้แล้ว (atomic + lock) |
| B3 | MAX_LAUNCHES=16 | แก้แล้ว (burst 5/60s ต่อ work) |
| B4 | find_work_hwnds เดินขึ้นไม่จำกัด | แก้แล้ว (ผ่านได้แค่ cmd.exe) |
| B5 | `_last_scan_ok` race | แก้แล้ว (thread-local) |
| B6 | Stop ช้า, taskkill ไม่ graceful | แก้แล้วสำหรับ job works; legacy ยังช้า (P5) |
| B7 | `is_running` scan ทุกครั้ง | แก้แล้ว (scan เดียวต่อการตัดสินใจ) |
| B8 | tray thread ค้างตอน Start/Stop | แก้แล้ว (queue) |
| B9 | detect หลวม vs kill เข้ม (HammonQuest VSCode, Midnight-Rider ร่วม path) | **ยังไม่แก้** → งาน M1-M3 |
| B10 | .bat เปราะ | แก้บางส่วน (escape, cd guard, chcp, ไม่เขียนทับ) เหลือ: ใช้ .bat ทั้งหมด → P4 |
| B11 | log/poll | **ยังไม่แก้**: viewer `readlines()` ทั้งไฟล์บน Tk thread, `_read_log` อ่านทั้งไฟล์, `_scan_error` จับ "error:" ทั้งไฟล์, STABLE_MAX เป็น dead code → งาน G1-G4 |
| B12 | launchdeck-helper | แก้แล้ว 1.1.0 (ACCESS_DENIED = denied) เหลือ PEB race cmdline ว่าง → R3 |

จุดอ่อนใหม่ที่รู้แล้วแต่ยังไม่ทำ:
- N1 `monitor_loop` ยัง scan process ทั้งเครื่องทุก 3s แม้ทุก work เป็น job
  (scan ใช้ launchdeck-helper ~0.2s หรือ powershell ~0.9s) → J2
- N2 `toggle_start_stop` บังคับ scan สำเร็จก่อน ถ้า scan พังจะกด Stop work ที่อยู่
  ใน job ไม่ได้ ทั้งที่ job ตอบได้เอง → J2
- N4 registry entry ของ work ที่ตายเองไม่ถูกลบ (เช่น hamster-server จาก 09-27) → J5
- N5 `poll_launch`, `registry_running`, `live_running`, `STABLE_MAX_SECONDS`,
  `SETTLED` ไม่มีใครเรียกนอก core แล้ว (ตรวจ grep 2026-10-01) → D1
- N6 เมนูคลิกขวา tray ยังใช้ emoji 🟢/⚪ (Win32 menu ไม่รองรับ image ง่ายๆ) → U3
- N7 `jobs.stop` ส่ง CTRL_BREAK โดยใช้ registry pid เป็น group id ถ้า registry
  ไม่มี pid (work ถูก Start โดย deck อีกตัว) จะใช้ member แรก ซึ่งอาจไม่ใช่ group
  leader → graceful ไม่เกิด แต่ force kill ยังทำงาน → J4
- N8 `jobs._pids` buffer 1024 PID ถ้า job ใหญ่กว่านั้น (ไม่น่าเกิด) จะตัด → J6
- N9 `_PRIOR` ใน facade โตไม่หยุดถ้ามีโค้ด assign `core.X = ...` นอก mock
  (ตอนนี้ไม่มี) → ถ้าเพิ่ม ให้ assign ที่ submodule ตรงๆ
- N10 deck รันใน job ของ terminal ที่มี KILL_ON_JOB_CLOSE (เช่นเปิดจาก VSCode
  terminal หรือ agent harness) → work ที่ nested จะตายตอนปิด terminal นั้น
  ปกติ deck เปิดจาก .lnk/Explorer จึงไม่โดน แต่ควรตรวจ/เตือน → J7

## 8. การตัดสินใจที่รอ user

- Q1 อนุมัติข้อยกเว้น `test_jobs.py` ใน `Docs/verification.md` (ตอนนี้ "PROPOSED")
  ไหม: ให้รันได้แม้มี work รัน เพราะ kill ได้เฉพาะสมาชิก job ใน namespace ของ test
  (session นี้รันไปแล้ว 1 ครั้งโดยยังไม่ได้อนุมัติ ไม่เสียหาย แจ้ง user แล้ว)
  ถ้าอนุมัติ: ลบคำว่า PROPOSED; ถ้าไม่: คงกฎเดิม
- Q2 standing gates เก่า (hide-quality, full-close, console smoke) ใน
  `status.md` ข้อ 3: retire หรือ re-scope (ตอนนี้ hide ถูกลบแล้ว น่าจะ retire)
- Q3 จะทำ supervisor daemon (P2) ไหม หรือพอแค่ job ใน process ของ deck
  (ข้อดี/ข้อเสียในหัวข้อ 9 P2) แนะนำ: ทำ J1-J7 + G ก่อน แล้วค่อยถาม
- Q4 work แบบ app (Unity/VSCode/Brave) จะให้ Stop ทำอะไร: legacy kill ต่อ,
  หรือเปลี่ยนเป็น "external/แสดงอย่างเดียว" (M2) ต้องถามเพราะเปลี่ยนพฤติกรรมที่ user ใช้
- Q5 ให้แยกไฟล์ใหญ่ที่เหลือ (`launchdeck_tray.py` 1,009 บรรทัด) ด้วยไหม
  (เป็น reference primitive, ความเสี่ยงต่ำ ประโยชน์น้อย) แนะนำ: ไม่ต้อง

## 9. Backlog ตามลำดับที่แนะนำ

ลำดับ: L (หัวข้อ 6) → J → G → M → P2 (ถ้า user เอา) → P4 → P5 → U → D
ทุกงาน: อ่านโค้ดก่อน, test ก่อน/หลัง, อัปเดต Docs ที่เกี่ยวข้อง, commit แยกเรื่อง

### J. เก็บงาน Job Object ให้แน่น (เล็ก เสี่ยงต่ำ ทำได้ทันทีหลัง L)

- [ ] J1 **ใช้ IOCP แทน poll ใน `jobs.stop`** ตอนนี้ loop `members()` ทุก 50ms
      (แต่ละรอบ = QueryInformationJobObject + Toolhelp snapshot) ทำ: สร้าง
      IO completion port ต่อ job (`JobObjectAssociateCompletionPortInformation`,
      info class 7) รอ msg 4 `JOB_OBJECT_MSG_ACTIVE_PROCESS_ZERO` ด้วย
      `GetQueuedCompletionStatus(timeout)` spike พิสูจน์แล้ว (ได้ msgs [6,7,4])
      ข้อควรระวัง: port ผูกกับ job ได้ครั้งเดียว ถ้า deck ตัวก่อนผูกไว้แล้วจะ fail
      → fallback เป็น poll ต่อ ห้ามเอา port ไปใช้กับ job ที่เราไม่ได้สร้าง
- [ ] J2 **monitor ไม่ต้อง scan ถ้าไม่จำเป็น** ใน `deck/ui/state.monitor_loop`:
      works ที่ `jobs.eligible` และ `jobs.managed` → running ไม่ต้อง scan
      scan เฉพาะเมื่อมี work ที่ไม่ใช่ job หรือ job ว่าง (อาจรันด้วยมือ) และลดความถี่
      เป็น 10-15s สำหรับส่วน legacy ส่วน job เช็คทุก 1-3s (ถูกมาก)
      แก้ `toggle_start_stop` ให้ถาม job ก่อน scan (N2): ถ้า managed → kill ได้เลย
      ต้องคง guard เดิม: scan พัง = ไม่รู้ ห้ามตีเป็น "ไม่รัน" แล้ว launch ซ้ำ
      test: patch `jobs.managed` + `scan_available=False` แล้ว Stop ต้องไปทาง kill
- [ ] J3 **root ตายก่อนลูก** (กับดัก 5.2) ทางเลือก: (a) deck เก็บ handle ของทุก
      job ที่ตัวเองเปิดไว้ตลอดชีวิต (ทำอยู่แล้วใน `_handles`) ปัญหาเหลือแค่ตอน deck
      ปิด (b) ตอน Quit ให้ DuplicateHandle ใส่ member ที่ยังอยู่ตัวใดตัวหนึ่งอีกครั้ง
      (c) เก็บ `pid + creation time` ของ member ใน registry แล้ว OpenProcess +
      IsProcessInJob(NULL job?) ไม่ได้ช่วย แนะนำ (b): ใน `Dashboard` quit path
      เรียก `jobs.pin_names()` ที่วน `_handles` แล้ว duplicate ใส่ member แรกที่เป็น
      node test: spawn cmd ที่ spawn node detached แล้ว exit, ปิด handle, reopen
- [ ] J4 **group id ของ CTRL_BREAK** (N7) เก็บ `group` (= root pid) ไว้ในชื่อ/
      ข้อมูลที่หาได้จาก job เอง: ใช้ `JobObjectBasicProcessIdList` ลำดับแรกคือ root
      ไม่ได้รับประกัน ทางที่ชัวร์: registry เก็บ `pid` อยู่แล้ว ให้ `kill_work`
      ตรวจว่า pid นั้นยังเป็นสมาชิก job (IsProcessInJob) ก่อนใช้เป็น group ถ้าไม่ใช่
      ให้ใช้ pid เดิมเป็น group id ต่อได้ (group id ยังใช้ได้หลัง leader ตาย
      ตราบใดที่ PID นั้นยังไม่ถูกนำไปใช้ใหม่เป็น group อื่น) และ attach ผ่าน member
- [ ] J5 **registry cleanup** (N4) ตอน monitor เห็น job ว่าง/ไม่มี process ของ
      registry pid (OpenProcess ไม่ได้ หรือ creation time ไม่ตรง) ให้ unregister
      ต้องเก็บ creation time ตอน register ก่อน (GetProcessTimes) เพื่อกัน PID reuse
- [ ] J6 `_pids` ใช้ buffer ขยายอัตโนมัติ: ถ้า `assigned > listed` ให้จองใหม่
- [ ] J7 **nested job warning** (N10) ตอน deck เริ่ม เรียก
      `IsProcessInJob(GetCurrentProcess(), NULL)` ถ้าอยู่ใน job ให้ query
      `JobObjectExtendedLimitInformation` ของ job ตัวเองไม่ได้ (ไม่มี handle) →
      ง่ายสุด: log เตือน + โชว์ใน status line "deck รันใต้ job ของ terminal: work
      อาจตายเมื่อปิด terminal" ทางแก้จริง: spawn work ด้วย
      `CREATE_BREAKAWAY_FROM_JOB` (ได้ถ้า job แม่อนุญาต BREAKAWAY_OK) ลองก่อน
      ถ้า fail ค่อยไม่ใส่ flag
- [ ] J8 เพิ่ม test ที่ spawn จริงใน `test_jobs.py`: J1 (IOCP), J3 (root exit),
      restart path (`_do_restart` = kill + launch ใหม่อยู่ job ชื่อเดิม)

### G. Log และ viewer (เร็วขึ้นที่ user เห็นชัด)

- [ ] G1 `deck/ui/logviewer.py:74` `f.readlines()[-150:]` อ่านทั้งไฟล์บน Tk thread
      → อ่านจากท้ายไฟล์ทีละ block (seek จาก end ย้อน 64KB จนได้ 150 บรรทัด)
- [ ] G2 follow loop 1s ใช้ `seek(pos)` อยู่แล้ว ตรวจว่าจัดการ log ถูก truncate
      (Start ใหม่ = ไฟล์ใหม่) ถ้า size < pos ให้ reload
- [ ] G3 `launch._read_log` / `_scan_error` อ่านทั้งไฟล์และจับ "error:" ที่ไหนก็ได้
      ใช้กับ `poll_launch` ซึ่งไม่มีใครเรียก (N5) → ถ้าไม่ใช้ ลบทิ้งพร้อม D1 ถ้าจะใช้
      สถานะ ready/failed ในแถว ให้อ่านเฉพาะส่วนหลัง marker `[deck] launch`
- [ ] G4 log rotate: `run_work` เปิด `"w"` ทุก Start (truncate) ถ้า instance เก่า
      ยังเขียนอยู่ไฟล์จะปนกัน เมื่อ job ช่วยยืนยันว่า instance เก่าตายแล้ว ปัญหาลดลง
      พิจารณาเก็บ `<id>.prev.log` 1 รุ่นไว้ดูย้อนหลัง
- [ ] G5 (ใหญ่ ไปกับ P3) ต่อ pipe แทนไฟล์ + ring buffer ในหน่วยความจำ

### M. Managed vs external (แก้ B9 ที่ต้นเหตุ)

ปัญหา: detection ใช้ token หลวม (เปิด VSCode ที่ `D:\HammonQuest` = hamstermap
ขึ้น running) แต่ kill เข้ม (ไม่ยอมฆ่า) → ค้าง "STOP BLOCKED (no safe target)"
และกด Start ไม่ได้เพราะเข้าใจว่ารันอยู่แล้ว

- [ ] M1 แยกสถานะ 3 แบบใน core: `managed` (มี job ของเรา), `external` (token
      match แต่ไม่มี job), `stopped` ให้ `detect.run_state(work, cls) -> str`
      ส่วน `is_running` คงไว้ (= managed or external) เพื่อไม่ให้ core checks พัง
- [ ] M2 UI: แถว external แสดงจุดสีอื่น (เช่นเหลือง/ขอบ) + ข้อความ "running
      (outside deck)" ปุ่มหลักเปลี่ยนเป็น "Stop…" ที่เปิด dialog โชว์ `dry_run`
      PID + ชื่อ + cmdline ก่อน kill (ตาม kill-safety ข้อ 4) และมีปุ่ม "Start anyway"
      (ต้องถาม user เรื่องนี้ = Q4) viewmodel `_row_view` เพิ่ม key `ext`
- [ ] M3 เกณฑ์ detection สำหรับ work ที่เป็น job ได้: ถ้า eligible แต่ไม่มี job
      ให้ใช้ token เข้มแบบ kill (`_primary_path_identity_matches`) แทน token หลวม
      → VSCode ที่เปิดโฟลเดอร์เดียวกันจะไม่ถูกนับ ต้องมี test จาก table จำลอง:
      `Code.exe D:\HammonQuest` ต้องไม่ทำให้ hamstermap running
- [ ] M4 Midnight-Rider ร่วม path (mr-unity, mr-vscode, gpt-mcp): หลัง M3 ให้
      ตรวจด้วย dry_run บนตารางจำลองว่า Stop ตัวหนึ่งไม่ดึง process ของอีกตัว
      gpt-mcp เป็น job แล้ว จึงเหลือ unity/vscode ที่ legacy

### P2. Supervisor daemon + IPC (ใหญ่ ต้องถาม user ก่อน = Q3)

แนวคิดจาก review: ให้มีเจ้าของ state คนเดียว (`launchdeckd`) และให้ dashboard
เป็น client บาง ไม่ scan เอง

```
launchdeckd (pythonw, mutex = ตัวเดียว)
 ├─ WorkSupervisor ต่อ work: job + IOCP, starting/running/stopping/exited
 ├─ Launcher (jobs.spawn)
 ├─ LogPump: pipe -> ไฟล์ + ring buffer -> push ให้ client
 ├─ State: in-memory + persist atomic (pid + creation time)
 └─ IPC: multiprocessing.connection บน \\.\pipe\launchdeck (authkey)
```

- ข้อดี: dashboard เห็นสถานะจากเจ้าของ state เดียว, ไม่ scan ซ้ำ, event แทน poll
- ข้อเสีย: เพิ่ม process + protocol, ต้อง upgrade path (deck เก่า/ใหม่), ต้อง
  ป้องกัน IPC: pipe name ใน `Local`/session เดียว + authkey สุ่มเก็บใน
  `%LOCALAPPDATA%` (อ่านได้เฉพาะ user) ห้ามเปิด TCP
- ทางเลือกที่ถูกกว่า (แนะนำให้เสนอ user ก่อน): ให้ dashboard เป็น supervisor เลย
  (ทำได้อยู่แล้วเพราะ job มีชื่อ) = ได้ 80% โดยไม่ต้อง IPC
- ขั้นถ้าทำ: P2.1 spike IPC (echo server/client, authkey, reconnect)
  P2.2 ย้าย `monitor_loop` + launch/kill ไปอยู่ใน supervisor object ใน process deck
  (ยังไม่แยก process) P2.3 เปิด pipe server P2.4 dashboard subscribe event
  แทน poll 3s

### P3. LogPump

- [ ] P3.1 ใน `jobs.spawn` ส่ง `stdout=PIPE` แล้ว thread อ่าน → เขียนไฟล์ + ring
      buffer (เช่น 2,000 บรรทัด) ข้อเสีย: ถ้า deck ตาย pipe ปิด → work อาจได้
      SIGPIPE/EPIPE และตาย (node เขียน stdout แล้ว error) **นี่คือเหตุผลที่ยังใช้ไฟล์**
      ต้องแก้ด้วย daemon (P2) ที่อยู่ยาว หรือคงไฟล์ไว้ ห้ามทำ P3 ก่อน P2
- [ ] P3.2 viewer อ่านจาก buffer (ไม่แตะดิสก์)

### P4. เลิกใช้ `.bat` ที่ generate

- ตอนนี้: `steps.materialize_steps` เขียน `launchdeck_logs/launchdeck-gen-<id>.bat` แล้ว
  `cmd.exe /c <bat>` กับดักที่รู้: setlocal+npm goto (ห้ามใส่ setlocal), codepage,
  เขียนทับไฟล์ระหว่างรัน (แก้แล้วด้วยการไม่เขียนถ้าเหมือนเดิม), injection ทาง title
- เป้าหมาย: `CreateProcess` ตรง cwd = ค่าจาก step `cd` แรก, env = `vars` ที่ expand
  แล้ว, terminal steps ที่เหลือรวมเป็น `cmd /d /s /c "a && b"` (string เดียว กับดัก 5.5)
- [ ] P4.1 ฟังก์ชัน pure `steps.plan_launch(work) -> (cwd, env, cmdline)` + test
      ครอบทุก work ใน works.json (เทียบผลกับ .bat เดิมด้วยตา + test ตาราง)
      ระวัง: step `mkdir ... 2>nul` ต้องใช้ `&` ไม่ใช่ `&&` (ตั้งใจให้ fail ได้)
      = คงความหมายเดิม: เฉพาะ `cd` ที่ guard ด้วย `||` ขั้นอื่นต่อกันด้วย `&`
- [ ] P4.2 identity token: legacy detection ใช้ชื่อ `launchdeck-gen-<id>.bat` เป็น
      runner token (`detect._runner_identity`, `kill_tokens_for`) ถ้าเลิก .bat ต้อง
      มี marker อื่น เช่น env var `LAUNCHDECK_WORK=<id>` (ไม่เห็นใน cmdline) หรือ
      `title` ใน cmdline job แก้ได้หมดแล้วสำหรับ work ที่เป็น job จึงทำ P4 เฉพาะ
      work ที่ eligible ก่อน
- [ ] P4.3 เก็บ .bat สำหรับ app steps (start "" ...) ไว้ก่อน หรือเปลี่ยนเป็น
      `os.startfile`/ShellExecute ใน deck ตรงๆ
- [x] P4.4 ย้าย runner เก่า 13 ไฟล์ไป `launchdeck_logs/archive/` โดยเก็บเนื้อหาไว้
      และเปลี่ยนชื่อเป็น `legacy-runner-<id>.bat` แล้ว 2026-10-02

### P5. ลด legacy (หลังทุก work ที่เป็น terminal อยู่ใน job และ L ผ่านแล้ว)

- [ ] P5.1 วัดก่อน: หลังใช้งานจริง 1-2 สัปดาห์ ดู `launchdeck_logs` deck log ว่ามี Stop
      ผ่าน legacy กี่ครั้งและเป็น work ไหน (เพิ่ม log บรรทัด "stop via job/legacy")
- [ ] P5.2 legacy 3 pass (`kill.kill_work` ส่วนล่าง ~300 บรรทัด) ยังจำเป็นสำหรับ
      app works (Q4) และ work ที่รันเองนอก deck ห้ามลบจนกว่า Q4 จะได้คำตอบ
- [ ] P5.3 ถ้า Q4 = "external แสดงอย่างเดียว + kill ต้องยืนยัน" → ย่อ legacy ให้
      เหลือ: dry_run → dialog → per-PID TerminateProcess (ctypes) ตัด taskkill
      graceful pass + sleep 2.5 + WM_CLOSE pass ออก แล้ว `windows.py` ส่วนใหญ่ลบได้
- [ ] P5.4 launchdeck-helper: ถ้า scan เหลือแค่สำหรับ external (10-15s) และ kill ใช้ ctypes →
      เขียน `CreateToolhelp32Snapshot` + อ่าน cmdline ด้วย
      `NtQueryInformationProcess(ProcessCommandLineInformation=60)` ใน Python
      แล้ว launchdeck-helper เป็นแค่ optional ต่อไป หรือเลิกใช้ (ต้องถาม user เพราะเขาสร้างไว้เอง)
- [ ] P5.5 อัปเดต `Docs/kill-safety.md` ให้ legacy เป็นหัวข้อรอง

### R. ความถูกต้องเล็กๆ ที่เหลือ

- [ ] R1 `launch_work` burst cap นับเฉพาะใน process เดียว (dashboard เป็น UI เดียว)
      10/นาที ยอมรับได้ (บันทึกไว้) ไม่ต้องแก้ถ้าไม่ทำ P2
- [ ] R2 `_StateMutex` timeout 5s แล้วทำต่อโดยไม่มี mutex (เงียบ) ควร log
- [ ] R3 launchdeck-helper PEB race (cmdline ว่างตอน process เพิ่งเกิด) ทำให้สถานะกระพริบหลัง
      Start สำหรับ job works ไม่มีผลแล้ว (ไม่ใช้ cmdline) เหลือ legacy
- [ ] R4 `steps._cmd_escape` ใช้กับ title เท่านั้น ตรวจว่า `vars` ที่มี `"` หรือ `%`
      ไม่ทำ `set "K=V"` พัง (มี test escape label แล้ว ยังไม่มีของ vars)
- [ ] R5 editor: ตรวจ id ซ้ำ/ว่าง, hotkey ชนกันแจ้งแล้ว (มี `hotkey_conflicts`)

### U. UI ที่เหลือ

- [ ] U1 ตรวจ 125/150% (L3) ถ้าล้น: font Tk scale อัตโนมัติ แต่ `dpi.px()` ใช้กับ
      geometry/ไอคอน ต้องแน่ใจว่าทุกขนาดคงที่ผ่าน `dpi.px`
      (`grep -n "width=\|height=\|padx=\|pady=" deck/ui/*.py`)
- [ ] U2 status pill ในแถว: running / starting… / stopping… / external (M2) / failed
- [ ] U3 เมนูคลิกขวา tray: emoji 🟢⚪ (N6) ทางเลือก: `SetMenuItemBitmaps` ด้วย
      HBITMAP ที่สร้างจาก `icons.compose()` (RGBA → DIB section 32bpp) ทำได้ด้วย ctypes
      หรือเปลี่ยนเป็นข้อความ "● running" ธรรมดา แนะนำแบบหลัง (ง่าย เสี่ยงน้อย)
- [ ] U4 ปุ่ม row บาง (trash/pencil/restart/log) โผล่เฉพาะ hover (เคยเสนอ ยังไม่ทำ
      ตอนนี้แสดงเป็น ghost ตลอด) ต้องดูว่า Tk hover ทั้งแถวไม่กระพริบ
- [ ] U5 ไอคอนเพิ่มตามที่ user ขอ: เพิ่ม svg ใน `assets/icons/` (viewBox 24,
      stroke 2, round caps) + ใส่ชื่อใน `theme.ICON_CHOICES` + `IconRenderer` test
      จะตรวจว่าทุกไฟล์ render มีหมึก
- [ ] U6 contact sheet สำหรับดูไอคอนทั้งหมด (เคยทำแบบชั่วคราวแล้วลบ) ทำเป็น
      `python -m deck.ui.icons --sheet out.png` ถ้า user อยากดู

### D. ลบของตาย + เอกสาร

- [ ] D1 ลบ `poll_launch`, `SETTLED`, `STABLE_MAX_SECONDS`, `GRACE_SECONDS`,
      `_read_log`, `_scan_error`, `ERROR_KEYWORDS`, `registry_running`,
      `live_running` ถ้า grep ยืนยันว่าไม่มีคนใช้ (รวม `test_launchdeck_core.py`
      ที่รันไม่ได้ อ่านด้วยตา) ระวัง facade: ชื่อหายจาก `_OWNER` อัตโนมัติ
- [ ] D2 `status.md` เขียนใหม่ให้สั้น (มีของยุคก่อน detached ปนเยอะ) ย้ายของเก่า
      ไป `history.md`
- [ ] D3 `tray.md` 228 บรรทัด ตัด PARK trial / hide ไป `history.md`
- [ ] D4 `README.md` ตรวจ layout + ตัวอย่าง works.json ให้ตรงกับ `deck/`
- [ ] D5 `spec-fix-tray-hide-foundation.md` ที่ root = ประวัติของ hide ที่ลบแล้ว
      ตาม AGENTS.md "spec-*.md history stays at root" จึงคงไว้ แค่เพิ่มหัวว่า superseded
- [ ] D6 `test_launchdeck_core.py` ยังอ้าง API เก่าหรือไม่ (hide?) อ่านด้วยตาและ
      `python -m py_compile` เท่านั้น ห้ามรัน

## 10. วิธีทดสอบ (ทำแบบนี้ทุกครั้ง)

### 10.1 ชุดปลอดภัย (รันได้เสมอ ไม่ spawn process)

สร้าง guard ไว้ใน `%TEMP%` (ไม่ใช่ใน repo) แล้วรัน 3 ไฟล์ผ่านมัน
guard บล็อก `subprocess.Popen/run` + `os.kill` ถ้า test ไหนหลุดไปเรียกของจริงจะ fail:

```python
# %TEMP%\ld_guard.py
import os, subprocess, sys, unittest
from unittest import mock  # import asyncio ก่อน patch (asyncio subclass Popen)
class _Blocked(subprocess.Popen):
    def __init__(self, *a, **k): raise AssertionError(f"BLOCKED Popen: {a[:1]}")
def _blocked(*a, **k): raise AssertionError(f"BLOCKED process call: {a[:1]}")
subprocess.Popen = _Blocked; subprocess.run = _blocked; os.kill = _blocked
sys.path.insert(0, os.getcwd())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
r = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if r.wasSuccessful() else 1)
```

```
cd /d D:\launchdeck
python %TEMP%\ld_guard.py test_kill_safety test_tray_foundation test_ui_smoke
```

baseline 2026-10-01: 51 tests OK (ลดจาก 56 เพราะลบ test ของ hide)
ทุก test module ตั้ง `_jobs.PREFIX = "Local\\launchdeck-test-<pid>-"` บรรทัดบน
ห้ามลบ (กัน test ไปเปิด job จริงของ user)

### 10.2 self-test ของ dashboard (headless)

รัน `self_test()` ใต้การบล็อกแบบเดียวกัน (สร้าง Tk แบบ withdrawn, scan ถูกบล็อก
แล้ว fallback) ต้องได้ `SELF-TEST OK` และคืน 0:

```python
# %TEMP%\ld_selftest.py  (รันจาก D:\launchdeck)
import os, subprocess, sys
from unittest import mock
class _B(subprocess.Popen):
    def __init__(self, *a, **k): raise AssertionError("BLOCKED")
subprocess.Popen = _B
subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("BLOCKED run"))
sys.path.insert(0, os.getcwd())
from deck.ui.selftest import self_test
print("self_test ->", self_test())
```

ห้ามรัน `launchdeck_dashboard.py --self-test` ตรงๆ ถ้าไม่แน่ใจ เพราะไม่มี guard
(มัน scan จริง แต่ไม่ launch/kill; อ่านอย่างเดียว)

### 10.3 test ที่ spawn จริง

- `test_jobs.py`: `set LAUNCHDECK_SPAWN_TESTS=1 && python -W ignore -m unittest test_jobs`
  ต้องมี node ติดตั้ง, 4 tests ใช้เวลา ~2s สถานะนโยบาย: ดู Q1 ก่อนรันทุกครั้ง
  หลังรันตรวจว่าไม่มี node ของ test ค้าง (read-only):
  `powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | ? { $_.CommandLine -match 'setInterval|grace.js|tree.js' }"`
  และไม่มี `launchdeck_logs\zz-jobtest-*`
- `test_launchdeck_core.py`: ห้ามรันถ้า user ไม่อนุญาตชัดเจน + ไม่มี work รัน

### 10.4 ตรวจหน้าตา (ไม่แตะหน้าจอ user)

วิธีที่ใช้ใน session นี้: สคริปต์สร้าง `Dashboard` บน manifest จริง/ปลอม โดย mock
`core.scan_commandlines`, `scan_available`, `launch_work`, `kill_work`,
`save_manifest` แล้วถ่ายด้วย `PrintWindow(hwnd, hdc, 2)` เฉพาะหน้าต่าง deck
(ไม่ใช่ทั้งจอ) เซฟ PNG ด้วย `icons._encode_png` แล้วเปิดดู ลบไฟล์ชั่วคราวหลังดู
ทำทั้ง dark/light และ compact/roomy

### 10.5 เทียบพฤติกรรมก่อน/หลัง refactor

รูปแบบที่ใช้ตอนแยก core: copy ไฟล์เก่าจาก `git show <rev>:launchdeck_core.py`
ไว้ใน `%TEMP%` โหลดด้วย `importlib.util.spec_from_file_location` แล้วเทียบ
`titles_for`, `kill_tokens_for`, `work_vars`, `gen_bat_name`, `materialize_steps`
(ใน temp dir), `is_running` บน cmdline จำลอง, hotkey, `build_model`, `ansi_runs`
บนทุก work ของ `works.json` (อ่านอย่างเดียว) ผลต้อง diff = 0
ข้อควรระวัง: ไฟล์เก่าคำนวณ `HERE` จากตำแหน่งตัวเอง ให้ส่ง path manifest เข้าไปตรงๆ

### 10.6 ตรวจชื่อชน module ทุกครั้งที่ย้ายโค้ด

`python -m unittest test_ui_smoke.DashboardSmoke.test_no_local_shadows_a_module`

## 11. คำสั่งดูสถานะแบบอ่านอย่างเดียว (ปลอดภัยบนเครื่อง user)

```
:: สมาชิก job ของ work (ไม่ kill) -- ว่าง = ไม่มี job / ไม่ได้รันผ่าน job
python -c "import launchdeck_core as c; from deck.core import jobs; m=c.load_manifest(); [print(w['id'], jobs.eligible(w), jobs.members(w['id'], c._NEVER_SEED_GUI)) for w in m['works']]"

:: รายการที่ kill_work จะฆ่า (dry run, ไม่ kill)
python -c "import launchdeck_core as c; w=c.work_by_id(c.load_manifest(),'hamster-clint'); print(c.kill_work(w, dry_run=True))"

:: registry ปัจจุบัน
type registry.json

:: log ของ deck เอง
type launchdeck_logs\launchdeck-tray.log   (deck.ui.state.LOG)
```

กฎ: `dry_run=True` เท่านั้นระหว่างสำรวจ, ห้าม `kill_work(w)` จริงนอกจาก user สั่ง
และได้โชว์รายการแล้ว

## 12. Job Object API ที่ใช้ (อ้างอิงเร็ว, ctypes, kernel32)

| เรียก | ใช้ทำ | หมายเหตุ |
|-------|-------|---------|
| `CreateJobObjectW(NULL, name)` | สร้าง/เปิด (ALREADY_EXISTS ก็ได้ handle) | name = `Local\launchdeck-job-<safe id>` |
| `OpenJobObjectW(0x1F001F, 0, name)` | เปิดของ deck ตัวก่อน | NULL = ไม่มี job |
| `Popen(creationflags=SUSPENDED\|NEW_PROCESS_GROUP\|NO_WINDOW)` | เกิดแบบหยุดไว้ | 0x4, 0x200, 0x08000000 |
| `AssignProcessToJobObject(job, proc)` | เข้า job ก่อนรันคำสั่งแรก | fail → TerminateProcess ลูก + OSError → fallback Popen ธรรมดา |
| `DuplicateHandle(self, job, child, ..., SAME_ACCESS)` | ฝังชื่อ job ไว้ใน root | กับดัก 5.2 |
| Toolhelp thread walk + `ResumeThread` | resume (Popen ไม่ให้ thread handle) | `_resume` |
| `QueryInformationJobObject(job, 3, ...)` | รายชื่อ PID | BasicProcessIdList, buffer 1024 |
| `IsProcessInJob(proc, job, &b)` | เช็คก่อน TerminateProcess | กัน PID reuse |
| `SetInformationJobObject(job, 7, port)` | IOCP (ยังไม่ใช้ = J1) | msg 4 = ACTIVE_PROCESS_ZERO |
| helper `GenerateConsoleCtrlEvent(1, group)` | CTRL_BREAK graceful | group = root pid |

ห้ามตั้ง `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (0x2000) กับ job ของ work
(spike T7 พิสูจน์ว่าปิด handle แล้วฆ่าลูกทันที = deck ปิด work ตาย)

ผล spike (2026-09-30, process ทดสอบของตัวเองเท่านั้น):
T1 tree 2 PID kill ~0ms / T2 IOCP msgs [6,7,4] / T3 python SIGBREAK 206ms
(ต้อง sleep สั้นๆ วน ไม่ใช่ sleep(120) เดียว) / T4 node 107ms /
T5 `cmd /c "cd && node"` 152ms members=3 (cmd, node, conhost) /
T6 reopen by name หลังผู้สร้างตาย ได้เมื่อ duplicate handle ใส่ลูก /
T7 KILL_ON_JOB_CLOSE ฆ่าจริง

## 13. Definition of done ของแต่ละงาน

1. โค้ดตามสไตล์เดิม (คอมเมนต์อธิบาย "ทำไม", ไม่ใช้ `from x import name` ข้าม
   module ใน deck/core, import `state`/`theme` เป็น module ใน deck/ui)
2. ชุด 10.1 ผ่าน + 10.6 ผ่าน + self-test ผ่าน
3. งานที่แตะ job/launch/kill: `test_jobs` (ตามนโยบาย Q1) + test ตารางจำลองใหม่
4. งานที่แตะ UI: ภาพ PrintWindow dark/light ดูด้วยตา
5. Docs: อัปเดตไฟล์ที่เป็นเจ้าของเรื่อง (`kill-safety.md`, `architecture.md`,
   `tray.md`, `status.md`) + ติ๊กไฟล์นี้
6. ไม่มีไฟล์ขยะใน repo/`launchdeck_logs` (`git status` clean ยกเว้นที่ตั้งใจ)
7. commit แยกเรื่อง ข้อความบอกเหตุผล + วิธีพิสูจน์ ท้ายด้วย Co-Authored-By
8. รายงาน user เป็นไทย: ผลก่อน, สิ่งที่ยังไม่ได้พิสูจน์บนเครื่องจริงบอกตรงๆ

## 14. สิ่งที่ห้ามทำ (สรุปสั้น)

- ห้าม kill/Stop work จริงของ user เพื่อ "ลองดู" โดยไม่ถาม
- ห้ามใส่ job ให้ work ที่มี `app` step (Brave/Unity/VSCode) โดยไม่มีวิธีกันแอป user
- ห้ามขยาย detection token ให้หลวมขึ้นเพื่อแก้สถานะ
- ห้ามเพิ่ม dependency นอก stdlib
- ห้ามทำ UI สองแพน
- ห้าม commit `works.json`, `registry.json`, `launchdeck_logs/`
- ห้ามแก้ `works.json` โดยไม่สำรองก่อน และแก้เฉพาะ field ที่ user ขอ
- ไฟล์ใน `launchdeck_logs/archive/` เป็นข้อมูลเครื่อง user ให้เก็บไว้
- ห้าม resurrect `kc` หรือระบบ hide









