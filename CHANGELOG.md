# Changelog

## 1.2 (in development)
- New core wired in behind `core.agent` (off by default): simple whole sentences go the fast way (Laya + rules),
  everything else to the Qwen agent loop, which can ask you a question or wait for your yes. Try it with
  `otto eval --core new` or `otto set core.agent true`.
- New core under way (one local Qwen loop with tools). First step: 32k context on every model call, local
  models only (Gemma 4 cloud removed from all model lists, including yours), and a multi-turn chat for the loop.
- Set this user's Laya acting minimum to 90%. Enforce the configured floor for all calibration modes and route middle-confidence split requests through Qwen too. Full suite passes 452 tests.
- Word window lookup requires WINWORD.EXE ownership, preventing unrelated workspace/document titles from matching Word or Microsoft Word. Nine regressions added; full suite passes 444 tests. Native voice acceptance pending.
- Goal-mode completion/replay stabilization (435 tests pass): verify Spotify's requested playback, stop on unconfirmed Play, treat Qwen completion as uncertain, verify saved-method outcomes, and prevent retries of dispatched clicks. Partial replays stop without restarting. Settings and saved data are preserved; live acceptance pending.
- Goal mode fixes from the second live run (418 tests pass; not yet re-run live):
  - Knows when it is finished: a code check where one exists (the asked-for "Play …" button was pressed and
    Windows reports music playing), otherwise Qwen is asked a separate yes/no "is the goal reached?" after each
    step. The same control is never pressed twice in one task.
  - Questions get answers: "how many playlists do I have" lets Qwen read the listed controls and reply.
  - A few safe keys: select all, undo, Escape, and Delete only when your request was to delete or remove
    (which already asks "Just checking…"). No Enter, because Enter can mean Send.
  - Stray speech is never typed: Qwen may type or write only when you used a typing word and the text is part
    of what you said.
  - Spotify: "number nine" means "#9"; "play for the rat" plays your playlist of that name if you have one.
  - Closing an app is confirmed by its window going away ("Closed Word."), or Otto says it is still open.
  - Finding an app's window no longer matches other windows that merely mention its name (a Notepad file
    called "… in word …" was being treated as Word).
- Indicator is now blue (#1877c9) with a soft fade.
- Qwen in the loop (395 tests pass; real requests through it not yet run live):
  - Interpreter: when Laya is unsure, or the rules have no answer or an odd one, local Qwen reads the request
    with the last few turns, the last app used and the window in front, and picks one of Otto's named actions.
    "Can you save this file" after "open notepad" now means save in Notepad. Laya and the rules still handle
    plain requests on their own.
  - Supervisor: when a step fails or can't be confirmed, Qwen chooses between working it out in the app (goal
    mode), asking you one specific question, or leaving the reply as it is. One attempt per request.
  - Misheard names: "for the rack" finds your playlist "for the rat"; a weaker match asks "Did you mean…?".
    Nearly-right button names are matched when one is clearly nearest.
  - "In notepad, can you click view then click status?" works with the app named first.
  - A quiet "save that", "no" or "cancel" is accepted; a quiet "yes" still is not.
  - "Change the song" skips to the next track and says what is playing.
- Indicator: a teal glow around the window Otto is operating and a small Otto pointer that glides to each
  control it uses. Click-through, never takes focus, hidden from screenshots, gone when the task ends.
- Goal mode (any-app control, slice 3; 366 tests pass; real pressing not yet run live):
  - When a fixed rule can't finish the job, local Qwen picks the next step by number from the window's real
    buttons and boxes; Otto checks the pick, does it, and looks again (up to 8 steps). Examples: typing in Word
    from its start screen, "click save in notepad" (File, then Save), "export this as a pdf in word".
  - Qwen can't type its own words, can't pick anything that isn't on screen, and Send/Delete-type buttons and
    password boxes are refused. If Qwen is unsure, Otto asks you for the next step.
  - A screenshot with the same numbers drawn on it is added when the list is short or a step got nowhere.
  - After a worked-out success, say "save that": next time Otto replays the steps without Qwen.
- "click view then click status in notepad" clicks both in Notepad; "click status" right after working in an
  app means that app again (for two minutes).
- Spotify playlist errors now name what went wrong instead of only "could not read the Spotify window".
- Any-app control, slice 2 (348 tests pass; not yet run live):
  - "click X in <app>" now reads the window quickly, stops if two controls share the name, and only says
    "Clicked" when the window visibly reacted.
  - New: "turn on/off X in <app>", "tick/untick X in <app>" (reads the switch back) and "set X to Y in <app>"
    (fills a named box and reads it back). Password and private boxes are refused.
- Spotify (desktop mode): "play my playlist #9" opens the playlist from Your Library and presses its Play button.
- "What's playing right now?" answers with the song instead of "sent, but not verified".
- Any-app control, slice 1 (331 tests pass; live typing not yet confirmed on Windows):
  - "open Word and write …" and "type … in Word" type the words into that app and read them back to confirm,
    instead of making a Notepad note. Otto refuses password and private fields and says so when it can't see
    where to type.
  - New reader for any app's buttons, boxes and tabs (no screenshot; 30–330 ms on the user's PC).
  - Plan for the remaining slices: docs/PHASE1_ANY_APP_PLAN.md. Credits: THIRD_PARTY_NOTICES.md.
- "set volume to 70, then lower it by thirty two" now lowers by 32, not 10.
- Fixes from the second live run (302 tests pass):
  - Spotify: the same song listed twice (Top result and again under Songs) no longer stops with "More than one
    matching Play button"; Otto presses the top one and still checks what Windows says is playing.
  - "type hello world in note pad?" writes just "hello world".
- Fixes from the first live Windows check:
  - Spotify: "Spotify search value did not match." Spotify reports its search text 80–400 ms after it is set;
    Otto now re-reads for up to ~2 seconds before giving up.
  - "Open a new tab on chrome and search hello world" no longer searches your files for "new tab chrome"; it is
    one Google search. "Open a new tab" alone opens Google in a new Chrome tab.
  - Opening a site or a Google search is confirmed from Chrome's own address bar ("Opened gmail."). If it can't
    be confirmed Otto says "Opening gmail. I couldn't confirm it loaded." instead of "sent but not verified".
- Review fixes (R1–R6, see docs/V1_2_FINAL_REVIEW.md), each with regression tests (279 tests pass):
  - Confidence bars judge equal-confidence answers as one group and are stored exactly (R3).
  - A newly trained Laya is approved at the bar it will really use, and re-checked at promotion. Candidates staged
    before this fix must be re-evaluated with `otto candidate` (R2).
  - Visual control in Chrome only uses Chrome's own address bar and New tab button, never look-alike page content,
    and re-checks right before clicking or typing (R1).
  - Spotify success needs the exact recording: a live, remix or sped-up version is reported, with an offer to find
    the original (R4).
  - Audio ducking restores every app it can even when one app's audio session has ended (R5).
  - "save that" after multi-step, screen-control or audio-output tasks explains it can't save those yet (R6).
  - R7 (learning reusable screen-control methods) is postponed to the any-app control phase.
- Removed the obsolete `tool.cmd`; README updated for git updates, Ctrl+Alt push-to-talk, training commands,
  audio outputs and opt-in screen control.
- Final D–F review records seven open findings in docs/V1_2_FINAL_REVIEW.md. Release readiness is withheld; recovery-recipe learning remains unimplemented.
- Cleanup removes unused execution scaffolding/imports and the redundant visual Enter action, consolidates the root architecture link, and clears generated pytest folders. Cleanup validation passes 252 tests with three existing COM warnings.
- D adds verified media output selection and undo, timer/note/file observations, and fixes for live Qwen Chrome and Spotify control.
- E adds per-app audio ducking with leases and recovery of unchanged session volumes. Verified cap and restore on three Windows sessions.
- F adds offline simulated practice and baseline reports, isolated Laya candidates, explicit fingerprint-checked promotion and rollback. Active calibration remains unchanged pending review.
- Visual mode reports model and target failures separately and allows up to 18 seconds for the first image within the task deadline. 234 tests pass.
- Added opt-in local-Qwen Spotify/Chrome window controller with one-action screenshot loop, bounded native controls, independent result checks and explicit “use Qwen to…” routing. 230 tests pass; live acceptance pending.
- Added a reviewable Qwen window computer-use implementation proposal; controller implementation remains pending scope approval.
- Fixed compound spoken volume numbers and Spotify's observed ComboBox search control; queries use direct value setting/readback. Live tool-assisted playback of The Hills confirmed; full Otto re-test pending. 218 tests pass.
- Initial D2 Spotify recovery uses local Qwen screenshots to select safe UIA controls, bounded by snapshot identity and attempt limits. Pixel-only actions remain unsupported. Fix spelled volume amounts; 217 tests pass, live recovery acceptance pending.
- D0: endpoint-bound volume follow-ups, explicit by/to amounts, bounded Spotify search-field polling with diagnostic reason codes, immediate dispatch guards and conservative read verification. 205 automated tests pass; live voice acceptance pending.
- Completed Astra design checkpoint for bounded Spotify visual recovery, volume context, system audio outputs and candidate recipe learning; implementation remains D0–D2/F.
- C3: compile compounds into one validated task; shared runner, scoped approvals/context, conservative dependency stopping, deadline-aware brain calls and no simulated recipe promotion. Minimal typed volume-output references are supported; broader verifiers remain D.
- Fix absolute volume targets/read-only volume questions and Spotify generic Play-card matching. Spotify desktop search now types literal spaces into a verified search field. 196 tests pass; live voice acceptance pending.
- Added desktop Spotify backend using named controls and Windows media verification, explicit Chrome search routing, filler-only suppression and internal SearxNG search. This user's desktop backend and local search port 8889 are configured. 173 tests pass; desktop acceptance pending.
- C2 live follow-up: encode complete Spotify search URIs, launch the desktop app even when a device is cached/listed, and report accepted-but-empty playback separately from dispatch errors. Live API playback issue remains under diagnosis.
- C2: Spotify task runner verifies identity, playing state and device before success; spoken progress, interruption requests, failure-feedback observations and sanitized JSON decode errors. Liked Songs verifies an explicit selection of up to 50 tracks. 156 tests pass; live voice acceptance pending.
- Push-to-talk supports modifier chords, with Ctrl+Alt as the new default and this user's setting. Narrow Spotify voice-prefix recovery avoids duplicate playback plans. 135 tests pass.
- Voice follow-up: preserve Spotify search intent with punctuation, search-only setup and “I want you to” corrections; clear unrelated pending learning context. 132 tests pass.
- C1: compile explicit Spotify search/play workflows into one music goal; preserve search-only app targets, reject unbound result references and malformed split lists, validate raw numeric arguments and recipe expansion. 128 automated tests pass; live verification awaits C2.
- Completed Review 1 against the live Spotify transcripts; documented contract gaps, regression acceptance cases and a revised runner/Spotify integration sequence. No runtime fixes in this review.
- Added task/outcome records and conservative conversion of legacy results; these await runner integration.
- Validate complete action plans before execution, rejecting invalid parameters, unknown fields, duplicate IDs and excessive steps. Model plans are never silently shortened or filtered.
- Contract and routing suite: 113 tests passing. Live playback verification and task lifecycle integration remain pending.
- Imported the 58 supplied regression tests and added 15 routing cases (73 passing).
- Prevented music requests such as Bruno Mars from fuzzy-matching installed apps such as Run.
- Exact configured game names and aliases still launch games; explicit song requests remain music.
- Complete corrected commands keep their new target without model rewriting.
- Music followed by another command is detected before music extraction; quoted titles are preserved.
- Queue requests explain that enqueueing is not supported yet.
- Playback verification and the new task runner are still pending; this is not the complete 1.2 release.

## 1.1 (November 2026)

**Music**
- Spotify through the official API (Premium): play a song, "song by artist", artist, album, your own
  playlists, your Liked Songs (shuffled), and "what's playing". `otto spotify` connects it once.
- Play/pause/skip use Spotify or Windows' own media controls, and check the result: no more "Done."
  when nothing happened. If nothing is loaded, Otto offers your Liked Songs.
- Spotify search links no longer show "lofi+beats".
- "play valorant" opens the game; "play the hills" plays the song.

**Conversation**
- Follow-ups: "its called student resume", "more", "the second one" are rewritten into full requests
  using the last few exchanges ("understood as" in the grey line).
- "do that again" repeats the last real request.
- Multi-step requests ("open discord, then set a timer and google X") are split and run in order.
- The Otto brief (`otto-data\brief.md`): one shared, editable set of instructions for every brain call.
- Shorter replies, talking speed 1.15.

**Voice**
- Listening modes: "Hey Otto" wake phrase (default), always listening, push-to-talk (hold F8).
- F9 mutes; "stop listening" mutes.
- Choose the microphone with `otto mic`.

**Everything else**
- One `otto` command for everything (replaces otto.cmd options and tool.cmd), added to your PATH.
- Change settings from the command line or while running (`:speed 1.2`, `:voice michael`, `:mic 3`, `:model ...`).
- `otto check` health check.
- Keys from a `.env` file.
- File search only looks in your own folders, documents first, and skips program/code folders.
- Opening an app checks that its window appeared, and brings it forward if it was already open.
- New settings only store what you change, so improved defaults reach you automatically.

## 1.0 (November 2026)
First Phase 1 build: Laya areas, three confidence zones, brain fallback through C0RE, Hands, recipes,
safety levels, Kokoro voice, Whisper ears, test set and learning loop.
