# Otto: the plan after the first live runs (12 Nov 2026, updated after Fable checkpoint A)

Written for Ki Hurn and for the reviewing model (Fable), so both can check whether the work is still on course.

## Where we are

- The new core (one local Qwen3-VL 8B loop with ~15 small tools, behind `core.agent`) runs on the PC.
  Two live runs and two eval runs are logged in `docs/WORKLOG.md`.
- What works live: audio swap, opening apps, the save check, the send question showing the box's real text,
  asking before sending/running.
- What keeps failing: long chains of small steps (click number N, type, Enter) for an 8B model: wrong spots
  clicked, invented control numbers, text typed several times, claims of "done" that weren't true.
- The last batches were mostly guards against single sentences from the logs. Each is small, together they add
  layers. **We stop doing that** (see "Rules for this plan").

## What other projects taught us (research summary in chat, 12 Nov)

- Microsoft UFO² (Windows, UI Automation): app APIs first, clicking only as a fallback; controls chosen by name;
  several steps planned per model call; learns from saved past runs and documents, **no retraining**.
- Windows-Use (same design as our new core) recommends big cloud models: the raw click/type loop is hard for 8B.
- Agent S2/S3: a planner plus a small specialist model only for finding things on screen.
- Qwen3-VL gives screen positions on a 0-1000 grid (fixed in Otto on 11 Nov).

## Before building: a five-minute check on the PC (the user)

Facts the code relies on but nobody has seen yet:
1. Type a letter in Notepad: does the window title show an unsaved mark (`*` or a dot)?
2. Does plain "Windows PowerShell" appear in the Start menu?
3. What did "clear" mean in the first live run (clear the text box, or close something)?
4. Grid clicks: answered by the live test below.

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

### Step 3. A spoken pass (hands-free)
Run the live list by voice (`otto voice`). Target from AGENTS.md: under 2.5 s for simple spoken requests.
Before checkpoint B.

### Step 4. Delete the old core (was "Task 9")
Only after steps 1-3 show the new core is better on the live test.
- **Remove:** compiler, interpreter, computer_use, window_control, recovery, goal_mode, offline_eval,
  visual_task, methods, the old pipeline special cases and the `core.agent` switch.
- **Move first** (things still used): `goal_mode.shortlist` (used by `core/tools.py`); check every importer
  (`hands/app_control.py`, `spotify_desktop.py`, `spotify_search.py`, `core/audio_focus.py`, `hands/web.py`,
  `hands/registry.py`, `core/evaluate.py`, `otto.py`). The list is built from imports, not from memory.
- **Stays:** Laya (router), the `details` fast path, `safety`, `action_runtime`, `hands/`, `senses/`, examples.
- Update AGENTS.md, ARCHITECTURE, README.

### Step 5. Teaching mode (step-by-step with your approval), on top of the skills
Otto shows each step, you approve or correct; approved runs become saved examples (`core/examples.py` already
stores "save that" runs). Fine-tuning only if this still isn't enough, and only on approved runs.

### If the score stays low after the skills
Try a GUI-specialised 8B model (GUI-Owl-1.5-8B) for the look-and-click step, or a cloud model for hard tasks,
measured with the live test. **Not** more guards.

### Later (decided together, not started on our own)
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

## Fable checkpoints (the user switches to Fable manually)

| When | What Fable checks |
|---|---|
| ~~A. Before building~~ | Done 12 Nov: on course; live test first, reuse app_control, menu size, voice pass, import-based delete list, MCP moved to later. |
| **B. After steps 1-3** (live test, skills, voice pass; before deleting the old core) | Code review of the skills; did guard code shrink; safety rules intact; is the live test meaningful? |
| **C. After step 4** (old core deleted) | Whole-branch review: anything broken or left behind, docs accurate. |
| **D. Before the first MCP server** (later) | Security review: permissions, keys, email text as instructions, the safety gate on MCP tools. |
