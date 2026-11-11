# Otto work log

Shared by every agent (Claude Code, Codex) and the user. Newest first inside each section.

## In progress
- [codex] D–F code review and confirmed dead-code/generated-file cleanup – started 2026-11-11 (review report, focused regressions, documentation).
<!-- Claim before starting: - [agent] task – started YYYY-MM-DD (files you expect to touch) -->

## Next up
- One final Astra review of D–F, including native acceptance gaps, promotion safeguards and release readiness. Keep the current Laya calibration active until a candidate is explicitly reviewed and promoted.

## Done

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
