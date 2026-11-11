# Otto 1.2 Review 1 — 10 November 2026

## Decision

Keep the Batch B foundation, but do not treat it as verified execution. Proceed with the amendments below before broad runner integration. This is a design/code review, not a playback fix or a release approval. The user's voice transcripts and Spotify screenshot expose missing integration and coverage; more Laya training cannot repair these execution defects.

## Findings, ordered by priority

### P1: Validation does not cover the complete user task

`core/pipeline.py:handle` advances its string queue whenever there is no pending question, without checking the previous action's outcome. `_split` coerces arbitrary model values into strings, truncates to four requests, and immediately processes the first. Each sentence is routed again independently. `safety.run_plan` validates an individual action plan, not this outer queue.

This explains both reported mistakes: the generated search lost Spotify and became a web search; “play the first result” became a literal music query. Both can pass argument validation. An earlier failed step can also leave subsequent queue items runnable.

Required change: compile the complete request into a validated task before effects, with explicit app, entity and dependency fields. Retire the string queue for migrated execution. Never send generated standalone sentences back through Laya. Reject malformed/oversized plans rather than coercing or truncating them. Resolve backward references only against typed outputs of the same task and revision; an unresolved reference must ask or stop before the dependent effect. Validate all structure before the first effect and each resolved target before dispatch.

For the supplied “open Spotify and search for The Hills by The Weeknd and play it,” use a deterministic music rule to produce one play goal with title and artist. Opening and searching are implementation details of that goal. Do not collapse genuine extra goals such as “play The Hills, then set a timer,” or turn a search-only request into playback. Ambiguous candidates require a choice; selecting the highest search score alone is insufficient.

### P1: Accepted playback is presented as observed success

`hands/media.py:play_music` and `play_liked` return successful “Playing…” text immediately after dispatch. The live pipeline still consumes `Result.ok`; the new adapter is unused. Even after adoption, the adapter retains the original success wording. `Outcome` requiring a nonempty evidence list is a useful guard but cannot establish that the expected target was observed.

Required change: code-owned preparation and verification hooks, plus replies generated from outcome status. For track playback bind the chosen URI/identity, intended device and playing state; handle relinked identity explicitly. Poll within the task deadline, rejecting observations of the old track or another device. Use a separate declared completion predicate for album/playlist/artist/Liked Songs playback rather than pretending every goal has one track identity. Missing state means uncertain, not “nothing loaded.” A dispatched/uncertain result must not advance dependent steps, update verified context, or improve recipe success metrics. Unmigrated actions remain explicit partial results.

The screenshot shows After Hours in the player while Over the Moon appears among search results. That supports the reported mismatch, but does not establish exactly when each API call succeeded or failed. Retest with timestamped, sanitized observations.

### P1: Pending replies and failure feedback need task identity

“You did not play it” was routed as a new media request and elicited “Play?”. `PendingQuestion` has task/revision fields, but the live pending path does not yet use them. Requested song and observed song must remain separate.

Required change: recognize explicit failure feedback before ordinary media routing; associate it with the recent relevant task, invalidate its claimed success, observe current playback, and offer or perform only the bounded recovery allowed by that action. User feedback is evidence of a problem, not proof of a particular device state. Bind candidate choices and approvals to task/revision/step/target/expiry, invalidate them on replacement or cancellation, and reject late results. If no relevant task exists, ask what failed. A bare yes must not resurrect an expired or replaced task.

### P2: Spotify JSON failure needs boundary handling and safe diagnostics

The transcript proves a JSON decoding exception occurred during `play_liked`; it does not identify the response or token read that produced it. `connectors/spotify.py` parses JSON at several boundaries, including `_call`, token loading and refresh. Do not assume the token file is corrupt or reset the user's authorization.

Required change: handle empty/204 responses explicitly and validate JSON response shape where JSON is expected. Wrap decode failures with operation/boundary, HTTP method, endpoint path without query, status, content type, body length and error class. Never log authorization headers, token values or raw response bodies. A malformed response after a mutation may mean the mutation happened: mark side-effect possibility, observe before recovery, and do not blindly repeat it. Test malformed success and error bodies, refresh failure, timeout after dispatch and valid empty success.

### P2: Validation must preserve raw types and distinguish data from templates

`builtin_steps` converts timer and volume arguments with `float`/`int` before the validator sees them. That can hide invalid booleans/types or raise outside the validation boundary. `validate_args` derives types largely from argument names, and its placeholder regex rejects literal note content such as `{title}`.

Required change: action-specific schemas shared by builtins, recipes and model plans; validate raw intent values before conversion, reject nonfinite values/bools and return structured errors. Validate recipe placeholders during template expansion, not by banning brace text in user content. Explicitly constrain lifecycle transitions and define the preparation/verification/recovery interfaces before integrating the runner. Preserve literal titles, including a quoted song named “Queue,” while blocking actual unsupported enqueue requests.

### P2: Existing tests do not establish playback reliability

The suite mainly exercises routing/dry-run and contract shape. Simulation must neither create a verified recipe nor count toward real execution success. User confirmation of an intent may be retained separately as a routing label, but a subsequent failed action must not be recorded as successful execution. In particular, the transcript's “learned” line is not proof that playback was verified.

Required change: use fake action backends with explicit observations for lifecycle tests. Keep simulation tests distinct; migrate any old dry-run recipe-success expectation to the verified fake backend. Do not weaken verification to preserve an old assertion.

## Revised implementation sequence for Sol 6.1

1. **C1 — contract corrections and music task compilation:** action schemas, lifecycle/preparation/verification interfaces, structured music goals, reference validation, and regression cases below. No new learning paths.
2. **C2 — first complete runner path with Spotify verification:** sequential execution, task-bound pending state, cancellation/deadlines, structured connector failures, playback observations and truthful replies. Move the minimum Spotify work from D into this batch so its first live path is useful and testable. Failure feedback and simulated execution use the same state machine. A fallback through the old queue must not bypass these checks.
3. **C3 — remaining runner/context integration:** migrate other supported goals with conservative outcomes; preserve safety gates and stop dependencies on failed/uncertain/cancelled results. Complete the lifecycle matrix before widening scope.
4. **D — remaining domain verifiers:** apps/focus, notes/files, timers and recipe compatibility. E (audio ducking) and F (offline evaluation/learning) retain their existing scope and review checkpoints.

Phase 2 remains the API and overlay. No autonomous desktop practice, model fine-tuning or SearxNG work is added here. No extra model call is needed on the common deterministic music path.

## Regression acceptance cases to implement

These are test specifications, not tests already added or passing.

| Scenario | Required assertion |
|---|---|
| Exact supplied Spotify/search/play request | One music goal; The Hills and The Weeknd retained; zero web searches |
| Search Spotify for The Shade by Rex Orange County | Spotify target retained; no implicit play |
| Generated “play the first result” without bound candidates | No literal song search; ask/stop with zero dependent dispatches |
| Valid search output followed by a result choice | Selected stable ID bound to same task/revision; stale choice rejected |
| Spotify setup fails, next step would play | No playback dispatch |
| Invalid final step of a compound request | Zero effects across the entire task |
| Accepted play request but After Hours remains | No verified claim for Over the Moon; stop dependent goals |
| Delayed correct track on correct device | One dispatch; bounded polling; verified only after matching observation |
| Correct title on wrong device or unavailable playback state | No false verification and no automatic Liked Songs substitution |
| “You did not play it” after playback attempt | Feedback path observes relevant target; no fresh generic play question |
| Liked Songs returns malformed JSON / empty 204 | Structured uncertainty for malformed post-mutation response; empty success proceeds to verification |
| Old yes after replacement, expired approval, cancellation during polling | No stale authorization, further effect or late success |
| Dry-run/evaluation of all above | No desktop/API mutation, success learning or active recipe promotion |
| Timer bool/nonfinite value; literal `{title}` note content | Reject invalid numeric input; preserve literal content |
| Play a quoted title containing Queue; actual enqueue command | Literal title remains playable; enqueue remains unsupported |
| Voice request outside wake/follow-up window | Deliberately ignored unless wake/PTT accepted; tested separately from playback |

## Review validation

Inspected pipeline, planner, safety/registry contracts, task records, media/Spotify boundaries and existing tests. Reran the suite: sandbox run had 112 passes and one fake-localhost-server reachability failure; rerun with the required network permission passed **113/113 in 3.13 seconds**. No production source changes, live Spotify commands, microphone tests, model training or runtime-data migrations were performed for this review. Unit-test results do not validate the new acceptance cases above or actual playback.
