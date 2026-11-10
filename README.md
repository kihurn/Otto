# Otto: Phase 1

Otto is your desktop assistant. You type or talk; **Laya** decides what you want in a fraction of a
second; plain Python code does it; the **brain** (Gemma 4 in the cloud, Qwen on your PC through
C0RE) only steps in when something needs understanding, writing or looking at. When Otto isn't
sure, it asks you. When you confirm, it learns.

The full design is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**This phase is a test.** At the end we check the pass marks (section 9) and decide whether Otto
keeps growing into a desktop agent, or narrows to a CRM assistant.

---

## 1. Put the files in place

1. Paste everything from the zip into `C:\Users\User\OneDrive\Documents\Otto`.
2. Delete the old **top-level** `ARCHITECTURE.md` and `architecture.svg`. They now live in `docs\`.
3. If you haven't yet, delete `otto-phase0\.venv` (several GB that OneDrive would upload).

Otto's private Python goes **outside** OneDrive, in `C:\Users\User\.otto\venv`. Downloaded models go to
`C:\Users\User\.cache`. Neither is synced. Your own data (`otto-data\`) stays in the project, so OneDrive backs it up.

## 2. Keys (you did this in Phase 0)

Otto reads its keys from Windows environment variables, never from files:
- `OTTO_C0RE_KEY` (needed). The C0RE key must allow `gemma4:31b-cloud`, `qwen3-vl:8b-instruct` and `qwen3-vl:4b-instruct`.
- `OLLAMA_API_KEY` (optional, for up-to-date answers via web search).

Check in a new PowerShell window:
```powershell
if ($env:OTTO_C0RE_KEY) { "C0RE key is set" } else { "C0RE key is NOT set" }
```
If it's not set, see `otto-phase0\README.md`, step 3.

## 3. Install

In PowerShell, in the Otto folder:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
This takes about 10–15 minutes and downloads about 6 GB. It ends with `GPU visible: True`.

**Everything (for file search):**
1. Install **Everything** from https://www.voidtools.com/downloads/ and let it index.
2. On the same page, download **"Command-line interface"** (ES, a small zip). Put `es.exe` in `C:\Program Files\Everything\`
   (next to Everything.exe) or in Otto's `tools\` folder.

## 4. Check the test set (about 10 minutes, do this once)

Laya's exam is 100 requests I wrote in your style (`otto-data\test_set.csv`). They're **never taught**, so
the score stays honest, and they decide how sure Laya must be before Otto acts alone. Check my labels:
```powershell
.\tool.cmd label_tests
```
For each request: **Enter** if the area is right, or type the right number. Add your own with **+**.

## 5. Use Otto

```powershell
.\otto.cmd            # type to Otto
.\otto.cmd --speak    # type, and Otto answers out loud
.\otto.cmd --voice    # talk to Otto, and it answers out loud
.\otto.cmd --dry-run  # Otto says what it WOULD do, without doing it (good for a first try)
```
The first start teaches Laya all the examples and takes its test (about 20–30 seconds). After that it starts quickly.

**Things to try:**
```text
open spotify and search lofi       pause            volume 30          skip
open youtube                       google best gaming mouse            take me to github
find my resume                     open my downloads                   open the latest screenshot
write down call the bank tomorrow  write a short poem in notepad       add bread to my note
set a timer for 10 minutes         remind me in 15 minutes to check the food     how long left
what's 15 percent of 80            who won the last world cup          what's the time
what's on my screen                what does this error mean           what's in my clipboard
close discord   (asks first)       search for taylor swift in discord  (Otto works it out, then: "save that")
```

**The grey line under each reply** shows how Otto decided, e.g.
`laya: apps 94% -> high (58 ms) | search_in_app {...} [rules] | plan: builtin`
- `high` = Laya was sure, so Otto acted. `middle` = Otto asked you. `low` = the brain guessed, then Otto asked you.
- `[rules]` = the details came from simple rules (instant). `[brain:...]` = a model filled them in.
- `plan: builtin / recipe / brain:...` = done the built-in way, from a saved recipe, or a new plan from the brain.

Type `:details` to hide it, and `:help` for all commands.

## 6. Teaching Otto

- **When it asks** ("Open VALORANT?"), answer **yes / yeah / nah / no**, or just say what you meant.
  Every yes becomes a teaching example. If you rephrase ("otto, valorant" → "can you open valorant"), it learns that too.
- **"save that"** after something worked:
  - if the brain had to work out *how* (e.g. searching inside Discord), Otto saves the steps as a **recipe**
    and next time does it instantly, with no brain;
  - otherwise it saves the request as a teaching example.
- **"forget that"** undoes the last thing it learned (it asks first).
- Laya relearns every **20 new examples**, and only keeps the new version if it scores at least as well on the test.
- Faster teaching, without doing anything: `.\tool.cmd try_laya` (like the Phase 0 tool, now using Otto's real data).
- `.\tool.cmd score` shows the test score, the confidence zones and Laya's mistakes.

## 7. Voice

- `.\tool.cmd voice_test` plays **Bella** and **Michael**. To switch, open `otto-data\settings.json` and set
  `"voice": "am_michael"` (or `"af_bella"`), then restart Otto.
- In `--voice` mode Otto ignores the mic while it's speaking, so it doesn't hear itself. Headphones help.
- If Whisper isn't sure what it heard, Otto asks *"did you say …?"*.

## 8. Safety

| Kind | Examples | What Otto does |
|---|---|---|
| read | find files, read the screen, the time | just does it |
| undoable | open/switch apps, media, websites, notes, timers | does it and tells you |
| ask first | close apps, open programs (.exe etc.), click Send/Buy/Pay/Delete-type buttons | asks, waits for yes |

The check happens in Otto's core, so nothing can skip it. Otto never types into password boxes. Text it
reads on screen is treated as information, never as instructions. **Ctrl+C** stops Otto at any time.

## 9. What to send Claude after a few days

1. The output of `.\tool.cmd score`.
2. Your log files from `otto-data\logs\` (one per day; they contain your requests and Otto's decisions, but no keys).
3. Anything that felt wrong, slow or annoying.

**Phase 1 pass marks:**
- when Otto acts without asking, it's right **≥ 95%** of the time
- **≥ 90%** of requests end up handled correctly
- recipes work **≥ 95%** of the time
- a simple typed command finishes in **< 1 s**, spoken in **< 2.5 s**

## 10. Settings (`otto-data\settings.json`)

| Setting | What it does |
|---|---|
| `brains` | Which models do which job, in fallback order |
| `zones.act_bar` / `guess_bar` | Starting confidence bars. Replaced by ones measured on the test set (`use_measured`), but never below `act_bar_floor` (0.70), and the "ask you" zone is always at least `ask_zone_min` (0.20) wide |
| `whisper.misheard_below` | How unsure Whisper must be before Otto asks "did you say…?" (more negative = asks less) |
| `whisper.mic_device` | Microphone number, if the default is wrong (`otto-phase0` `check_live.py --list-devices` lists them) |
| `voice_out.voice` | `af_bella` or `am_michael` |
| `everything_es_path` | Where es.exe is, if it's somewhere unusual |
| `show_details` | The grey line under each reply |

Pasting a newer Otto never overwrites `otto-data\`. New settings appear automatically.

## 11. Troubleshooting

| You see | What to do |
|---|---|
| `py -3.12` not found | `winget install -e --id Python.Python.3.12`, then open a new PowerShell window |
| `GPU visible: False` | Update the NVIDIA driver, restart, run setup again |
| "isn't installed, as far as I can see" for an app you have | Wait a minute after starting (the app list refreshes in the background), or type `:reload` |
| File search says it needs es.exe | Step 3 |
| "Everything isn't running" | Start the Everything app (it can start with Windows) |
| `invalid_key` / can't reach a brain | Step 2; check C0RE is running at http://127.0.0.1:7080/admin |
| Otto asks about everything | Normal at first, until the test set is checked and Laya has more examples. Run `.\tool.cmd score` |
| Voice: nothing happens when you talk | Check the mic in `otto-phase0`: `check_live.py --list-devices`, then set `whisper.mic_device` |

## 12. Known limits in Phase 1

- Laya chooses the **area**. The **action** inside it (open vs close, etc.) comes from rules, then Qwen. Your
  confirmations are logged with the action, so Laya can learn actions later.
- Timers only run while Otto is open.
- Clicking buttons by name works in most normal Windows apps, but often not inside Chromium-based apps
  (Spotify, Discord). For those, Otto uses links and shortcuts instead.
- No talking over Otto to interrupt it yet (Ctrl+C works).
- Windows only. The floating overlay is Phase 2.
