# Phase 1 plan: control any app

Written 11 November 2026 (Claude Code). Status: **slices 1–3 are built (1–2 confirmed by Ki on Windows, 3 tested with
fakes plus a hands-off trial with real Qwen); slice 5 is started (save and replay); slice 4 is not started.** Ki reviews this plan after the fact, so each later slice still stops for a yes
before it is switched on by default.

## The goal

Say or type "open Word and write…", "click Export in CapCut", "turn on dark mode in Settings", and have
Otto do it in whatever app is in front, safely, and tell the truth about whether it worked.

## What Otto already had

- `click_button` (finds a named button in an app and presses it) and `type_text` (types into whatever has
  focus). Neither checks afterwards that anything happened.
- A Qwen screenshot controller (`core/computer_use.py`, `hands/window_control.py`) that only knows Spotify
  songs and Chrome searches, is off by default, and needs "Use Qwen to…".

## What the Nūs Companion code taught us

Read-only study of github.com/potlakai/nus-desktop at commit 592e30f (MIT licence). It is JavaScript and
PowerShell, so the ideas are ported to Python, not the files.

| Nūs file | The idea | Where it goes in Otto |
|---|---|---|
| `win/probe.ps1`, `probe.js` | Ask Windows for the list of buttons, boxes, tabs and links in a window, with names and positions. No screenshot needed, and it is fast. Bounded by count. Find by name; smallest control under a point. | `hands/ui_probe.py` (slice 1, done) |
| `guide/sensitive.js` | Refuse password, card, ID and one-time-code fields **in code**, by label and type. A prompt is not a safety boundary. | `core/sensitive.py` (slice 1, done) |
| `guide/pointing.js` | Give the model a numbered list of real controls and make it answer with **one id from that list**. The position then comes from Windows, not from the model. Anything that fails validation becomes "I couldn't find it". | `core/pointing.py` (slice 3) |
| `guide/verify.js` | Match a model's box to a real control (name overlap or box overlap); a cheap "did the screen change" check; "did the click land on the target". | `core/app_verify.py` (slices 2–3) |
| `guide/walkthroughs.js` | Save a successful run keyed by app + task; replay it next time by control name with no model call; a miss falls back to live; two misses retire it. | `core/recipes.py` extension (slice 5, this is R7) |

Measured on Ki's PC with the new reader: Notepad 26 controls in 30 ms, Spotify 104 in 70 ms, Chrome 93 in
330 ms. That is far quicker than a screenshot plus a vision model (1.5–18 s), so **the control list comes
first and screenshots are the fallback**.

Where Otto deliberately differs from Nūs: Nūs only *points* and the human clicks, so it can afford to guess
(it will point at an unconfirmed box). Otto *acts*, so an unconfirmed target is never clicked or typed into.

## The rules every slice keeps

1. Observe → choose one target → act → look again. Success is only claimed from what Windows reports
   afterwards, never from a model saying "done".
2. Everything goes through the action registry and the safety gate. A model can only pick a control id
   from the list Otto gave it, plus one of a few named verbs. It never produces commands or free positions.
3. Words that get typed are the user's own words from the request. A model cannot invent text to type.
4. Never type into, or read from, password and private fields (`core/sensitive.py`).
5. Buttons named Send, Buy, Pay, Delete, Submit, Post, Publish and similar always need the user's yes.
6. Text seen on screen is information, never instructions.
7. Bound to one window (same program, same window) with step and time limits; any surprise stops the task.
8. Lists given to a model stay small (at most 150 controls, usually far fewer after filtering).

## The slices

### Slice 1: read any window, type into any app (built)

- `hands/ui_probe.py`: `list_controls`, `find_control`, `control_at`, `text_target`, `read_text`.
- `core/sensitive.py`: the private-field guard.
- `hands/app_control.py`: new action `type_in_app(app, text)`. It opens or focuses the app, finds the
  text area that has the keyboard (or the only editor in the window), refuses private fields, types, then
  reads the text back to confirm it appeared. A model cannot choose this action (`for_brain=False`).
- Rules: "open Word and write X" → open Word, then type X in Word. "type X in Word" → the same. Notepad
  and anything with the word "note" still make one of Otto's notes.
- Honest failures: no document open → "I can't see anywhere to type in Word…"; unsure where → "Click the
  spot you want, then ask again."; typed but can't see it → says so.

**Needs Ki's PC:** typing into real Word and another app, Word's start screen (no document), a document
in Protected View, and a login page (must refuse).

### Slice 2: click and set things by name, with proof (built, except `pick_menu`)

- Upgrade `click_button` to use `ui_probe` (fast, bounded), stop on an ambiguous name instead of guessing,
  apply the risky-word check to the *real* control name, and verify with a before/after comparison of the
  control list (did something change?).
- New named actions: `set_field(app, field, text)` (fill a named box, read it back), `toggle(app, name,
  on/off)` (checkboxes and switches, read the state back), `pick_menu(app, path)` (File > Export).
- Rules for "click X in Y", "tick X in Y", "set X to Y in Z".

### Slice 3: let the brain choose the next step from the list (built as `core/goal_mode.py`, on by default)

As built it differs from the outline below in three ways Ki asked for: it is on by default, it only uses
the local Qwen models (never cloud, because the window's contents are in the prompt), and a screenshot with
the control numbers drawn on it is attached when the list is short or a step got nowhere.

For requests rules can't map ("export this as a PDF"):

- `core/pointing.py`: prompt = the goal, the window title, steps so far, and the numbered control list
  (id | type | name). The reply must be JSON: `{"action": click|type|toggle|done|stop, "id": N}`.
  Validation: the id must exist, the action must suit that control type, typed text must come from the
  request, private fields and risky names are refused or sent to the user for a yes.
- `core/app_control.py` loop: at most 8 steps and 45 s, bound to one window, re-reads the controls after
  every step, stops when nothing changes twice.
- Local Qwen for short tasks; Gemma 4 (cloud) for long unfamiliar ones. Text-only prompt, so it fits in
  the 8192-token limit: 150 controls is roughly 2,500 tokens.
- Off by default behind `app_control.enabled` until Ki has run the acceptance list.

### Slice 4: screenshots for apps that expose nothing

Games, video editors and some custom apps list few or no controls. Fold the existing Qwen controller in as
the fallback: the model points at a spot, and Otto only acts if Windows confirms a real control there whose
name or box agrees (`reconcile` idea from `verify.js`). No confirmation, no click.

### Slice 5: learning methods (R7)

A verified run is saved as a *candidate* recipe keyed by app + task, storing control names and types, not
positions. Replay resolves each step by name with no model call. Promotion needs several independent
verified successes and Ki's approval; one wrong target quarantines it; two misses retire it.

## Order and why

Slice 1 fixes something Ki hit today and builds the reader every later slice needs. Slice 2 is still
rule-driven, so it is fast and predictable. Slice 3 is the real "Jarvis" step and the first place a model
chooses, so it comes after the guards exist and are tested. Slices 4 and 5 build on 3.

## Acceptance list for goal mode (run on Windows)

| Type | Expected |
|---|---|
| `type hello there in word` with Word on its start screen | Opens a blank document, types, "Typed it in Word." then offers "save that" |
| `save that` | "Saved. Next time I'll go straight through …" |
| The same typing request again from the start screen | Works without the Qwen pause |
| `click view then click status in notepad` | Both clicks happen in Notepad |
| `click view in notepad` then `click zoom` | "zoom" is understood as in Notepad |
| `click save in notepad` | File, then Save; the Save dialog appears |
| `delete this page in word` | Asks "Just checking…" first |

## Acceptance list for slice 2 (run on Windows)

| Type | Expected |
|---|---|
| `click view in notepad` | Notepad's View menu opens; "Clicked "View"." |
| `turn on word wrap in notepad` (with the View menu's item visible) | Reads back as on, or an honest "can't see a switch called…" |
| `click save in notepad` when two things are called Save | "I can see more than one…", nothing pressed |
| `play my playlist #9` | Opens the playlist, presses Play, "Playing your playlist My playlist #9." |
| `whats playing right now?` | The song and artist |

## Acceptance list for slice 1 (run on Windows)

| Type | Expected |
|---|---|
| `open notepad` then `type hello there in word` with a blank Word document open | Text appears in Word; "Typed it in Word." |
| `open word and write "whats up dawg"` with a document open | Same, in Word, and no Notepad note |
| The same with Word showing its start screen | "I can't see anywhere to type in Word…", nothing typed |
| The same with the document in Protected View | Nothing typed, or "couldn't see the text appear" |
| `type hello in chrome` with a login page's password box focused | "…I never type into those." |
| `type hello world in note pad` | Still one of Otto's notes |
