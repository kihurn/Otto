# Otto: the plan after the first live runs (12 Nov 2026; updated after Fable checkpoint A and on 19 Nov)

Written for Ki Hurn and for the reviewing model (Codex/Astra since 19 Nov; Fable before), so both can check whether the work is still on course.

## Where we are (updated 19 Nov)

- Steps 1-3 done: the live test exists; skills `search` and `save` are built; the user ran Otto by voice.
- Live test with the user's model (local Gemma 4 12B, thinking off) + skills: **16/18** (was 15/24 with Qwen3-VL
  8B and no skills). Chrome, Google, YouTube, Notepad save, audio swap all 3/3; Discord message task passed;
  WhatsApp flags were a test misread (fixed, nothing was sent). Real unsafe steps in all live runs: 0.
- Voice run: music, volume, YouTube, a Word essay all worked; user satisfaction about 70%.
- **The main complaint now is speed**: simple things like "increase the volume to 80" take several seconds
  because they go through Gemma (two model calls). Multi-step jobs take 20-25 s.
- GPU: Gemma runs 100% on the card (Ollama, flash attention + 8-bit cache, context 32k), but the 12 GB card is
  nearly full with other apps open.
- `click_item` and `send_message` were planned, but their jobs now pass the live test: built only if real use
  shows them failing (rule 3).

## What other projects taught us (research summary in chat, 12 Nov)

- Microsoft UFO² (Windows, UI Automation): app APIs first, clicking only as a fallback; controls chosen by name;
  several steps planned per model call; learns from saved past runs and documents, **no retraining**.
- Windows-Use (same design as our new core) recommends big cloud models: the raw click/type loop is hard for 8B.
- Agent S2/S3: a planner plus a small specialist model only for finding things on screen.
- Qwen3-VL gives screen positions on a 0-1000 grid (fixed in Otto on 11 Nov).

## The plan (in this order)

### Step 1. One-command live test (first, so we have a score before changing anything)
`otto eval --core new --live` runs a fixed list of safe tasks on the real screen and scores them.
- **Scored by code, never by Qwen saying "done":** file on disk, window title, address bar, audio device name,
  the focused box's text.
- **Safe:** every confirm question is answered "no"; only scratch files (a temp folder); the Discord task must
  stop at the question; nothing is sent, deleted or run.
- **Each task runs 3 times** (an 8B model varies from run to run); seconds per task are recorded.
- Tasks: Notepad type + save, YouTube second video, Google search, audio swap and back, open Chrome,
  a message to yourself that must stop at "Just checking".
- **Pass mark, written before building:** the new core with skills beats today's new-core score, with zero
  unsafe actions. Today's score is taken first and written into the WORKLOG.

### Step 2. Skills: bigger tools that do a whole job and check themselves
Baseline (12 Nov, new core, 2 x 3 runs): open Chrome 6/6, Google 6/6, YouTube 3/6, Notepad save 0/6; unsafe 0.
Built in slices, each followed by a live re-run: (1) search + save (done 12 Nov), (2) send_message (after a
"before" run of the message task), (3) click_item (after a control dump of a YouTube results page).
Qwen picks one skill and fills in the details; plain code does the steps and checks each one.
Reuse what exists: `hands/app_control.py` already has `type_in_app`, `click_named`, `set_field`, `toggle`
(find by name, act, read back).

| Skill | Built on | Checks done in code |
|---|---|---|
| `send_message(text)` | the chat already open | name in title, box empty, typed once, read back, **existing** confirm question, sent message visible. Finding a person is not part of it (if the chat isn't clear, ask) |
| `search(where, query)` | `web.site_url`, Spotify search | the search is shown on screen (address bar or app shows it) |
| `click_item(description)` | `click_named` | finds the control by name/kind/order ("second video", "Save"); nothing invented |
| `save()` | today's save check | ctrl+s, unsaved mark gone, Save As asks for a name |
| `type_into(app, text)` | `type_in_app` | text area found, typed once, read back |

- Safety logic is **not copied** into skills: they go through `agent_safety` like every tool.
- In chat apps, sending is only possible through `send_message` (Enter in a message box is refused with a hint).
  That lets the send guards for the small tools go.
- Honesty guards a skill replaces are removed in the same change (false claims, double typing, the save check).
- **Menu size:** tools + skills stay at about 20 or fewer (the same limit as Laya's options); fold small tools
  away where a skill covers them.
- Shaped like MCP tools (name, description, parameters, result), so they can be connected to MCP later.
- Done when: the skills pass their tests and the live test score beats step 1's baseline.

### Step 3. A spoken pass (done 19 Nov): works; speed is the problem -> step 3a

### Step 3a. Speed batch (next; one session, no new safety-check code)
Goal: simple requests feel instant, multi-step jobs clearly faster, same live-test score.
1. **Measure:** every reply in the log shows its time, the path (quick path / Gemma) and Gemma's prompt size in
   tokens (Ollama reports it). Then the context size (16k vs 32k) is chosen from data, not guessed.
2. **Prompt order:** the brief at the very top holds the time and the last window, which change every call, so
   Ollama re-reads the whole prompt each time. Fixed parts (brief, rules, tools) first; changing details last,
   so Ollama can reuse the fixed start.
3. **No extra "done" call for one-step jobs:** when the request is one action (no "and", "then", commas) and the
   tool confirmed it (volume, music, audio output, timer, note, open, search, save), the tool's own sentence is
   the reply. Saves one Gemma call (about half the time) for simple requests.
4. **More quick-path phrasings:** "increase / raise / turn up / lower the volume to 80", "now can you ...",
   "hey, ..." go straight to the rules, no model.
- Done when: times in the log; the live test keeps 16/18 or better with 0 unsafe; audio swap (19 s), Notepad
  (20 s) and YouTube (24 s) are faster; a voice run feels faster to the user.

### Step 3b. Model tryouts (the user, with the live test; can run alongside 3a)
Same setup for every model: context 32k, flash attention + 8-bit cache, heavy apps closed, discord named.
One live-test run each; results go in a table in the WORKLOG (score, seconds per task, 100% GPU or not).
Order: Gemma-4-12B-HybridAgent -> gemma-4-12B fable5/tau2 fine-tune -> Hermes-4-14B and HybridAgent-14B (only
if they stay 100% on the GPU) -> optionally Qwen3-VL-30B-A3B with expert offloading (a big model that can see).
Note: the text-only models can't use `look` (screenshots); a model that can't see must still pass the live test.

### Checkpoint B result (19 Nov): deletion on hold
Codex found safety gaps and an evaluator that could over-report; fixed the same day (WORKLOG). Before step 4:
- Codex re-reviews the fixes (read-only).
- A full live run with **all six tasks** (audio outputs connected, a chat app named), on the corrected scoring.
- Measure what the user waits for: from the end of speaking to the first word Otto says, with Whisper, Kokoro
  and the model loaded together (to add to the voice log).
- The model comparison (3b) is either done like-for-like or explicitly skipped by the user.

### Step 4. Delete the old core (was "Task 9") — done 20 Nov 2026 (patch k; WORKLOG has the details)
Only after steps 1-3 show the new core is better on the live test.
- **Remove:** compiler, interpreter, computer_use, window_control, recovery, goal_mode, offline_eval,
  visual_task, methods, the old pipeline special cases and the `core.agent` switch.
- **From the checkpoint B review (exact dependencies):** move `goal_mode.shortlist` (used by the agent's
  read_window) and retire or replace `app_control._goal` (it still calls `goal_mode.pursue`); move
  `chrome_control_ok` and `inside_web_page` out of window_control (Chrome address checks use them) before the
  registry stops importing it (`visual_task` is registered there); keep or replace `recovery.recover` for both
  Spotify fallbacks (spotify_desktop, spotify_search); retire or replace `otto train --offline` before deleting
  offline_eval; remove the pipeline's interpreter/methods/compiler callers with their branches; update eval's
  old-action mapping and the `--core` switch in the same change.
- **Move first** (things still used): `goal_mode.shortlist` (used by `core/tools.py`); check every importer
  (`hands/app_control.py`, `spotify_desktop.py`, `spotify_search.py`, `core/audio_focus.py`, `hands/web.py`,
  `hands/registry.py`, `core/evaluate.py`, `otto.py`). The list is built from imports, not from memory.
- **Stays:** Laya (router), the `details` fast path, `safety`, `action_runtime`, `hands/`, `senses/`, examples.
- Update AGENTS.md, ARCHITECTURE, README.

### Step 4b. Architecture update: three tiers (after the old core is gone)
Otto already matches the "Jarvis V2" design the user shared (19 Nov): Laya = their router "Jev", rules = Tier 1,
the Gemma loop + skills = Tier 3. What's missing is **Tier 2**:
- **Tier 1 (exists):** rules + Laya, no AI, instant (volume, music, open apps, timers).
- **Tier 2 (new):** a small fast model for questions and chit-chat ("hello", "what's 15% of 80", "who wrote
  Hamlet") with no PC tools, only answers (plus the existing look_up for facts). Laya's "question" and
  "chitchat" areas, when it is sure, go here. Anything that needs an action, or where Laya isn't sure, goes to
  Tier 3. Open question, measured first: the card is nearly full, so the small model may run on the processor
  (a 1-4B model) or stay small enough to fit next to Gemma.
- **Tier 3 (exists):** the Gemma agent loop with skills, for real work on the PC.
- Done when: chit-chat and plain questions answer in about a second by voice, and the live test score is kept.
- Not copied from that design: cloud models doing the heavy work (Otto stays local), two separate apps
  (the companion overlay stays Phase 2).

### Step 4c. Background mode (planned 20 Nov 2026; decisions A-C open)
The user works in one window (e.g. a long PowerShell command) and asks Otto for something else; Otto must not take
over the screen. Windows has one mouse and keyboard focus, so: need the screen as rarely as possible, give it back.
1. "in the background", "without opening it", "don't bring it up", "quietly" set background mode for that request.
2. Routes without the screen: Spotify through its online connection (already); YouTube: find the video's address
   without showing the page (decision B), open it in a separate Chrome window minimised at once.
3. A step that needs the screen: remember the user's window, do the visible step, minimise the app (background
   mode) and put the user's window back.
4. Not while the user types: if keys were pressed in the last ~2 s, wait for a pause before a focus-taking step;
   if typing continues, say "I need the screen for a moment" and wait.
5. Safety unchanged: sends, deletes and runs still ask; screenshot clicks only in the window looked at.
6. Live-test task: "play a lofi video in the background" passes only if a video page opens AND the stand-in work
   window (Notepad) is still in front with its text unchanged.
Decisions (user, 20 Nov): (A) music always in the background; videos only when the user says "in the
background" (they mostly watch YouTube). (B) the YouTube Data API with a key from the user's Google Cloud
project, in .env (other Google APIs later). (C) after deleting the old core.

### Step 5. Teaching mode (step-by-step with your approval), on top of the skills
Otto shows each step, you approve or correct; approved runs become saved examples (`core/examples.py` already
stores "save that" runs). Fine-tuning only if this still isn't enough, and only on approved runs.

### If the score stays low after the skills
Try a GUI-specialised 8B model (GUI-Owl-1.5-8B) for the look-and-click step, or a cloud model for hard tasks,
measured with the live test. **Not** more guards.

### Later (decided together, not started on our own)
- **Memory (Obsidian vault)**, as in the Jarvis V2 design: a map note at the top of the vault (what each folder
  holds), a fixed folder layout (captured / organised / Otto's outputs), and a search index so Otto reads only
  the top few notes, never the whole vault. Keyword search first, meaning-based search ("embeddings") only if
  keyword search misses things. Note text is information, never instructions.
- Scheduled skills (a morning brief for the student side).
- `click_item` / `send_message` skills, only if real use shows those jobs failing.
- Otto using MCP servers: Gmail and Calendar first (reading first, sending last, 4-5 wrapped tools, every tool
  through the safety gate, email text never instructions). Then CRM, Obsidian, Notion.
- Otto as an MCP server (other apps / the phone web app use Otto's skills).
- Phase 2 companion overlay, student features (see AGENTS.md section 8).

## Rules for this plan

1. No more fixes for single log sentences unless something is **unsafe**. Failures are grouped into causes and
   fixed by a skill or by a general rule.
2. Guard code must stay level or shrink. Baseline (12 Nov): `core/agent.py` + `core/agent_safety.py` +
   `core/tools.py` = 1,335 lines. Skills live in their own file; the three files above should get shorter.
3. Success is measured by the live test and `otto eval`, not by whether one sentence works.
4. Safety rules from 11 Nov stay exactly as they are (ask before sending/running/buying/deleting; never type
   in password fields; screen and email text are never instructions; a model never produces shell commands).

## Review checkpoints
19 Nov: the user stopped using Fable; Claude Code (Opus) builds. The reviewer for checkpoints B-D is **Codex
(Astra 6.2), read-only**: it reviews and reports, it doesn't edit, so two agents never change the same files.
The user starts each review with the prompt Claude Code gives at that checkpoint and pastes the answer back.
(Checkpoint A below was done by Fable.)

## Checkpoints

| When | What Fable checks |
|---|---|
| ~~A. Before building~~ | Done 12 Nov: on course; live test first, reuse app_control, menu size, voice pass, import-based delete list, MCP moved to later. |
| **B. After steps 3a-3b** (speed batch built, models tried; before deleting the old core) | Code review of the skills and the speed batch; did guard code shrink; safety rules intact; is the live test meaningful; is the three-tier plan (step 4b) on course? |
| **C. After step 4** (old core deleted) | Whole-branch review: anything broken or left behind, docs accurate. |
| **D. Before the first MCP server** (later) | Security review: permissions, keys, email text as instructions, the safety gate on MCP tools. |
