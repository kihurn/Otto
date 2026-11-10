# Otto 1.2 technical design

Status: approved for implementation; Batch A completed (73 tests passing). Prepared 10 November 2026.
This document specifies intended changes; it does not describe features already implemented.

## 1. Release goal and boundaries

Otto should interpret common requests correctly, verify supported outcomes, and stop or recover when a step fails. A successful command submission is not automatically a successful user task.

Included: music/app disambiguation, Spotify verification, a sequential task runner, corrections and bounded context, audio ducking, safe Laya candidate promotion, and offline practice/evaluation reports.

Deferred: unattended desktop training, Qwen weight fine-tuning, a general OCR/vision judge, automatic code editing by the trainer, arbitrary visual workflows, and SearXNG (a separate follow-up). Phase 2 remains the local API and Tauri mascot/overlay. Phase 3 remains pointing and broader screen guidance. The 1.2 task events will support those interfaces without building them now.

Retain Python, existing named actions, Laya area routing, the C0RE client and configurable model chains. No replacement agent framework, database migration, or second desktop executor is needed.

## 2. Baseline findings

| Current implementation | Consequence | Design response |
|---|---|---|
| `pipeline._clear_music()` converts fuzzy app matches scoring at least 90 into launches | Bruno Mars can become Run; this bypasses Laya | Exact/explicit game resolution only |
| `hands.media.play_music()` reports success after submitting playback | Wrong or unchanged playback can be reported as success | Resolve, execute, then observe target playback |
| Music parsing precedes compound-request handling | Later commands can become part of the music query | Detect independent clauses before the music shortcut |
| `Otto.queue` is a list of text requests; continuation checks only pending questions | Failure/cancellation can leave subsequent work runnable | One task runner owns all advancement |
| `Result.ok` mixes command acceptance and user-goal success | Replies, recipe scores and learning can reward incomplete work | Explicit outcomes and evidence |
| Brain plan validation drops unknown arguments and truncates oversized lists | A changed or partial plan may execute silently | Reject the whole invalid plan |
| Pending replies are processed before speech confidence checks | A low-confidence approval can execute a pending plan | Validate action approvals before consuming them |
| Startup training uses `force=True` after example changes | A worse candidate can replace the saved model | Separate training from promotion |
| History marks a turn as performed when a plan exists | Failed work may be repeated or used as factual context | Record observed outcomes separately |

The working tree already contains substantial 1.1 changes and deletions. Preserve them. Supplied tests are in `C:/Users/User/Downloads/otto-handover/tests/`; they are not yet in this workspace. The installed Otto Python currently lacks pytest. Tests have been read, not executed for this design.

## 3. Module ownership

| Module | Responsibility after 1.2 |
|---|---|
| `core/pipeline.py` | Interpret a turn, resolve conversation references, create/resume/cancel a task, produce a reply |
| `core/tasks.py` (new) | Dataclasses/enums for task, step, outcomes, evidence, pending questions and approvals |
| `core/executor.py` (new) | Single sequential runner, cancellation, deadlines, result aggregation and bounded recovery |
| `core/planner.py` | Compile intents/recipes into plans and validate complete plan structure |
| `core/safety.py` | Authorize each resolved step; bind approvals to the exact task revision and scope |
| `hands/registry.py` | Action definitions, parameter validation, preparation/verification hooks and retry classification |
| `hands/*`, `connectors/*` | Domain operations and domain-specific observations |
| `core/context.py` (new) | Current task summary and requested/resolved/observed entities |
| `senses/audio_focus.py` (new) | Temporary volume changes and restoration |
| `core/evaluation.py`, `tools/train.py` (new) | Offline scenarios, candidate datasets and before/after reports |
| `core/router.py`, `core/learning.py`, `core/recipes.py` | Learning artifacts, promotion and persistence |

Keep the CLI as the only runtime interface in 1.2. Emit plain structured events through a callback plus the existing JSONL log. Do not introduce a network server or general event bus yet.

## 4. Data contracts

Use Python dataclasses and enums, plus explicit validators. Existing action parameter descriptions remain useful prompt text but are not a type system.

| Record | Required information |
|---|---|
| `Task` | ID, revision, original request, mode (`live`, `dry_run`, `evaluation`), status, ordered steps, current position, completed results, cancellation event, elapsed active time |
| `Step` | ID, action name, arguments, source (rule/builtin/recipe/model), declared output bindings, status |
| `PreparedStep` | Validated resolved arguments, target identity, runtime expectation, authorization scope, before-state if necessary |
| `Outcome` | Status, short message, structured outputs, evidence, error code, whether a side effect may have occurred |
| `Evidence` | Observer name, observation time, target identity, expected fields, observed fields; no credentials |
| `PendingQuestion` | Kind, task/revision/step IDs, expiry, exact candidate IDs or approval scope |

Outcome statuses: `verified`, `failed`, `uncertain`, `needs_input`, `cancelled`, `simulated`, `dispatched`.

- `verified`: the registered contract was observed. For a read action, this means a successful read, including an empty result; it does not mean a broader goal such as opening a file is complete.
- `dispatched`: an operation was submitted but its intended effect cannot be checked. Say "I sent/opened the request", not "Done". This is not verified task success and cannot automatically unlock a dependent step.
- `uncertain`: attempted execution may have changed state, but verification is missing or contradictory. Never automatically repeat a non-idempotent action.
- `simulated`: dry-run only; does not train recipes, increment success counters or claim real completion.

Preserve `Result(ok, say, data)` temporarily while migrating actions. In the new runner, a legacy `ok=True` maps conservatively to `dispatched`, never automatically to `verified`; `ok=False` maps to `failed`. Migrate core actions explicitly. A compatibility `.ok` property may mean `status == verified` for updated callers. Do not leave two independent implementations of plan execution: `safety.run_plan()` becomes a compatibility wrapper around the runner and is then retired from pipeline usage.

## 5. Task lifecycle and cancellation

Task states: `planned`, `running`, `waiting_input`, `succeeded`, `failed`, `uncertain`, `cancelled`, `simulated`.

Step states add `preparing`, `executing`, `verifying`, and `skipped`. Only a verified step permits normal automatic advancement. All steps are sequential in 1.2; even independent later steps stop after an earlier failure. This avoids surprising partial execution and keeps the first release small.

A terminal `dispatched` step produces task status `uncertain` with a truthful dispatch message. Preserve the step's more specific outcome for reports. `waiting_input` retains the suspended step; only a validated answer resumes it. A dry-run task ends `simulated`, not `succeeded`.

1. Validate the entire plan's structure before any side effects.
2. Resolve the next step's arguments and prerequisites; ambiguity yields `waiting_input`.
3. Obtain approval when required, tied to the resolved target and current plan revision.
4. Execute once, then observe the result until verified, failed, cancelled or out of time.
5. Record the outcome before considering advancement.
6. On failure/uncertainty/cancellation, mark remaining steps skipped and report what already happened.

No automatic rollback: closing a newly opened app or undoing a note could itself destroy user work. Report partial results; reversal is a separate explicit request.

An expired question cancels its suspended continuation. A different complete request cancels/supersedes the old continuation before creating a new task. A correction creates a new task revision and invalidates affected prepared steps and approvals. "Again" creates a new task from the last verified user action, resolving targets afresh; it never silently repeats a failed action or reuses an approval.

Replace global `confirmed=True` authorization with an internal approval record containing task ID, revision, step ID, resolved-argument digest, target identity and expiry. Consume it for that action only. A review can cover several fully resolved steps if each scope was displayed; new targets, arguments or recovery strategies invalidate the affected approval. Approval is never inferred from a model reply or from screen/web text.

The initial runner remains synchronous. Ctrl+C must set cancellation on the active task, stop further steps, and unwind audio cleanup; while idle it retains quit behaviour. Waiting loops use a cancellation event rather than long unconditional sleeps. In-flight HTTP/Windows calls may not be immediately interruptible: enforce bounded calls and check cancellation as soon as they return. A cancelled task never resumes when late results arrive. Voice interruption during execution is deferred; F9 remains microphone mute, not a cancellation promise.

Initial configurable bounds: at most 4 user goals and 8 executable steps total, 45 seconds active task budget excluding human response time, 30 seconds for a pending question, and at most one allowed recovery per step. Use a monotonic clock. These are initial limits to validate on the PC, not measured optimal values.

Propagate the remaining deadline into model fallbacks, connector requests and verification. A full model chain must not receive a fresh total budget per model/retry. No new work starts after expiry; report uncertainty if a previous call may have applied an effect.

## 6. Plans and model output

Keep the existing `do`/`with` vocabulary. A proposed compound output is:

```json
{
  "version": 1,
  "steps": [
    {"id": "music", "do": "play_music", "with": {"query": "The Hills", "kind": "track", "artist": "The Weeknd"}},
    {"id": "timer", "do": "set_timer", "with": {"seconds": 1200, "label": "study"}}
  ]
}
```

The model does not supply risk levels, retry permissions, verification bypasses, executable code, or success claims. Action definitions determine these. Only offer relevant action groups, normally no more than 20 options; use a small routing/planning stage when more groups are needed. Keep existing configured Qwen/Gemma job chains unless measurement justifies a separate change.

Reject unknown actions, unknown/missing arguments, wrong types, nonfinite numbers, invalid enums/ranges, empty steps, duplicate IDs, excessive size, unresolved placeholders and invalid references. Reject rather than silently truncate or drop fields. Allow at most one constrained model repair within the original budget; no partial execution of an invalid plan. User-facing replies are generated from outcomes, not the model's proposed success sentence.

Compound detection runs before broad music matching, but respects quotes and recognises the single goal "open Spotify and play X". Separate independent verbs/clauses; do not split song titles merely because they contain "and". If structural parsing is ambiguous, use a constrained model proposal or ask. Never lower a routing confirmation threshold just because a request was split.

For result-dependent tasks, support only typed backward references to declared outputs. Example: `find_files` emits `selected_path` only after an unambiguous result or user selection; `open_path` may use `{"$ref":"find.selected_path"}`. Structural/type validation happens before execution; the concrete path is revalidated and authorized when available. No expressions, arbitrary JSON paths or invented filenames. If a later step cannot yet be resolved, pause at that boundary and preserve prior results honestly.

## 7. Action checks and recovery

| Action | Required observation | Recovery / limitation |
|---|---|---|
| Play selected track | Expected identity, playing state, selected device | Poll; do not blindly resend after an ambiguous timeout |
| Play album/playlist/artist | Requested context and playing state on target device | Missing context gives uncertainty; a matching song alone does not prove playlist selection |
| Open/switch app | Identified app window; foreground identity when focus is required | One launch then bounded wait; no repeated launching loop |
| Set volume | Read back requested level within 1 percentage point | Direct setting may retry once after observation; keypress fallback is unverified |
| Relative volume | Read initial level, compute absolute target once, verify target | Never recompute delta on retry |
| Pause/resume | State of selected media session/device | Avoid toggles; unrelated playing sessions do not count |
| Skip/previous/toggle | Fresh target-session evidence of expected transition | No automatic replay; same-title repeats may remain uncertain |
| Set timer | Timer ID exists with expected deadline/label | Task/step execution ID prevents duplicate timer creation in-process |
| New/append note | Exact target path and expected content change | Unique file naming; no overwrite from minute-level name collisions; no blind append retries |
| Find file | Search completed and returned paths | Selection is explicit before opening ambiguous results |
| Open file | Target association/window evidence where available | Mere `os.startfile` return is dispatched, not proof the document opened |
| Browser search/link | Submission can be reported | No page-load/search-result success claim until a browser observer exists |
| Generic click/type/hotkey | Exact focused target and supported postcondition | Otherwise stop as dispatched/uncertain; never save as a verified autonomous recipe |

For keyboard input, bind the prepared target to a real process/window and recheck focus immediately before sending input. Refuse password fields and unknown focus classification for text entry. Named-action safety must consider target context and actual resolved controls; keyword matching alone cannot establish that Enter or a click is harmless. Unclassified generic input requires review and is excluded from unattended execution. Restrict app-link schemes to registered handlers and validate paths before launch.

Retry categories are code-owned: `read_only`, `set_to_value`, `non_repeatable`. Observation retries are separate from execution retries. No automatic replanning loop in 1.2. A supported recovery can refresh a stale device/window handle once and recheck; a new strategy or target needs a new validated revision.

## 8. Spotify flow

Separate resolution from playback: `query -> candidates -> selected media -> selected device -> playback request -> observation`.

Resolution preserves meaningful words and versions. Normalise case, whitespace and punctuation, but do not erase "in"/"the", artist names, live/remix qualifiers or user corrections. Explicit artist and kind constraints are hard filters. Exact installed-game names/explicit game aliases may route to launching; fuzzy app names never override a music request. A full corrected command after "no" is processed as a replacement request without requiring a model rewrite.

Return structured candidate IDs, names, artists, kinds and match reasons. In `auto` mode search supported kinds; use exact name/artist matches first. Distinct exact interpretations (song versus album, or different artists) require a short choice. Fuzzy-only matches propose a candidate instead of auto-playing in 1.2. Collapse only proven equivalent identities. Do not silently replace a recording with a remix or live version. An explicit "queue" request must not be implemented as immediate play; until enqueue is supported, explain the limitation.

Prefer a user-configured device; otherwise resolve the local PC, launching Spotify once if necessary. Do not silently choose an active phone or speaker. If local identity cannot be established, ask which device. Re-resolve stale device IDs and exclude restricted devices.

Read full playback state after submission. Spotify exposes device, context, item and playing state; track relinking metadata can establish equivalence when present. The verifier must tolerate missing fields and must not depend on deprecated fields. Exact identity unavailable means uncertain, not a title-only success. A successful API response alone does not satisfy Otto's verification contract. [Playback state](https://developer.spotify.com/documentation/web-api/reference/get-information-about-the-users-current-playback), [Start playback](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback).

Use an initial 6-second observation window with roughly 1-second polling, capped by remaining task time and rate limits. Handle 401 with the connector's bounded refresh path; 403 as an actionable failure; 429 according to Retry-After, stopping if the wait exceeds budget. A network timeout after PUT is uncertain: read state before any further mutation. Distinguish wrong state from unavailable observation.

For Liked Songs, verify the actual requested mode. If the fallback plays a fetched subset, say "Playing from your Liked Songs" and report that subset, not the whole library. Only claim shuffle if observed. With Spotify disconnected, opening a search remains useful but the play task is not successful.

## 9. Context, questions and speech

Maintain separate `requested`, `resolved`, `observed` and `rejected` entities. Sources and timestamps travel with them. Never put an assistant success sentence into context as proof of an action.

Keep up to 8 recent exchanges; send at most 3 relevant exchanges plus a structured current-task summary to the model. Initial summary budget: 1,500 characters; total brief plus history budget: 6,000 characters, excluding the action schema/current request. Do not clip JSON structures; remove oldest optional entries first. Character budgets are guards, not exact token counts: implementation must also cap the complete prompt for the gateway's stated 8,192-token limit, including output/vision headroom. Preserve safety instructions and current user request.

Use the existing 120-second follow-up age as the initial default. The voice wake-follow-up window remains a separate 8-second setting. Long-term preferences are explicit saved data, not automatically inferred from every correction.

- "Okay" with no pending action is a harmless acknowledgement and never starts a hearing-confirmation loop.
- "Okay" while approving a risky step is an approval candidate; low-confidence speech must be clarified before execution.
- "No, can you play The Hills?" rejects the previous requested target and starts the replacement music request.
- "The second one" resolves only against the current unexpired candidate list.
- A new unrelated request clears old pending continuation; it is not learned as a correction.
- A bare "no" cancels the pending scope and never resumes downstream steps.

Do not learn "artist X means app Y" merely because an action returned success. Routing-label confirmation and verified execution are different evidence types and must remain separate in training records.

## 10. Audio ducking

Implement one scoped audio-focus controller, independent of model/planner code. Prefer Windows per-session volume for competing applications, excluding Otto's own process, so Otto's speech remains audible. Set each affected session to `min(original, 20%)`; never raise quiet audio or unmute it. The 20% refers to the application's session slider, not a guaranteed perceived loudness. If per-session control is unavailable, report the feature unavailable rather than silently lowering Otto's own voice through master volume.

Acquire on F8-down, or once a wake/request is recognised; retain through execution and speech, then release. Restore while waiting for human clarification, on empty input/release, no speech, timeout, cancellation and recoverable error. A no-input lease expires after 30 seconds; renew only for an active interaction. Reference-count overlapping speech/timer announcements so one completion cannot restore too early. Audio control calls run on a dedicated COM-initialised worker; hotkey callbacks only enqueue events.

Store original session volume/mute and the value Otto applied. Restore only sessions Otto still owns: an external user change relinquishes restoration ownership for that property. Handle new sessions during the lease, disappearing sessions, and output-device changes. Explicit "volume 40" updates the real master target and is not undone by session restoration. Keep ordinary volume actions separate from temporary ducking.

Use finally-based cleanup and normal shutdown handling. A force-killed process cannot guarantee immediate restoration; keep a small recovery journal and restore on next startup only when session identity and Otto-applied values still match. Test this limitation on Windows and document it. Immediate wake-phrase ducking before transcription requires a future wake detector; 1.2 does not promise it.

## 11. Learning and offline practice

The initial proposed CLI is `otto train --offline --tasks 100 --seed 42`. This command does not exist yet. It may use local Qwen for task generation, but has no live Hands, desktop input, Spotify mutation, cloud fallback or production learning writes. Give it an isolated data root and injected fake action backend; dry-run alone is insufficient because it bypasses action outcomes.

Start from typed scenario templates with known ground truth. Qwen paraphrases requests while preserving declared action/arguments; rejected or uncertain paraphrases stay out of training. Curriculum: single actions, confusing entities, corrections, two-step tasks, longer tasks, then injected failures. Advance on a separate development sample (initial threshold 90% over at least 20 cases with no critical violations), not repeated success on the same generated tasks. Continue mixing earlier levels. Label this simulated competence, not desktop reliability.

Limit the run to the requested task count and a configurable duration, with deterministic seed and resumable generation records. Default to text-only simulation; no screenshots or real voice recordings. A Qwen-generated case and Qwen judgment alone do not establish correctness. First-release generated examples require review before admission; deterministic fixture outcomes provide evaluation evidence.

Keep three datasets: training, development/calibration, and a frozen release evaluation set. Split related templates/paraphrases together. The existing `test_set.csv` is development/calibration because it already tunes thresholds and selects models; preserve its contents and its exclusion from training. Do not expose final evaluation cases to the generator or fit process. After results inform fixes, treat that evaluation version as a regression suite and replenish untouched cases for the next independent assessment.

Candidate promotion:

1. Snapshot dataset/schema/model/settings versions and hashes. Read a consistent dataset snapshot.
2. Load the current calibration and evaluate it and the candidate on the same development set; never compare a new score with a stale score from a different dataset.
3. Fit in a separate candidate instance/directory. Never mutate the active serving model in place.
4. Require no regression in aggregate development accuracy, no new failures on critical labelled cases, and no degraded action-zone precision; insufficient evidence means no automatic promotion.
5. Save a complete candidate, verify it loads, then switch an atomic manifest/pointer. Keep the old artifact for rollback. Use one training writer and prevent concurrent promotions; a failed write never removes the active artifact.
6. A missing/corrupt model is an explicit bootstrap/recovery case, not permission to silently promote a regression. No empty or unchecked evaluation set can produce a trusted promotion.

Interactive user-labelled examples can retain automatic promotion after the gate passes. AI-generated candidates remain pending user review. `force` may request training, never bypass the quality gate. Training should be an explicit separate process in 1.2; collecting 20 examples marks training due rather than blocking a voice turn with fitting.

Save under `otto-data/training/<run-id>/`: manifest, scenarios, candidate examples, baseline/candidate results, JSON metrics and a Markdown report. Include completion status for interrupted runs. Laya artifacts remain local/versioned; Qwen weights do not change. Recipes require verified execution plus explicit user saving, validated parameters and current contracts; simulations never promote a live desktop recipe. Existing recipes load through compatibility validation, are rechecked at execution and are not overwritten. New verification failures affect their success counters honestly.

## 12. Reporting and observability

Events include task/revision/step IDs, mode, input source, action, outcome, evidence summary, error code, duration and model usage when available. Preserve original request separately from rewritten text. Store before/after identities rather than full screenshots by default. Do not log tokens, authorization headers or raw credential-bearing HTTP errors; sanitise connector failures centrally.

Reports show counts and denominators for routing correctness, action/argument correctness, verified complete-task success, false-success claims, wrong actions, clarification rate, cancellation correctness, recovery and p50/p95 latency. Break out typed/voice, single/multi-step and simulated/live results. Measure request-to-action and request-to-verified-completion separately. A search fallback is partial, a safe refusal is not completed work, and a correct clarification is scored as appropriate behaviour but not task completion until answered.

Compare the same scenario set and initial state for before/after runs. List regressions individually, model/dataset versions and promotion decision. Report missing measurements as unavailable, not zero. This release does not claim microphone improvement from text-only practice or claim model-training gains from code fixes.

## 13. Validation and release gate

Bring the four supplied test files and requirements-dev.txt into the project without changing their expected results merely to get green tests. Repair fixture isolation as necessary, document baseline failures, and add tests that inspect emitted actions/state, not just spoken strings. Read production code from the workspace, redirect all data writes and use fake models/devices/clocks. No GPU training or real desktop effects in the ordinary pytest suite.

One existing expectation deliberately changes: the supplied recipe test saves a method after a dry-run. Replace that setup with the new isolated executor and a fake backend returning verified evidence, so the test still proves save/replay without real side effects. Add a separate test that dry-run cannot save a live recipe. Document any other intentional expectation changes against this specification; do not delete failing coverage.

Required regression matrix:

| Group | Cases |
|---|---|
| Intent | Bruno Mars with Run installed; exact Valorant alias; unknown game; The Hills correction; track/album ambiguity; quoted titles containing conjunctions; queue request |
| Compound | Music then timer; app then input; three clauses; invalid later step rejected before first mutation; empty/malformed/oversized model plan |
| Lifecycle | Step fails/uncertain; cancel during wait; low-confidence yes; expired approval; unrelated request; changed plan invalidates approval; late result after cancellation |
| Playback | Accepted PUT but old track remains; delayed change; wrong device; missing/null fields; relinked identity; 401/403/429; timeout with possible success; disconnected Spotify |
| Side effects | Timer/note retry cannot duplicate; note-name collision; focus stolen; password detection unavailable; unsafe app-link scheme |
| Context | Requested versus observed song; stale candidate choice; bare acknowledgement; corrected explicit command; repeat only verified action |
| Learning | Startup hash change cannot force promotion; changed development set; empty set; candidate save/load failure; rollback; frozen-test exclusion; simulation cannot save recipe |
| Audio | Originally muted/below cap; nested leases; empty PTT; timeout; exception; user adjustment; disappearing/new session; endpoint change; startup recovery |

Windows acceptance: Spotify and local-device checks, actual volume restoration, F8/F9/Ctrl+C, note/file window checks and real speech replay. Begin with 40 versioned everyday scenarios across supported features, including at least 10 multi-step cases; repeat representative device/timing cases three times. Publish individual outcomes and distinguish design-required clarification from wrong action. This sample is a practical release gate, not a statistical guarantee.

Hard gates: no new failing existing tests; all new lifecycle/safety regression tests pass; no wrong-app launch, false verified-success claim, or dependent action after failure/cancel in the release scenarios. Targets: at least 95% correct autonomous actions, at least 90% complete requests in the supported set, and no unexplained regressions. Insufficient autonomous attempts must be stated. Retain <1 second typed / <2.5 seconds spoken targets for action start on warmed common paths; measure verification latency separately. If missed, report actual numbers and decide scope before release rather than silently weakening criteria.

## 14. Implementation batches and model checkpoints

| Batch | Model | Files / concrete output | Exit check |
|---|---|---|---|
| A: baseline and routing | Sol 6.1 | Import supplied tests/dev requirements; `details.py`, music override in `pipeline.py`, app matching; regression fixtures | Baseline recorded, Bruno/Run fixed, compound/title cases covered |
| B: outcome/plan contracts | Sol 6.1 using this design | `tasks.py`, registry validators, planner validation, conservative legacy adapter | Invalid plans cause zero effects; simulated versus verified distinct |
| Review 1 | Astra 6 | Review contracts, validation and task-runner implementation plan | Resolve design issues before changing execution flow |
| C: runner and context | Sol 6.1 | `executor.py`, `context.py`, pipeline/safety integration, deadline-aware brain calls, CLI cancellation | Failure, expiry, replacement and cancellation scenarios pass |
| D: domain verification | Sol 6.1 | Spotify/media, apps/window focus, timers, notes/files, recipe compatibility | Realistic fake-backend checks; partial results honest |
| E: audio | Sol 6.1 | `audio_focus.py`, ears/keys/mouth/CLI hooks, settings | Fake-session lifecycle tests and Windows acceptance |
| F: learning/evaluation | Sol 6.1 after Astra reviews promotion contract | Router/learning, evaluation runner, train CLI and reports | No live effects, no regression promotion, reproducible report |
| Final review | Astra 6 | Whole diff, failure paths, results and release scope | Approve release readiness or identify bounded follow-up fixes |

Batches are sequential and independently reviewable. Avoid two agents editing pipeline.py, details.py or otto.py concurrently. The user controls chat model switching; announce checkpoints and pause before the next model-specific batch. No automatic subagent delegation is assumed.

Before code changes, reconcile the supplied WORKLOG/AGENTS handover with the workspace and record the agreed work. Create a `codex/otto-1.2` branch without discarding or committing unrelated existing changes. Keep the 1.1 baseline identifiable; commits must separate inherited edits from new work. If branch/worktree handling cannot preserve the current state clearly, resolve that before implementation.

Add settings with defaults rather than replacing user data. Bump settings schema only for real migrations; preserve explicit user choices, especially voice/hotwords. Version task/recipe/training artifacts separately. Keep imports of Windows libraries lazy. Update CHANGELOG, WORKLOG, README, docs/ARCHITECTURE.md and the CLI version only as features actually land. Identify the old root ARCHITECTURE.md as historical rather than leaving two competing current designs.

Proposed new settings (initial values, validated at load and on change):

| Key | Default | Meaning |
|---|---|---|
| `tasks.max_goals` / `tasks.max_steps` | 4 / 8 | Structural plan limits |
| `tasks.active_timeout_s` | 45 | Shared active budget across planning, execution and verification |
| `tasks.max_recoveries_per_step` | 1 | Upper bound; action definitions may prohibit retries |
| `spotify.device_name` | null | Explicit target preference; otherwise resolve local PC |
| `spotify.verify_timeout_s` / `spotify.poll_interval_s` | 6 / 1 | Bounded playback observations |
| `context.follow_up_max_age_s` | 120 | Entity/reference expiry, independent of wake window |
| `audio_duck.enabled` / `audio_duck.cap_percent` | true / 20 | Per-session temporary audio cap |
| `audio_duck.idle_timeout_s` | 30 | Restore after abandoned/empty interaction |
| `training.model` | `qwen3-vl:8b-instruct` | Local generator, no automatic cloud fallback |
| `training.max_duration_s` | 1800 | Offline practice run budget |

Retain `zones.clarify_timeout_s` and `listen.follow_up_s` for their existing distinct purposes. Reject invalid values rather than relying on action-time coercion. Per-action hard limits cannot be raised by a generated plan. Defaults here are design choices to validate, not already-installed settings.

## 15. Approval and next action

Approval of this specification authorizes implementation of the included scope, not deferred desktop training or Phase 2. The first implementation checkpoint is Batch A on Sol 6.1. Remain on Astra only if revising the design. No implementation, package installation, training, test import, branch change or runtime data migration has been performed as part of writing this document.
