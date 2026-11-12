# Otto work log

Shared by every agent (Claude Code, Codex) and the user. Newest first inside each section.

## In progress
<!-- Claim before starting: - [agent] task – started YYYY-MM-DD (files you expect to touch) -->
- [claude] docs/PLAN_NEXT.md step 1: live test (`otto eval --core new --live`) – started 2026-11-12 (core/evaluate.py, core/live_test.py, otto.py, defaults/live_tests.csv).

## Next up
The order is in `docs/PLAN_NEXT.md` (updated after Fable checkpoint A, 12 Nov): live test, skills, voice pass,
delete the old core, teaching mode. MCP (Gmail/Calendar) moved to "Later". Older items (1.2 voice checks,
goal-mode reruns, slice 4) are replaced by that plan.

## Done

### New core: fixes from the second live run (11 Nov 2026, Claude Code, main)
Log after pulling the first batch: audio swap works both ways; Chrome opens ("already open, brought to front");
the save check caught a false "saved"; the send block and box readback worked (the question showed
"thank you guysthank you guysthank you guys", and the user still said yes). New failures and causes:
- `web.site_url` rejected full `https://` addresses, so open_site Googled them (YouTube links opened Google).
- `open` Googled any unknown text ("a new tab in Chrome"); Qwen then pressed a "Plus Button" described in
  Google's AI overview. Now refused, with a ctrl+t hint; `google` tool added; `web_search` renamed `look_up`.
- Two look-based clicks hit "Desktop 1" (the taskbar). Likely cause: Qwen3-VL gives positions on a 0-1000 grid,
  not pixels (not confirmed). Positions are now asked for and read on that grid and must be inside the window.
- Qwen invents control numbers before reading; the failure blocked the same call after a read. Such failures
  are now `blocked` (retryable), and `type` with an unknown number and no read types at the cursor.
- `type` into control 1 (a server icon) "worked": typing is refused into non-text control types.
- Unbacked claims ("Message sent" with no step, "typed" after failed typing): `agent._unbacked_claim`.
- Mute toggled 16 times: `_back_and_forth` stops after A, B, A, B.
- Qwen still opened Anaconda PowerShell Prompt for "powershell": `_wrong_app` refuses other installed apps when
  the request named one. Whether "Windows PowerShell" is in the user's app index is unconfirmed.
- A pending ask_user swallowed new requests (six times). `pipeline._answers_question`: yes/no, an offered
  option, or a short reply that doesn't read like a request ("can you", "open", "what", "you ...") is the answer;
  anything else drops the question (marked unanswered) and runs as a new request.
- Advisor review of this batch: dedupe only in chat boxes holding little more than the text; claims checked only
  when the request asked for that action; an invented control number (no read yet) stays refused, only a stale
  one is retryable; flip-flop guard only for media/audio_output; explicit mute/unmute via `set_mute` (verified
  with GetMute); `_wrong_app` refuses only look-alikes sharing a word; `named` apps in the trace; `look_up` refused
  when the request says search/google; `web_search` kept as an alias for saved examples; position clicks on Send
  ask with the text and person.

### New core: fixes from the first live run (11 Nov 2026, Claude Code, main)
The user's live log (core.agent true) showed: a WhatsApp message sent after a click from a screenshot with no
re-read of the chat; "ok sure" typed three times into Discord's box across runs; "what is on my discord" redoing
the earlier reply and YouTube searching the earlier "banana bread" (conversation bleed); "Saved the file." after
clicking an unknown control; web_search used for "search and press show more", then a click at a random spot;
"open chrome" failing; "swap my audio output" setting the device already in use; PowerShell opened as Anaconda
Prompt; "clear" closing Discord. User decision: fix code and instructions first, fine-tune only after
(training on top of these bugs would teach Qwen workarounds).
- Sending (`agent_safety.blocked`, `_send_question`): a send is refused (not even asked) until read_window/look
  happened after the last open/click in the request; the question shows the focused box's real text and the
  window title minus unread counts. Blocked calls don't count as failures or block the retry.
- Conversation (`pipeline._conversation(t)`): chain of turns with gaps under 180 s; empty when the request names
  an app/site after open/in/on/... and isn't a follow-up or correction. One note, "already finished: never redo";
  dropped confirms marked NOT done; no step lists. "new topic"/"start over" clear history. Bare "clear" is
  deliberately NOT a command (it may mean "clear the text"): Qwen is told to ask about one- or two-word requests.
- Done checks (`agent._not_saved`): triggered by a Save press or Qwen claiming "saved" (not by the user's words).
  Confirmed only when the title had an unsaved mark (`*`, ●, "unsaved") before Save and not after; otherwise
  "I pressed Save, but couldn't confirm it saved." A Save As window asks for a name. Title marks are from
  memory: PC check needed. The send question uses the box's text only when it contains what was typed.
- Gate keeps context for "open it in chrome" / "type that in notepad" (verb + it/that); "new topic" also cancels a
  waiting question. Advisor review of this batch applied.
- Tools: web_search says nothing was shown and points to a Google link; position clicks report the name under the
  point; `swap_audio_output`; `agent.named_apps` hint; `win.find_window` accepts chrome.exe for "Google Chrome".
- Logging: each call's `say` (160 chars) is in `otto-data/logs`.
- Chrome cause NOT confirmed: the profile-name title is a guess; the next log shows the real reason.

### Agent core, task 7: the new core inside the pipeline (11 Nov 2026, Claude Code, main)
- Behind the setting `core.agent` (default off; `otto eval --core new` turns it on for the eval only). Off = the old
  pipeline, unchanged.
- On: guards, misheard words, open questions, "save that"/"forget that" and "do that again" stay. Then time, date and
  maths are answered locally; then the fast path; everything else goes to the agent loop. The old follow-up rewrite,
  "it was not played", "use qwen to", the regex shortcuts, the old Qwen supervisor and brain guessing are skipped.
- Fast path (`details.whole_command`, `details.whole`, `Intent.full_match`): door 1, unmistakable whole sentences
  without Laya (pause/next/mute, volume up/down/to N, what's playing, a timer with only a length); door 2, Laya at
  or above the acting bar picks the area AND that area's rule covers the whole sentence (open/close an exact app,
  "play X by Y", "google X", "find my X"). Joined sentences (and, then, commas...) never take the fast path.
- Agent questions and yeses are pending answers (`agent_ask`, `agent_confirm`). A yes is checked against the window
  and focused box from when Otto asked: Otto brings that window back to the front (you typed the yes into Otto's own
  window) and refuses if it changed. Anything other than yes/no drops the waiting step; expiry works as before.
- The loop gets its own 90 s deadline (also on resume); conversation = last 6 exchanges with a short "did:" note.
- "save that" saves an example only after a live run that finished with every acting step OK (an approved step
  counts once); "forget that" removes it.
- `otto eval --core new`: the first call is judged; must-ask sentences run to the end in dry-run, and only a yes
  request counts as asking (a clarifying question does not). A must-ask run that acted and finished without a yes is
  a safety regression. Dry-run knows File Explorer, Command Prompt and Terminal. Two eval rows changed (Notepad type
  and click now accept open/read_window first): delete otto-data/eval.csv to pick them up.
- Reviewed by Fable 5.2 before building (window-in-front on yes, deadline on resume, old layers leaking, Laya's role,
  honest eval) and after: time/date answered locally only for whole questions ("time in tokyo" goes to the loop),
  YouTube/video sentences never take the Spotify fast path, an unresolved volume follow-up reaches the loop, earlier
  screen reads are dropped after you answer a question, and the run file keeps each case's agent steps. 559 tests.
- Correction: the two reviews above ran on the advisor tool while it was still not Fable (its usage stayed 0). The
  user then switched the session itself to Fable 5.2, which reviewed all of task 7 and fixed: Otto's cancel key now
  stops the loop (between steps and inside a key press or click); nothing is typed, pressed or read while Otto's own
  window is in front; a yes still counts when only the unread counter in the window title changed; agent questions
  and yeses wait 2 minutes, not 30 s; "do that again" goes to the loop; conversation older than 15 minutes is left
  out; failed steps are not saved into examples; "10-4" is not a sum; the glow is hidden after a run (a pointer you
  asked for stays); "open youtube" (a site in your sites list) takes the fast path. 569 tests.
- Task 8, first numbers from the PC (11 Nov, same 25 rows): old core 16/25, new core 19/25. The new core fixed
  "open youtube and play the first video", both Notepad rows and "swap my audio output". Its one ordinary miss,
  "play some lofi on youtube", opened YouTube first (right) but the row wanted "lofi" in that first step; the row now
  wants "youtube". All five must-ask rows read "did not ask first" on BOTH cores, as expected in dry-run; the agent
  steps from the run file and the live check decide those.
- The new core's steps on the must-ask rows (run file, 11 Nov): no safety regressions; none reached a risky step.
  One loop bug seen and fixed: look / same failing click, seven times, until the step limit. Now a step that already
  failed in the request is not run again, and four failed steps in total stop the run. In a rehearsal (dry run) Qwen
  is told that "would ..." means done, so it carries on instead of repeating "open". 572 tests.
- For Task 8: re-run `otto eval --core old` on the same (updated) file, as the 16/25 baseline used the older rows.
  Must-ask sentences can't reach their risky step in dry-run (no real window to read), so judge those in the live
  check. PC-only: after a typed yes, does Otto really bring the chat window back with the same box focused?

### Agent core: review fixes before wiring it in (11 Nov 2026, Claude Code, main)
- Safety judges the live foreground window and live keyboard focus (not the last window read); `open` forgets the
  last window; control numbers expire after any action (re-read needed), so the step limit is now 16 calls.
- Mouse fallback clicks check what is really under the point; Enter/Space on a focused risky button asks; a failed
  "what's under this point" lookup asks instead of allowing.
- `open`: drive paths with either slash and `file:` links go through `open_path` (programs ask first); other links only
  for known schemes (spotify, ms-settings, mailto, steam, discord, ...).
- `type` fills a box directly only when it is empty (UI Automation SetValue replaces everything); otherwise it focuses
  the box and types at the cursor. `verified` is set only when the text is read back.
- Repeat guard lets navigation keys and scrolling repeat. 522 tests.
- Correction: the advisor reviews so far ran on Opus 5.5, not Fable (the /advisor change applies after /compact or
  /clear). For task 7: give agent runs their own deadline (the 45 s turn deadline would cut the 90 s budget), and
  only save examples from runs code verified.

### Agent core, task 6: the agent loop (11 Nov 2026, Claude Code, main)
- `core/agent.py`: `run(request, conversation, brain, ctx)` / `resume(pending, brain, answer=|yes=)`. Qwen replies
  `{"tool","args","why"}` (our JSON format; native tool calling works too but has no "why", which the coordinate-click
  safety rule reads). Limits: 12 calls, 90 s, two failures in a row, one corrective retry for an invalid call,
  identical consecutive acting calls not run. `ask_user` and "waiting for a yes" end the turn with resumable state.
  `stop_after` lets eval judge only the first decision. In dry runs the safety rules judge by the app last opened.
- `core/examples.py`: "save that" examples (otto-data/agent_examples.jsonl), most similar 5 shown to Qwen.
- Not in this task: replaying goal mode's saved methods without a model call (decide in task 7/9 whether examples
  are enough). 12 tests.

### Agent core, task 5: look, positions, scroll, drag, point (11 Nov 2026, Claude Code, main)
- `senses/eyes.capture(hwnd)` returns the image plus the captured screen rectangle and shrink scale; `tools.to_screen`
  maps an image x,y back to the screen. New tools: `look` (screenshot + Qwen, answer as information), `point`,
  `scroll`, `drag`; `click` also takes x,y from the last look (refused without one). Coordinate clicks ask Windows
  what is under the point (`agent_safety.name_at`, UI Automation ElementFromPoint) and ask first for risky names, or
  when nothing is identified and the model's stated reason is risky. `hands/mouse.py`: scroll, drag.
- Not verified on Windows yet: ElementFromPoint call shape, DPI (physical pixels assumed), sideways scrolling.

### Agent core, task 4: safety rules for tool calls (11 Nov 2026, Claude Code, main)
- `core/agent_safety.check(name, args, ctx)` runs inside `tools.call` before every call: send keys / typed new lines in
  message boxes and messaging apps, Enter/Run/OK for typed commands (terminals, Run box, Explorer address bar, VS
  Code terminal), select-all then Delete/Backspace, Delete in Explorer/mail/chat, risky button names. A yes lets
  exactly the next call through. Plain close is free in the new core (the old pipeline's close still asks); AGENTS.md
  rule 4 updated. 16 tests.

### Agent core, task 3: the tool menu (11 Nov 2026, Claude Code, main)
- PC results: native Ollama tool calling works through C0RE with qwen3-vl:8b (0.8 s, `open("youtube")`); graphics
  memory 9.7/12 GB at 32k with Laya + Qwen (no Whisper; re-check when voice is used); `otto eval` baseline for the
  current core: 16/25 (misses: YouTube first video, type/click in Notepad, swap audio output, all five must-ask cases).
- `core/tools.py`: 15 tools (open, close, find_files, media, audio_output, timer, note, web_search, read_window, click,
  type, keys, ask_user, done) over the existing actions through `safety.run_plan`; `menu()` for our JSON format and
  `schemas()` for Ollama's native tools; `validate()`/`call()`; outside text returned as `information`. read_window's
  numbers are exactly the listed controls (goal_mode.shortlist renumbers, so the full list is not kept). The Windows
  key is never allowed in `keys`. `hands/mouse.py` started (click_at). Added `close` (missing from the spec's list).

### Agent core, task 2: `otto eval` (11 Nov 2026, Claude Code, main)
- `core/evaluate.py` + `defaults/eval.csv` (25 seed sentences from recorded failures and the acceptance lists, seeded
  into otto-data/eval.csv): runs Otto in dry-run with the real Laya and Qwen and judges route (fast/loop/reply), first
  tool, key words and "must ask first". Old actions are mapped to the new tool names (`OLD_TO_TOOL`). Results go to
  otto-data/eval_runs/. Case args are a list of words that must appear (not a dict as the plan sketched).
- "Understood" is judged on what Otto does (first tool, key words, asking when a case must ask); the route is shown
  but not scored, so old and new cores are compared on outcomes. A safety regression means a risky step would have
  run without a yes (`Decision.unsafe`, set by the new core in task 7); refusing or not getting that far is a miss.
  New default sentences are added to an existing otto-data/eval.csv automatically. Eval never answers questions or
  says "save that", so it teaches Laya nothing (checked: `_learn` only runs after an answer or "save that").
- Baseline still to run on the PC: `otto eval`.

### Agent core, task 1: context size, multi-turn chat, local models only (11 Nov 2026, Claude Code, main)
- Design approved by the user (docs/superpowers/specs/2026-11-11-agent-core-design.md): one local-Qwen loop with
  tools replaces the deciding layers; 1.2's remaining checks are frozen (replaced by the new core); Codex paused on
  new features; C0RE and Ollama context length raised to 32k by the user.
- `core/brain.py`: every call sends `num_ctx` (`brain.num_ctx`, default 32768); new `Brain.chat(messages, ...)` for
  the loop's own conversation. Gemma 4 cloud (now paid) removed from every default chain; settings v3 migration
  removes it from existing users' chains. Linux-only test failures fixed (pywinauto import order in
  hands/spotify_desktop.py). `tools/tool_call_probe.py` checks native Ollama tool calling on the PC. 456 tests pass.
- On the PC: run `python tools\tool_call_probe.py`, and check graphics memory with Otto running.

### Laya 90% acting floor (11 Nov 2026, Codex)
- Inspection found brains.decide still tried Gemma cloud first despite the interpreter's Qwen name. Set this user's decision chain to local qwen3-vl:8b-instruct, then qwen3-vl:4b-instruct, as requested. Other job-specific model chains are unchanged. Read back both settings successfully; no model inference was run.
- User requested that Laya act directly only at 90% confidence or above, handing less-confident requests to Qwen. Set this user's zones.act_bar and zones.act_bar_floor to 0.90 using the settings API. Effective loaded threshold verified as 0.90; 0.89 is middle, 0.90 is high. No retraining or default migration.
- The acting floor now applies even when measured bars are disabled or unavailable. Stricter measured thresholds remain respected. Removed the old split-request shortcut that allowed middle-confidence Laya decisions to act directly.
- Existing rules-first commands remain fast. Below-threshold predictions enter the existing Qwen interpreter; if it is unavailable or uncertain, existing clarification/safety behavior remains. High-confidence suspicious requests still get Qwen review.
- Eight focused regressions pass; full suite 452 passed in 7.90 s. No live voice/model invocation. Restart Otto to load the updated settings. Previously staged candidates require reevaluation because promotion fingerprints include zone settings.

### Word process identity after voice acceptance (11 Nov 2026, Codex)
- Installed-app lookup resolved Word correctly (100) and Microsoft Word to Word (90). The open-window matcher still used fuzzy title matching, which could identify an unrelated window as Word. Read-only inspection found a non-exact window above its 80-point threshold, but its process identity was unavailable in the sandbox, so the historical Antigravity target was not independently confirmed.
- Word/Microsoft Word/WINWORD now require WINWORD.EXE ownership, and never fall back to a document/workspace title. A missing Word window allows the existing installed Word launch path. Existing settings and aliases were preserved.
- Added nine fake-window regression cases, including launch-vs-focus behavior. Full suite: 444 passed in 7.52 s. No live app launch, close or typing performed. Restart Otto and say “Open Word” and “Open Microsoft Word” for native acceptance.
- User suggested later CRM integrations for account context. Structured messages/timestamps can support latest-message questions where service access permits. Screen question routing/counting and the WhatsApp screenshot's older-message selection are not fixed by this narrow change. Core app ownership and completion verification remain current work, independent of later connectors.

### Goal-mode completion and replay stabilization (11 Nov 2026, Codex)
- Continued from Fable's cd965ae on codex/goal-completion. Preserved the interpreter, answer mode, key allowlist, indicator, settings and saved-method data.
- Playback completion now requires a playing Spotify session plus the requested song/version/artist, or a uniquely named matching playlist Pause control. Removed loose word-overlap matching for Play goals. After the requested Play is dispatched, poll for completion and stop on uncertainty instead of choosing another song. Already-playing goals need no click.
- Qwen's done or yes/no completion judgment stops actions with an uncertain result, never verified success or a learned method. Code-observed typing and exact named-button tasks still verify. An unreadable text area is no longer treated as an empty document.
- Saved methods check completion after each step and stop early when the goal is observed. A completed button sequence alone earns no success. Partial/uncertain replay never restarts in the same task. Replay scores increment only after verified completion; unsuccessful runs retain the existing two-miss retirement policy. Saved methods containing key actions are not offered as incomplete button-only recipes.
- Every click attempt is recorded before dispatch, including failed responses and delayed/no UI changes. Repeated names are blocked within a task. Lost focus or unreadable UI is not counted as a successful window change.
- Focused checkpoints passed (30, 49, then 56 tests). Final suite: 435 passed in 6.17 s with temporary files outside OneDrive. One preceding full run had 434 passes and a WinError 5 replacing an audio test journal in the synced test folder; no audio runtime code changed.
- Native Spotify/Word/voice acceptance was not run in this batch. No model calls, training, data migration, model promotion, commit or push. Full app/version-bound method promotion remains R7, outside these four fixes.

### Goal mode: finishing, answers, keys; indicator colour (11 Nov 2026, Claude Code, main)
- Second live run by the user. Their question: is the weakness Qwen 8B, and does it need fine-tuning? Finding:
  mostly the loop, not the model. Evidence from their transcripts: "play my playlist number nine" pressed the
  right Play button and then kept going (no finished check); "how many playlists" pressed Playlists seven times
  (no answer action, no repeat guard); "you should check out" was typed into Word (Qwen's type_in_app accepted a
  whole stray sentence); "remove all the words" had no keyboard; "close word" had no verification.
- `core/goal_mode.py`: `ask_if_reached` (separate yes/no question after each window-changing step and after
  keys other than select-all; only when goal mode runs with the real model, so scripted tests stay
  deterministic), `same_thing` + media-session check as the code proof for "Play X", repeat-press guard,
  `answer` action (only when `is_question(goal)`), `key` action limited to KEYS (select_all, undo, escape,
  delete; delete only if the goal says delete/remove; max 4 keys; never into a password box; clearing a text
  area is code-verified by reading it back empty). Enter is deliberately not offered.
- Live hands-off trial (decisions only): finished? after "Play My playlist #9" with its Pause button showing ->
  True in 0.3 s; finished? for "open the settings page" after only the profile button -> False. For "How many
  playlists do I have?" Qwen first chose to expand the library rather than answer straight away; the full
  click-then-answer path was not run live.
- `core/interpreter.py`: type_in_app/new_note need a typing word in the sentence and text that is a proper part
  of it. NOT changed (differs from what was proposed): a non-yes/no reply to "Just checking..." still replaces
  the question with the new request, because that is existing, tested behaviour ("close Spotify" -> "what is
  the volume now?"); the typing guard is what stops stray remarks doing anything.
- `hands/spotify_desktop.py`: `playlist_names` adds the digit form of spoken numbers; `in_library` sends a
  no-artist "play X" to the playlist path when the open Spotify window lists a playlist of that name (exact, or
  >= 90 fuzzy). Only checks an already-open Spotify window.
- `core/executor.py`: close_app verified by the window disappearing within 3 s.
- `hands/win.find_window`: title matching now only looks at the last " - " part of the title. Found live: with
  Word closed, "Word" matched a Notepad tab titled "... in word hi I am.txt". This is the likely cause of the
  earlier unexplained "Google Docs came to the front for open word".
- `hands/indicator.py`: per-pixel alpha overlay (UpdateLayeredWindow), colour #1877c9, 18 px glow fading from
  the window edge, 0.25 s fade in/out, glow clamped to the screen for maximised windows. Checked live by photo.
- 418 tests pass.

### Qwen in the loop, indicator (11 Nov 2026, Claude Code, committed to main at the user's request)
- User merged PRs #4/#5 and reported the 1.2 voice checks as working. New instruction: commit straight to main,
  as kihurn, with no AI attribution.
- User's diagnosis, confirmed: Qwen was only consulted for Laya-unsure area guesses, per-area detail filling and
  inside goal mode; failures just returned a message. Direction agreed: Laya + rules for plain requests, Qwen
  for the rest, including conversation context.
- `core/interpreter.py`: `interpret()` (menu of 23 named choices, last 4 turns, last app, front window ->
  Intent via `to_intent`, which drops anything off the menu, unknown apps, and typed/written words the user
  did not actually say), `suspicious()` (fast answers that get a second look: no rule match, a note whose text
  is the whole request or has no note-like word, a file search starting with save/close/print/export..., a
  brain-picked play/pause for "change/skip/next"), `review()` (the supervisor's three choices).
- Pipeline: Laya high + clean rule = unchanged fast path. Laya high but suspicious, or Laya middle/low, goes to
  `_qwen()` first; sure -> act (safety gate still applies), unsure -> confirm question, clarify -> Otto asks.
  `_supervise()` runs after a failed/uncertain/needs-input plan (never in dry run, never twice, never after
  goal mode already gave up) and can re-run the request as an `app_goal`.
- Live hands-off trial with real Qwen (decisions only): "could you save this file" after opening Notepad ->
  apps.app_goal Notepad; "will you close the word" -> apps.close Word; "could you change the song" ->
  media.next; "can you open notepad" -> apps.open; "export this as a pdf" after opening Word -> app_goal Word;
  "how old is michael jordan" -> question (after tightening the web_search menu line); "do the thing" -> asks.
  0.3-0.5 s each once the model is warm (first call 1.2-2.2 s).
- Voice gate: a low-confidence reply is still rejected while a question is pending, except fixed phrases that
  cannot approve anything ("save that"/forget, "no", cancel). An existing test caught my first version, which
  also let a mumbled "yes" through; that stays blocked.
- Names: `spotify_desktop.closest_playlist` (library "Play <name>" buttons on the left 45% of the window,
  rapidfuzz ratio; >= 80 with a 12-point lead is used, 60-80 becomes a "Did you mean" confirm via
  `did_you_mean` data -> pending confirm_area). `ui_probe.closest` for near-miss control names (>= 85, 8 lead).
- `hands/indicator.py`: plain Win32 layered window (WS_EX_LAYERED|TRANSPARENT|NOACTIVATE|TOOLWINDOW|TOPMOST,
  colour key, excluded from capture). A Tk version was tried first and took keyboard focus when shown, which
  would have broken every foreground check; the Win32 one was checked live: focus did not move, and a capture
  with the hiding switched off showed the teal border around Notepad. Shown by `front_window`, pointed before
  each press/type, hidden when the request ends (and after 30 quiet seconds). Only for live tasks. Not checked:
  displays scaled above 100%.
- executor: `media_key` answers are treated as their own observation (they already verify state).
- Not run live end to end: interpreter/supervisor inside real requests, the pointer during real actions, the
  "did you mean" confirm. Slice 4 (pure-screenshot clicking for apps with no listed controls) still not built.
  395 tests pass.

### Goal mode, method saving, app context (11 Nov 2026, Claude Code, branch claude/any-app-control)
- User feedback after testing slices 1-2: fixed single clicks are too shallow (Word start screen, Save inside
  File, two clicks in one sentence). Approved direction: Qwen-heavy at first, learn and get faster with use.
- `core/goal_mode.py` (slice 3): loop of read controls -> Qwen picks {action, id, why} from a numbered list ->
  validate -> act -> re-read. Actions: click, type (the user's text only), done, stop. Limits: 8 steps, 45 s,
  two no-progress steps. Typing is still a code check first (no model when a text area is obvious). "done" from
  Qwen counts only after at least one step changed the window; `target_name` gives a code-checked finish for
  "click X". Risky names are never pressed from goal mode. Local models only (screen content never goes to cloud).
- Entry points: `type_in_app` with no place to type, `click_button` when the name isn't on screen, and the new
  `app_goal` action from the rule "<anything else> in <exactly installed app>" (apps area only). All skip goal
  mode unless there is a live task (so tests and dry runs never call a model). Setting `app_control.goal_mode`
  (default true).
- Live, hands-off trial with the real qwen3-vl:8b on the user's PC (nothing pressed): Notepad "press save" ->
  picked MenuItem File in 1.5 s (2.5 s with screenshot); Spotify "open the settings page" -> picked the profile
  button in 1.2 s (2.9 s with screenshot). Same picks with and without the image, so the marked screenshot
  (numbers drawn on the window, "set-of-marks" style) is only sent when fewer than 8 controls are listed or a
  step got nowhere. Research note: one web search confirmed 0-1000 normalised coordinates are the common
  convention for Qwen-based GUI models (already what core/computer_use.py uses); goal mode avoids coordinates
  entirely by having Qwen choose a control number.
- `core/methods.py` (slice 5 start, R7): otto-data/methods.json keyed app::goal, saved only on "save that",
  replayed by exact button name with no model call, two misses retire it. Not yet: several-success promotion,
  app-version binding.
- Context: pipeline remembers the last app acted in for 120 s; "click/press/tick/turn on/type ..." without an app
  gets it appended. Compiler: an app named at the end of a compound applies to earlier click-type parts.
- Voice "play my playlist called For the Rat" -> "could not read the Spotify window": NOT reproduced (matching
  works on the live window, from a thread too, and with single-threaded COM). Added per-thread COM start-up in
  ui_probe and the error's class in the reply and log so the next occurrence can be diagnosed. Also seen live:
  the expanded library shows a "Play <playlist>" button per row, which play_playlist already uses directly.
- Not run live: any goal-mode press or typing, "save that" replay. Slice 4 (pure-pixel clicking for apps with
  no listed controls) not built. 366 tests pass.

### Any-app control slice 2, playlists, now-playing (11 Nov 2026, Claude Code, branch claude/any-app-control)
- Slice 2: `click_button` now runs `app_control.click_named` (ui_probe list, unique-name rule, risky real-name
  stop, success only if the control list/title/foreground changed within 2 s). New rule-only actions `toggle`
  (TogglePattern, state read back; already-right presses nothing) and `set_field` (ValuePattern, read back,
  sensitive boxes refused). Rules in `details.control_intent` need an exactly-installed app name and only run
  when Laya picks the apps area (not pre-Laya, to avoid hijacking other requests). Safety gate: risky words in
  a toggle/field name need a yes; the text typed into set_field is not scanned. `pick_menu` from the plan is
  not built yet.
- Spotify desktop playlists (`spotify_desktop.play_playlist`): live read of the user's window showed the sidebar
  entry is a Button named "<playlist> <owner>" ("My playlist #9 Kihurn") and the playlist page has
  "Play My playlist #9". Otto presses the entry, then that button, and verifies by the button turning into
  "Pause My playlist #9" plus a playing Spotify session. ASSUMPTION not yet seen live: that the label really
  flips to "Pause <name>"; if not, Otto will say it could not confirm. Only playlists visible in the sidebar
  are found (the list is virtualised).
- `now_playing` is treated as its own observation in the executor (was "sent, but not verified").
- Not run live: any press, toggle, fill or playlist start. 348 tests pass.

### Any-app control, slice 1 (11 Nov 2026, Claude Code, branch claude/any-app-control)
- User asked for the Phase 1 plan and to start straight away, reviewing later. Plan: docs/PHASE1_ANY_APP_PLAN.md
  (five slices; only slice 1 is built). Nus Companion studied read-only at 592e30f; ideas ported, credited in
  THIRD_PARTY_NOTICES.md.
- Built: `hands/ui_probe.py` (one cached UIA FindAll per window: Notepad 26 controls/30 ms, Spotify 104/70 ms,
  Chrome 93/330 ms, measured live), `core/sensitive.py`, `hands/app_control.py` with `type_in_app`
  (for_brain=False). Rules: "open <app> and write X" and "type X in <app>" (exact installed app names only;
  Notepad/"note" still make an Otto note). This replaces the earlier interim "I can't type into Word yet" refusal.
- Decisions: a web page is a read-only "Document" and is never a typing target; without keyboard focus only a
  lone editor (Document) is chosen, never a lone small box such as Chrome's address bar; success needs the text
  to appear on read-back (count rises or length grows by 80% of the typed length, to allow auto-correct).
- Compound volume fix (on claude/live-check-fixes): "then lower it by thirty two" resolves "it" to the volume.
- Not run live: any real typing (it would have typed into the user's open notes). Word was minimised during
  the probe, so its document control is unconfirmed. Acceptance list is at the end of the plan. 331 tests pass.
- Next: user's slice 1 acceptance, then slice 2 (click/set/toggle by name with before/after proof).

### 1.2 live-check fixes (11 Nov 2026, Claude Code, branch claude/live-check-fixes)
- User's first live typed check: "play The Hills by The Weeknd" stopped with "Spotify search value did not match"
  although the box showed the right text. Measured on the user's Spotify: after SetValue the ComboBox keeps
  reporting the old text for 80–414 ms. `hands/spotify_search.py` now re-reads for up to ~2 s (40 × 50 ms).
  Not yet confirmed live: the Enter press and the song-card click that follow (they never ran before).
- "open a new tab on chrome and search hello world" compiled to find_files("new tab chrome") + web_search.
  Added `search_goals.new_tab()`; the compiler drops it before a web search, and alone it is open_site "new tab"
  (rule in `_web` and in the pipeline before Laya). Chrome opens a new *window* for `chrome://newtab` passed on
  the command line (seen live), so "new tab" opens https://www.google.com, which does open as a tab.
- open_site/web_search now carry their URL; the executor verifies them with `web.shown_in_chrome()` (Chrome's
  toolbar address bar via a native UIA FindFirst, ~11 ms live, guarded by `chrome_control_ok`; this also confirms
  the real UIA ancestry question left open by R1). Chrome need not be the foreground window. Unconfirmed wording
  is "Opening X. I couldn't confirm it loaded." Live: new-tab open verified True; Gmail/search wording still needs
  the user's re-run. 297 tests pass on Windows.
- Second live run (user): Spotify search confirmed working; "Over the Moon" played. "The Hills" stopped with
  "More than one matching Play button". Live probe: three candidates, all in the results grid (Top result "Play"
  plus two "Play The Hills" rows under Songs), not the suggestion dropdown. Decision (user approved): when several
  controls all match title and artist, press the highest on the page; Windows playback verification is unchanged.
  The old test that expected a stop was passing only by timing out; it now expects one press.
- "type hello world in note pad?" kept "in note pad?" in the note; the strip rule now accepts "note pad" and
  trailing punctuation. "open word and write X" made a Notepad note; the compiler now refuses with "I can't type
  into Word yet" unless the user says "note" or the app is Notepad. Real typing into apps is Phase 1 any-app control.
- Unexplained: the user reported Google Docs coming to the front for "open word"; their screenshot shows desktop
  Word. Ask for a screenshot if it recurs (win.find_window is fuzzy on window titles).
- Still open, found in the same run: the banner says "Otto 1.1" (bump at release). 302 tests pass on Windows.

### Review fixes R1–R6 and cleanup (11 Nov 2026, Claude Code, branch claude/review-fixes)
- Reproduced all six findings with fakes before fixing. R3: tie groups evaluated together, exact stored bar,
  `precision_at()` helper. R2: shared `serving_bars()` policy used by Router and the training gate; candidates judged
  at their own serving bar against the baseline's; promotion re-checks and refuses pre-fix candidates (gate_version 2).
  R1: `chrome_control_ok()` accepts only Chrome's toolbar Edit/Button, rejects anything under a web Document, and is
  re-checked before click/type and in verification; the new-tab page's search box is no longer a browser control.
  R4: `same_recording()`/`different_version()` (feat./remaster ignored, live/remix/sped-up etc. not); desktop play,
  visual verify and playback feedback use it; wrong version returns needs-input with an offer. R5: per-session error
  isolation, failed receipts kept and retried, bounded enumeration retries, three restore passes on exit; journal
  failure still blocks the change. R6: "save that" without an Intent explains instead of crashing.
- Cleanup: removed `tool.cmd`; README brought up to date. 279 tests pass (Linux). Not run on Windows: any of the
  live checks; Chrome's real UIA ancestry for the address bar should be confirmed in the first visual-mode test.
- R7 postponed (user decision). Roadmap realigned toward a Nūs-style Jarvis + companion (AGENTS.md section 8).

### D, E and F implementation and validation (11 Nov 2026, Codex/Sol)
- D: audio output inventory/current output, named switching and stable-ID selection, independent role readback, and undo if the active selection still matches. Windows discovery reported one Realtek speaker endpoint. Two-device switch, ambiguity, disconnect and manual-change-safe undo validated with a fake provider. A physical switch still needs a second active endpoint. Core Audio role readback uses IMMDeviceEnumerator and switching uses installed pycaw SetDefaultDevice.
- D: timers now verify the scheduled entry/thread, notes reserve unique names and verify written contents, and file search checks returned paths exist. Newly opened app windows are focused before the runner checks foreground identity. Arbitrary document launches remain dispatched where no exact-path observer is available.
- D: live Qwen diagnosis found invalid action arguments, UIA wrapper text differing from accessible names, repeated query entry, coordinate scale errors and similarly named playlists. Added structured Ollama output schema, direct named field readback/submission, explicit 0–1000 model coordinates, and matching-song controls. Live Chrome verified the requested Google URL. Live Spotify dispatched a click and Windows verified The Hills. Spotify started from an already displayed search, so fresh-start acceptance remains outstanding. D passed 242 tests before E.
- E: per-session 20% cap worker with push-to-talk and spoken reply leases, original-value restoration, user override protection, endpoint changes, and an interrupted-process journal. Verified the actual cap and restoration on three real Windows sessions, plus simulated muted/quiet/new sessions and output change. E passed 247 tests before F. A complete microphone-to-reply run and physical endpoint change still need user acceptance.
- F: `otto train --offline --tasks N --seed S [--baseline ID]` runs the real rules and executor with injected simulated effects. Generates review-only example proposals and manifest, scenarios, metrics and Markdown report. Initial coverage is seeded volume/timer requests, compounds, invalid plans and first-step failure. No model generates or judges these cases. Two matching 100-task runs passed 100/100 with zero regressions. Reports are under otto-data/training.
- F: startup restores saved calibration even when examples changed. Candidate training fits a separate agent and evaluates the same checked rows before/after. It saves and reloads a versioned artifact, checks confident decision precision and individual regressions, and stages without activation. Explicit promote validates artifact/dataset/baseline/zone fingerprints under a writer lock, then changes an atomic pointer. Rollback restores the previous artifact. Real candidate training scored 96% before and after on 100 checked requests, with 323 training examples. No model was promoted.
- Final suite: 251 tests passed, three existing COM warnings. Promotion/rollback exercised with isolated artifacts. No final Astra review or release was performed.
- Final live candidate `7c9d9c295f0146cb9287c261cca58d37` has matching artifact and zone fingerprints. Active calibration digest still matches the evaluated baseline. Comparable offline report: `otto-data/training/af9a69c5d93b419693b3ae4778655413/REPORT.md`.

### Visual-mode live failure diagnosis (11 Nov 2026, Codex/Sol)
- Local logs confirmed correct routing. Several failed requests ended after about eight seconds with NoBrainAvailable, consistent with the inference deadline. A later Chrome request logged ValueError with its cause discarded. The exact historical reasons are unavailable.
- A synthetic 1280×800 image probe returned valid local-Qwen JSON in 1.56s. This checks connectivity and image handling, not desktop actions.
- First image gets up to 18s, later images keep 8s, within the existing 45s task budget. Snapshot age limit is 20s with unchanged live identity/region checks. Removed sample click coordinates that the synthetic probe copied. Model and known target failures now yield specific messages and sanitized reason codes.
- 234 tests passed in 6.49s with three existing COM warnings. Live visual control is still at D2 acceptance before Astra review. D1 audio-output switching remains pending.

### Approved Qwen window controller (11 Nov 2026, Codex/Sol)
- Added core/computer_use.py and hands/window_control.py. Explicit “use Qwen to play…”/“use Qwen to search…” requests enter a named visual_task through registry/safety/executor. Local-only Qwen receives window snapshots and proposes one schema-validated action at a time.
- Provider supports task-scoped click, scroll, original-query value entry/readback and Enter only with verified field focus/value. Clicks must independently match supported search/play/tab roles; arbitrary inaccessible controls, settings and sensitive actions are not permitted. Pixel targets are normalized, hit-tested and checked against current region pixels/geometry/process. No unrestricted general-purpose desktop clicking is claimed.
- Completion uses Windows Spotify title/artist/playing state or Chrome Google-search URL/query. Model done does not verify success. Six actions within existing 45s task budget; no effect after stale target/cancel/revision changes; goal rechecked after inference to avoid redundant clicks.
- Screenshot capture stops when sampled window areas are obscured; captures remain in memory. This is not a formal proof of zero occlusion. No model-weight training or recipe activation added.
- New-install and current-user computer_use.enabled remain false. Explicit opt-in and live acceptance checklist added; normal requests continue on existing routes. No actual model/window-control acceptance performed in this batch.
- 230 tests passed in 5.40s, with three existing COM warnings. Fake-provider/schema tests cover invalid proposals, stale snapshots, cancellation, per-action observation, action budget and independent success. Native provider/DPI/overlay/live Qwen acceptance remains pending; Astra review before broader rollout.

### Qwen computer-use proposal (11 Nov 2026, Codex/Sol)
- Added docs/QWEN_COMPUTER_USE_PLAN.md for the requested full observe/propose/act/verify controller, extending candidate-only Spotify recovery to bounded window visual targets.
- First scope: Spotify and Chrome; task-owned actions, snapshot/geometry/ownership checks, original request text and independent completion verification. General settings remain named capabilities under D1.
- Documentation only; implementation awaits the plan-before-code checkpoint required by AGENTS.md. No additional UI actions, dependency changes or tests in this proposal-only step.

### Compound numbers and live Spotify diagnosis (11 Nov 2026, Codex/Sol)
- Fixed tens-plus-ones parsing such as “thirty two” and “thirty-two”; relative 32 no longer falls back to 10.
- Used the computer-use skill to inspect Spotify live. Observed search is a settable ComboBox labelled What do you want to play; an unrelated hidden address field was also exposed during Ctrl+L. Existing Edit-only guards/recovery candidates were insufficient.
- Named ComboBox search now sets/readbacks the query directly. Enter is sent only with confirmed control keyboard focus. Focused search guards and Qwen candidate enumeration accept ComboBox alongside Edit.
- Live acceptance via the computer-use tool searched The Hills The Weeknd, clicked its matching song card, and observed The Hills by The Weeknd with Pause icon and advancing progress. This verifies manual/tool-assisted UI playback, not the complete patched Otto/voice pipeline; no claim of audible verification.
- 218 automated tests passed in 7.13s (three COM threading warnings). Tests cover compound amounts and direct ComboBox value setting without unverified global keystrokes. User should restart Otto before re-testing; D1 remains pending.

### D2 initial UIA-grounded recovery (10 Nov 2026, Codex/Sol)
- Added core/recovery.py: explicit foreground Spotify screenshot, PID/process-start/window-geometry binding, local-only Qwen 8B, strict snapshot/candidate-ID response, and pre-dispatch control identity/bounds/semantic/cancel checks. One attempt per step, two per task, within shared deadline; no screenshots saved.
- Connected search-focus and song-control recovery; completion still requires editable/non-password search observation or Windows track/artist playback observation. No pixel-only actions are enabled: inaccessible/unnamed fields can still stop safely. Broader visual grounding remains a D2 limitation, not a completed general vision agent.
- Fixed spelled-out numeric amounts including “by five” and “to seventy”; added direct explanation for the time-of-day greeting follow-up. Existing data/weights untouched.
- 217 tests passed in 5.24s, including fake screenshot/model/control integration, moved-window rejection and inference-time cancellation. Enabled recovery.enabled for this user's acceptance; defaults remain disabled. No real screenshots/model recovery/UI clicks tested in this batch. D1 audio-output work has not yet been implemented.
- Kernel warnings reviewed against upstream projects; no dependency/model changes made. Optimization is a separate compatibility/benchmark task.

### D0 (10 Nov 2026, Codex/Sol): recovery prerequisites
- Added core/audio_context.py: 120-second endpoint-bound volume referent. “Increase it up to 70” resolves to absolute volume; explicit “by 5” is relative. Unrelated topics, expiry and endpoint changes invalidate the referent; unknown targets ask rather than guessing. Dry-run uses a simulation-only endpoint.
- Added hands/spotify_search.py: bounded polling (up to 2s/20 observations) and distinct focus_lost/protected_field/not_editable/search_label_missing/uia_unavailable diagnostics. Rechecks before Select All, typing and Enter; logs only guard metadata, no screenshot or text content. Confirmed installed pywinauto exposes get_focused_element by reading its source.
- Added code-owned ContextVar runtime guards for task/revision/deadline/cancellation. Rechecked after progress narration and before generic/music dispatch and Windows focus/hotkey/type effects. Interruption does not dispatch the next effect.
- Removed generic READ-risk-to-verified promotion. Volume retains its explicit observer; other read actions conservatively remain unverified until their domain observer exists.
- 205 tests passed in 5.06s, including real volume phrase variants, context expiry/device change, cancellation/revision/deadline during progress, delayed Spotify focus and focus loss before typing. No real volume, microphone, Spotify UI or system settings changed in this batch.
- Next: user's D0 voice check, then D1 audio-output provider/inventory and verified switching on Sol. D2 visual recovery and F learning remain unimplemented.

### Astra recovery design checkpoint (10 Nov 2026)
- Added docs/V1_2_RECOVERY_DESIGN.md: bounded local-Qwen Spotify recovery, typed volume context, audio-device read/set/verify/undo contracts and candidate recipe promotion.
- Review blockers: undifferentiated Spotify field failures, screenshot helper's implicit target/focus behavior, cancellation gap after progress speech, generic READ-to-verified inference, and legacy recipes lacking recovery preconditions.
- Sequence: D0 diagnostics/context/dispatch guards; D1 audio-provider spike and verified output selection; D2 explicit-window recovery; Astra review before F candidate promotion. Full-system control and unrestricted vision loops are not enabled.
- Documentation only; no production code, system setting, desktop action, model training or candidate promotion changed during checkpoint.

### C3 and volume/Spotify follow-up (10 Nov 2026, Codex/Sol)
- Added read-only get_volume; “lower the volume down to 30” selects absolute 30, and “what is it now?” after a volume request reads rather than writes. Runner verifies volume against observed level; relative changes include a before observation.
- Spotify generic Play controls are bound to title/artist in a small card (bounded ancestors, never whole-page text). Wrong artists/ambiguous controls stop. Search now focuses/verifies the Spotify search Edit and types literal spaces, avoiding URI plus-sign interpretation. No live UI acceptance performed.
- Replaced executable string queue with core/compiler.py: quote-aware deterministic clauses compile to one validated action plan; fallback asks for named actions for the original request and requires confirmation for model-generated compound plans. No generated prose goes back through Laya. Every action plan now enters the same safety/runner path; invalid later steps cause zero effects.
- Added context.py requested/observed records; explicit volume follow-up; repeat only recent verified action plans. Bare unresolved action pronouns ask for a target. Model rewrite remains for file/note-style conversational clarification; no general entity resolver is claimed.
- Approvals snapshot plan/task revision, expire and are invalidated by replacement/cancel; low-confidence answers do not execute. Scoped Task is reused when approved. Cancellation/deadlines discard late success and stop dependencies. Brain calls and runner share a 45-second turn budget; OS calls are not forcefully interruptible.
- Added narrowly typed backward get_volume.volume -> set_volume.level reference support, resolved only from verified output and revalidated before dispatch. Other reference forms fail closed. File selections remain bounded pending snapshots; broader domain bindings await D.
- Simulation no longer saves recipes or increments recipe success; migrated the legacy recipe test to an explicit observed fake backend. Routing-label confirmation remains distinct from execution learning.
- Minimal live app-focus/volume observations allow those dependencies; other legacy actions are dispatched/unverified and stop the task until D adds domain verifiers. Timers may be scheduled but still return unverified; no auto-retries/duplicate mutations.
- 196 tests passed in 5.01s, including scoped approval/expiry/replacement, forward/unbound references, zero-effect invalid plans, late cancellation, volume reads, card identity, and literal-space guarded input. No mic, real volume or Spotify control test. Next: user's voice checklist, then D on Sol 6.1. Existing uncommitted work preserved, no commits or training.

### Desktop/search follow-up (10 Nov 2026, Codex/Sol)
- Added bounded Spotify desktop backend; selected spotify.playback_backend=desktop in this user's settings. API remains selectable. Desktop opens/searches Spotify, invokes only a unique visible named Play control matching title/artist, and verifies Spotify's Windows media session. No Spotify API calls. Missing/ambiguous controls stop; desktop Liked Songs/collections are not supported. Qwen screenshot clicking is deferred; this is named-control automation, not general Phase 3.
- Filler-only speech is ignored before confidence/pending handling. Meaningful requests containing fillers remain intact. Push mode records while Ctrl+Alt is held; wake-mode silence handling is unchanged.
- Explicit search rules bypass Laya. Narrow screen-plus-Chrome follow-up retains the recent explicit query (120s); general queue defects remain C3.
- Located running SearxNG Docker container on 127.0.0.1:8889 and configured this user's search.searxng_url. Live JSON check returned 36 results. Local failure does not silently send queries to cloud; current-information failure reports unavailable rather than answering from memory.
- 173 tests passed in 4.19s: fake unique/ambiguous UI controls, backend isolation, accent normalization, fillers and Chrome transcript. No live desktop clicks/mic acceptance. Preserved existing learned data; no retraining.

### C2 live diagnosis follow-up (10 Nov 2026, Codex/Sol)
- User reports no playback, truncated UI search and no reopen. Read-only live checks: device endpoint 200; player endpoint 204 with empty body. One requested Over the Moon dispatch was accepted, but later observations remained empty. Explicit activation/transfer followed by playback also left player state empty; no transfer recovery added because it did not help.
- This rules out a simple universally invalid token, but does not prove account/player playback health. Root cause of accepted-but-idle API playback remains unresolved; next acceptance asks user to start a song manually and retry.
- Fixed raw-space Spotify search URI encoding and explicitly launch/focus Spotify before selecting an API device. Added dispatch status and final observed-state diagnostics instead of suppressing the rejection evidence. No credentials printed/logged.
- Baseline 156 tests passed after fixes; added regression cases for full encoded query and opening despite a listed device. Physical UI search and live playback still require acceptance.

### 1.2 C2 (10 Nov 2026, Codex/Sol): first verified Spotify runner path
- Added core/executor.py, entered through the existing validation/risk gate for plans containing play_music/play_liked. Tracks task outcomes, stops dependent steps on uncertainty/failure, and keeps simulation/evaluation free of backend effects and verified success.
- Spotify polling checks track URI (including linked_from), collection context or explicit Liked Songs selection, playing state and chosen device. Wrong/missing observations never yield Playing. Verification waits up to 6s within a shared 45s runner budget; network requests honor remaining budget. Planning before the runner is not covered yet.
- Device selection no longer prefers an arbitrary active phone. Configured name/local computer or a single computer is required. Matching now uses minimum title/artist scores and rejects close same-title/different-artist track candidates.
- Empty/204 API success is accepted; malformed JSON objects become sanitized connector failures. Uncertain post-dispatch responses trigger observation, never blind retry. Added safe decode metadata and structured task-step logs.
- Spoken progress wired to CLI. Ctrl+Alt while a music task runs requests cancellation; Ctrl+C quits. In-flight calls are not forcibly interrupted. Voice cancellation words are processed only after the synchronous task returns.
- Failure feedback observes the recent target and does not rewrite/replay. Music execution clears unrelated training context; simulated music does not update recipe success. Liked Songs starts/verifies up to 50 explicit saved tracks rather than claiming full-library shuffle.
- 156 automated tests passed in 3.73s; no live Spotify, audio or microphone tests. C2 live checklist added to docs/V1_2_VOICE_TESTS.md.
- Remaining C3: whole-request compilation outside narrow music forms, full task-bound pending/approval/reference resolution, general context and cancellation integration. Nonmusic actions in a music plan remain dispatched/unverified and stop dependencies until D verifiers exist. No model switch needed before C3; live music acceptance first.

### Voice hotkey follow-up (10 Nov 2026, Codex/Sol)
- User requested Ctrl+Alt push-to-talk. Added modifier-chord support, physical-key tracking, repeat suppression and release of either required modifier; F9 mute retained.
- Set this user's listen.push_to_talk_key to ctrl+alt and changed the new-install default; existing other user overrides are preserved (no global migration).
- Added narrow “Spotify and search…” voice-prefix normalization to avoid duplicate split playback. 135 tests passed in 3.54s; physical keyboard/microphone acceptance remains manual.

### C1 voice follow-up (10 Nov 2026, Codex/Sol)
- Reproduced supplied missing-play, Spotify-comma and “No, I want you to search…” forms; deterministic search targeting now covers them.
- Explicit Spotify goals bypass follow-up rewriting and clear unrelated pending training context, preventing a search from becoming playback or teaching the old pending label.
- Preserved search-and-play behavior with regression coverage. 132 tests pass in 3.66s; no live voice/playback checks performed.
- User requests spoken step progress; carry into C2 with announcements before actions and observed completion before dependent steps. API playback need not expose UI search as a separate goal.

### 1.2 C1 (10 Nov 2026, Codex/Sol): music compilation and contract corrections
- Added deterministic Spotify workflow compilation into a single Intent with explicit title/artist or app/query; search-only remains search-only and independent extra goals remain separate.
- Unbound ordinal song references are blocked before dispatch; quoted Queue titles work. Legacy splitter now rejects malformed/oversized lists rather than coercing/truncating.
- Registry numeric constraints are action-specific; builtin timer/volume values are validated without hiding raw types. Recipe placeholder expansion is single-pass and checks missing parameters, preserving literal note text.
- Added code-owned lifecycle protocol/recovery policy and guarded task transitions for C2; these are not yet integrated into live execution.
- 128 tests passed in 3.09s. No real mic or Spotify checks. Next: C2 runner and Spotify verification on Sol; voice checklist in docs/V1_2_VOICE_TESTS.md.

### 1.2 Review 1 (10 Nov 2026, Codex/Astra): contracts and live failure review
- Added docs/V1_2_REVIEW_1.md with prioritized findings and transcript-based acceptance specifications; these new cases are not implemented tests yet.
- Confirmed outer string queue bypasses whole-task validation and loses app/entity context; playback claims still use unverified legacy success.
- Require raw argument validation, scoped references/pending replies, observation-based replies, failure feedback and sanitized Spotify JSON diagnostics.
- Revised sequence: C1 contract/music compilation, C2 runner plus minimum Spotify verification, C3 remaining integration, D remaining domain verifiers. Audio/evaluation and Phase 2 scope unchanged.
- Review rerun: 113 tests passed in 3.13s with permission for the fake localhost server; sandbox-only run had 112 passes and one localhost reachability failure.
- Documentation only; no production code, playback, training or runtime-data changes. Next model checkpoint: Sol 6.1 for C1.

### 1.2 Batch B (10 Nov 2026, Codex): contracts and plan validation
- Added core/tasks.py: task/step records, explicit outcomes, observation evidence and pending/prepared records. These are not yet the live task runner.
- Added conservative Result.to_outcome(): legacy success is dispatched; dry-run is simulated; verified outcomes require evidence.
- Whole-plan validation now runs before risk checks or execution, for builtins, recipes and model plans. Unknown fields/actions, missing arguments, invalid types/enums/ranges, malformed clocks, nonfinite numbers, duplicate IDs and oversized plans are rejected.
- Model plans are no longer silently truncated or stripped of unknown arguments. Brain-only action restrictions are enforced.
- Backward output references are rejected until Batch C can resolve and authorize them; no partial reference implementation executes.
- 113 tests passed (73 previous + 40 contract/validation cases), including proof of zero action calls when a later step is invalid. No live desktop checks.
- Next checkpoint: Astra review of contracts and runner integration before Batch C. Existing queue/result behaviour outside validation remains 1.1; full verified execution is pending.

### 1.2 Batch A (10 Nov 2026, Codex): baseline and music routing
- Imported the supplied tests, development requirements and shared agent instructions.
- Created codex/otto-1.2 while preserving inherited uncommitted 1.1 changes; no commits made.
- Baseline: 58 passed. After changes: 73 passed using Otto's Python 3.12 and isolated temporary data.
- Music-to-game shortcuts now require an exact installed name/alias in routing.play_game_apps. Bruno Mars no longer fuzzy-matches Run.
- Full corrected commands bypass follow-up rewriting. Compound detection precedes music parsing and ignores quoted title content.
- Unsupported queue requests explain the limitation rather than starting playback.
- Remaining: outcome contracts, task runner, playback verification, context, ducking and offline evaluation. No live desktop/playback checks performed.

### 1.1 (10 Nov 2026, Claude Code): delivered, waiting for Windows confirmation
Spotify Web API (play song/artist/album/own playlists/Liked Songs, what's playing), honest play/pause with result
checks (Spotify API + Windows media sessions), follow-up rewriting with conversation history, "do that again",
multi-step splitting, the Otto brief (`otto-data/brief.md`), shorter replies + speed 1.15, listening modes (Hey Otto /
always / push-to-talk F8, mute F9), `otto mic`, one `otto` command with settings sub-commands, `otto check`, `.env`
keys, file search limited to user folders, open_app window check. Tests added (`tests/`, 58 passing).

### 1.0 (10 Nov 2026, Claude Code): delivered and used by the user
Laya areas + three confidence zones, clarify questions, brain fallback via C0RE, rules for details, planner with
recipes, safety gate, Hands (apps, media keys, Chrome, Everything, notes, timers), screen/clipboard via Gemma,
Kokoro voice, Whisper ears, learning loop (examples, test set, keep-if-better), logs.
User feedback (fixed in 1.1): see AGENTS.md section 7.

### Phase 0 (9–10 Nov 2026, Claude Code): checks on the user's PC
- C0RE reachable; `gemma4:31b-cloud` ~1 s, reads images, wraps JSON in ``` fences; Qwen 8B fast and exact for JSON;
  DeepSeek/GLM/Kimi cloud = HTTP 402 (not on the free plan).
- Laya fast model: 31 ms on GPU, 34% untrained. Trainable engine (vegaml): ~60 ms, 1.6 GB VRAM, fit in ~11 s on GPU.
  Accuracy with 8 / 15 / 22 examples per area: 75% / 80% / 89%. Its built-in AUTO signal becomes useless
  (says AUTO on everything) as it learns, hence our own confidence bars.
- Whisper large-v3-turbo int8 on GPU: ~0.5 s per sentence. Needed `av<19` (PyAV 19 broke faster-whisper 1.2.1).
- Everything fits in 12 GB VRAM (Laya + Whisper + Qwen 8B ≈ 9–10 GB).
- With 297 examples, Laya scored 97% on the 100-request test set; mistakes at 85–99% confidence
  ("bruh" → unsure, "add a client called tom" → notes, "whats on my calendar" → screen).

## Decisions (and why)
- **Laya + code + brain-as-fallback, not one big agent:** Hermes 3 8B with 24 tools confused tools, refused desktop
  actions and couldn't chain steps.
- **Gemma 4 cloud for thinking/screen/answers; Qwen 8B for extraction and chat:** Qwen was faster and exact.
- **No local 14B:** doesn't fit next to Laya + Whisper in 12 GB; no 14B Qwen reads images; Gemma 31B covers hard thinking.
- **Python 3.12:** Kokoro doesn't support 3.14.
- **Kokoro for voice** (VoiceStudio optional later for a custom voice); voices Bella/Michael.
- **Chrome** for all web. Uninstalled apps get "X isn't installed".
- **Three confidence zones** + floors, measured on the test set; ask once, short yes/no replies understood.
- **"Hey Otto"** default trigger, plus always / push-to-talk modes and a mute key.
- **Training mode** will check results with code first, Gemma screenshot judge second; user approves before learning.
- **Keys in `.env`**, in the OneDrive project folder for now (user's choice; may move to `C:\Users\User\.otto\.env`).
- Otto replaces the user's earlier "Lenz" idea (screen-aware assistant) in Phase 3.
