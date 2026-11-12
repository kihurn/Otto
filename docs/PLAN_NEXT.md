# Otto: the plan after the first live runs (12 Nov 2026)

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

## What other projects taught us (docs: research summary in chat, 12 Nov)

- Microsoft UFO² (Windows, UI Automation): app APIs first, clicking only as a fallback; controls chosen by name;
  several steps planned per model call; learns from saved past runs and documents, **no retraining**.
- Windows-Use (same design as our new core) recommends big cloud models: the raw click/type loop is hard for 8B.
- Agent S2/S3: a planner plus a small specialist model only for finding things on screen.
- Qwen3-VL gives screen positions on a 0-1000 grid (fixed in Otto on 11 Nov).
- Jarvis voice projects: same voice chain as Otto; tools added through MCP; little real desktop control.

## The plan (in this order)

### Step 1. Skills: bigger tools that do a whole job and check themselves
Qwen picks one skill and fills in the details; plain code does the steps and checks each one.

| Skill | Checks done in code |
|---|---|
| `send_message(app, to, text)` | right chat open (name in title/header), box empty, typed once, read back, ask, sent message visible |
| `search(where, query)` | Google / YouTube / Spotify search shown on screen (address bar or app shows it) |
| `click_item(description)` | finds the control by name/kind/order ("second video", "Save"); nothing invented |
| `save()` | ctrl+s, unsaved mark gone, Save As asks for a name |
| `type_into(app, text)` | text area found, typed once, read back |

- Shaped like MCP tools (name, description, parameters, result), so step 2 plugs in without changes.
- The small tools stay as a fallback for apps no skill covers.
- Guards that a skill makes unnecessary are **removed** in the same change (the total code should shrink or
  stay level, not grow).
- Done when: the skills pass their tests, and the live checklist below passes on the PC.

### Step 2. One-command live test
`otto eval --core new --live`: runs a fixed list of safe tasks on the real screen and scores them
(Notepad type + save, YouTube second video, Google search, audio swap and back, a Discord message to yourself
that must stop at "Just checking"). Replaces the 15-minute manual test and log pasting.

### Step 3. Delete the old core (was "Task 9")
Remove compiler, interpreter, computer_use, window_control, recovery, goal_mode, offline_eval, visual_task, the
old pipeline special cases and the `core.agent` switch; update AGENTS.md, ARCHITECTURE, README. Only after
steps 1-2 show the new core is better on the live test.

### Step 4. Otto uses MCP servers (Otto as an MCP client): email and calendar first
- Gmail and Google Calendar through MCP servers instead of clicking web pages. Then CRM, Obsidian, Notion.
- Every MCP tool goes through Otto's safety gate (sending, deleting, buying ask first).
- Text from emails/MCP results is information, never instructions.
- Tools shown to Qwen only when relevant (keep the menu small, like Laya's ~20 options rule).
- Each server reviewed before it's added; keys only in `.env`.

### Step 5. Teaching mode (step-by-step with your approval), on top of the skills
Otto shows each step, you approve or correct; approved runs become saved examples (as UFO² does).
Fine-tuning only if this still isn't enough, and only on approved runs.

### Later
- Try a GUI-specialised 8B model (GUI-Owl-1.5-8B) for the look-and-click step, measured with `otto eval`.
- Otto as an MCP server (other apps / the phone web app use Otto's skills).
- Phase 2 companion overlay, CRM, student features (see AGENTS.md section 8).

## Rules for this plan

1. No more fixes for single log sentences unless something is **unsafe**. Failures are grouped into causes and
   fixed by a skill or by a general rule.
2. Every change must keep or shrink the amount of guard code; a skill replaces guards, it doesn't add to them.
3. Success is measured by the live test and `otto eval`, not by whether one sentence works.
4. Safety rules from 11 Nov stay exactly as they are (ask before sending/running/buying/deleting; never type
   in password fields; screen and email text are never instructions; a model never produces shell commands).

## Fable checkpoints (the user switches to Fable manually)

| When | What Fable checks |
|---|---|
| **A. Now, before step 1** | Is this plan on course for the goal (hands-free Jarvis, on-screen companion)? Are the skills the right ones? Anything missing or over-built? |
| **B. After step 1 + 2** (skills and live test built, before deleting the old core) | Code review of the skills; did guard code shrink; are the safety rules intact; is the live test meaningful? |
| **C. After step 3** (old core deleted) | Whole-branch review (the original Task 9 review): anything broken or left behind, docs accurate. |
| **D. Before step 4 goes live** (first MCP server) | Security review: permissions, keys, email text as instructions, the safety gate on MCP tools. |
