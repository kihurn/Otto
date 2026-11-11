# Design checkpoint: recovery and system audio

10 November 2026 — Astra review; implementation handoff to Sol.

## Decision and scope

Proceed with a bounded recovery extension, after strengthening verification and collecting the actual Spotify failure evidence. Do not add a generic screenshot-and-retry loop to every exception. The current tests establish routing and fake-backend behavior, not reliable Windows operation.

Initial scope: volume follow-up context, Spotify search-field discovery and song-card Play controls, audio output inventory/default selection/undo. Screenshot recovery is local Qwen only and limited to the Spotify window. Add candidate recipe recording after these paths pass live acceptance. Full desktop navigation, arbitrary Windows Settings changes and model-weight training remain outside this increment. Phase 2 remains the API/overlay; this extension brings a narrow portion of Phase 3 forward at the user's request.

Laya chooses the request area. Qwen proposes a structured recovery. The task runner validates it, and Hands performs named actions. Qwen cannot redefine verification or grant itself more attempts.

## Review findings to address first

1. **Spotify's search guard has several independent failure causes but reports one message.** `hands/apps.py` checks foreground HWND, control type, password flag and accessible name after a fixed 0.2-second delay. The screenshot establishes that a search-looking field was visible; it does not establish which check failed. Collect structured metadata for each check and use bounded polling. Do not simply remove the guard or increase sleep blindly.
2. **The existing screenshot helper is unsuitable for recovery dispatch.** `senses/eyes.py:screenshot` uses the last non-Otto window, may fall back to the full monitor, resizes the capture, and may restore terminal focus. Recovery needs an explicit captured window, coordinate mapping and a fresh target check; it must fail if that window cannot be captured.
3. **Cancellation can arrive during progress speech.** The executor checks cancellation before speaking, then can dispatch after speech without a new check. Recheck cancellation, deadline, task revision and target immediately before every effect, including after narration, inference and focus changes. A cancelled task must not dispatch even if a late observation/model response looks valid.
4. **A read risk classification is not a verifier.** The executor currently promotes successful READ results using a generic evidence object. Replace this with action-specific observation contracts. A low-risk action returning `ok=True` or a nonempty evidence list does not prove its expected result. Unknown observations remain uncertain.
5. **Context exists but generic volume pronouns do not use it.** “Increase it up to 70” falls into relative-volume rules because the absolute parser requires the word volume. Resolve a recent volume referent before parsing the absolute target; do not ask Qwen to invent a level.
6. **Current recipes do not contain recovery preconditions or evidence.** The legacy recipe store has steps and success counters. It is not sufficient for automatically activating visually discovered procedures. Record separate candidate artifacts first.

These are integration blockers for autonomous recovery, not a conclusion that the architecture is infeasible.

## Recovery contracts and execution

Use code-owned records, separate from model output:

- `FailureObservation`: task/revision/step, failure code, whether an effect may already have happened, observer and timestamp, available target identity.
- `WindowSnapshot`: opaque snapshot ID, HWND, PID, process start identity where available, executable identity, client rectangle, DPI/scale, capture size, timestamp and screenshot hash. Include current UIA candidates with snapshot-local IDs and bounds. Never expose tokens or unrelated windows to the model.
- `RecoveryProposal`: version, snapshot ID, task revision, capability, candidate ID or normalized point, short explanation. Strict schema; reject unknown keys, NaN, oversized lists and out-of-bounds coordinates. The runner supplies text to type from the original request; Qwen cannot replace the query.
- `PreparedRecovery`: validated target, original goal/authorization scope, expected result, original deadline, consumed attempt count and a code-owned verification function identifier.

Initial recovery capabilities are `focus_spotify_search` and `activate_spotify_track`. These are named capabilities with fixed substeps, not arbitrary model-generated action lists. Each can use at most two focus/click effects plus one original-query replacement and Enter where applicable. No generated hotkey, shell, arbitrary text, URI or app launch is accepted through this interface.

```text
known action -> observe
  verified -> next step
  known UI-target failure -> capture explicit Spotify window
      -> local Qwen proposal -> validate/recheck -> one recovery -> observe
  uncertain possible mutation -> observe first; do not repeat the mutation
  auth/network/missing dependency/unsupported capability -> diagnostic reply
```

One recovery per step and at most two per task, within the existing shared 45-second active budget. No additional attempt merely because a model response is malformed. Default inference cap: 8 seconds, clipped to remaining budget. At least 3 seconds must remain for verification before dispatch. These are implementation defaults to measure, not performance claims. Waiting for a user's clarification pauses active work but keeps a separate expiry; resumption never resets consumed attempts. Candidate changes increment the revision and invalidate approval.

Before any effect: recheck task/revision/cancel/deadline, executable/PID/HWND, client geometry, focus and target visibility. After model reasoning, acquire a fresh observation; compare relevant target region/UIA identity, not whole-image equality that would fail on every animation. Movement, scaling, window replacement or target-region changes invalidate the proposal. Abort without clicking; do not silently reuse coordinates.

Prefer Qwen selecting an observed UIA candidate ID. If only a point is available, it is valid for that snapshot alone. Transform image coordinates using the recorded client rectangle/scale, check bounds and hit-test ownership before moving/clicking. Never save the point as a reusable recipe. Initial pixel fallback may focus the Spotify search box, but typing still requires confirming an editable non-password field owned by Spotify. If that cannot be established, stop and request manual focus. Do not weaken password/focus checks to make the demo pass.

Play recovery requires title/artist evidence in the selected song card and exclusion of global playback buttons or unrelated cards. A Play/Pause icon by itself identifies neither the song nor successful playback. If the right track is already playing, report that observation without toggling Pause. Verify via Spotify's Windows media session and normalized title/artist/playing state. Qwen's own success judgment cannot promote the attempt to verified. Unavailable media-session evidence means uncertain, even if the UI looks plausible.

## Volume and output devices

Volume context is a typed `volume` referent with endpoint ID, timestamp, original request and observed level; it expires after 120 seconds and is invalidated by a conflicting topic or endpoint change. Within that context:

- “Increase it up to 70” / “lower it to 30” -> absolute set.
- “Increase it by 10” / “lower it by 5” -> relative change from fresh observation.
- “What is it now?” -> read-only observation.
- A relative direction with a target outside 0–100 is rejected; it must not fall back to a ten-point change.
- Without a volume referent, “increase it to 70” asks what to change.

Introduce `list_audio_outputs`, `get_default_audio_output`, `set_default_audio_output` and `undo_audio_output`. Device resolution uses stable endpoint IDs from an observed inventory, never a display-name substring alone. A saved preference may map “my speakers” to an endpoint ID; disconnect/replacement invalidates it and triggers rediscovery.

Define “default output” as normal system media output. Communications output is a separate explicit role; do not silently change call-device defaults. The implementation spike must confirm which roles the Windows backend can read and set, on this PC, before enabling the mutating capability. Existing endpoint-volume access is not evidence that default-device switching is supported. Use a documented/tested provider abstraction; do not have Qwen generate registry edits or shell commands as a fallback.

If multiple active outputs match Speakers, present a short numbered choice bound to inventory version, task/revision and expiry. A specific user command authorizes that reversible change without a second redundant yes. Capture previous endpoint/roles, perform the switch once, and independently read each affected role back. Partial changes are uncertain and include what changed. Do not blind-retry.

Undo is a short-lived receipt tied to the verified change. Restore only if the current default is still Otto's chosen endpoint and the previous device remains available; otherwise explain the conflict or ask which device to select. Output switching must coordinate with future ducking: restore/release leases on the old endpoint, then establish new leases rather than applying an old scalar to a new device. Capture all verification before TTS changes can confuse perceived success.

The system-capability catalog can later grow to other settings with read/prepare/execute/verify/undo contracts. It should not claim visibility of every Windows setting. Screen reading and administrative control are distinct capabilities.

## Learning and persistence

Keep routing labels, execution outcomes, recovery candidates and model weights separate. Successful recovery saves a candidate, not an automatically active recipe and not a Qwen weight update.

Candidate schema: version; source task/revision; capability; app executable/version and environment fingerprint; semantic target strategy; parameter schema; preconditions; verifier ID/version; observed outcome summaries; timings; attempts; promotion status. No raw coordinates, secrets or screenshots in reusable steps. Screenshots stay in memory by default; optional diagnostic retention requires an explicit setting, bounded retention and redaction policy.

Proposed promotion gate: three independently verified successes across at least two fresh app/window sessions, zero contradictory observed outcomes, replay of relevant frozen regression cases, and explicit user “save this method” or review of a candidate report. Qwen cannot judge its own promotion. These counts are a starting engineering gate, not a reliability percentage. The existing session approval authorizes building this mechanism, not treating every future candidate as user-approved.

Only supported semantic recipes are promotable. A recovery that depended only on pixel coordinates remains diagnostic. Replay rechecks all preconditions, current target and completion predicates. One observed wrong-target outcome immediately quarantines a recipe. App/version mismatch or uncertainty suspends it pending revalidation; cancellation and network failure are tracked separately from recipe mistakes. Never use simulation to increment live success, teach the frozen test set, or automatically retrain the serving model. Existing Laya promotion safeguards still need the planned F review.

## Implementation order and ownership

1. **D0 — diagnostics and foundation (Sol):** Spotify failure codes and bounded focus polling; typed volume follow-up rules; pre-dispatch cancellation checks; action-owned read verifiers. No vision needed to fix these regressions.
2. **D1 — audio outputs (Sol):** read-only inventory/provider capability spike, then exact-ID set/readback/undo with fake-provider tests and live acceptance. If the platform provider cannot meet the contract, report the limitation before adding a fragile fallback.
3. **D2 — Spotify recovery (Sol using this contract):** explicit window capture, local-only Qwen proposal schema, validator, bounded UIA-first recovery and Windows-media verification. Keep recovery disabled by default until recorded-image and fake-UI tests pass; then enable for this user's acceptance run.
4. **Remaining D, then E (Sol):** finish domain verification and audio ducking, with live acceptance in each batch.
5. **F extension (Sol):** implement candidate recording, reports and gated recipe promotion.
6. **Final Astra review:** review the combined D–F implementation, live traces, promotion safeguards and release readiness.

Primary files: new `core/recovery.py`, `core/audio_context.py`, `hands/audio_devices.py`, explicit capture API in `senses/eyes.py`; registry/executor/pipeline integration; separate recovery-candidate store. Preserve current data and unrelated edits. No runtime code or settings change is part of this design checkpoint.

## Required tests and live acceptance

Automated: real transcript variants for absolute/relative volume; expired/conflicting context; every search-field failure reason; slow focus; cancel during spoken progress/inference; changed task revision; invalid Qwen JSON; wrong candidate/window; window move/DPI change; missing or protected edit; screenshot text instructing an unrelated action; exhausted recovery budget; successful mutation with lost response; wrong track/artist; correct title in wrong app; already-playing track; absent media observation; no API calls in desktop mode.

Audio fake-provider matrix: unique/ambiguous Speakers, duplicate names/different IDs, disconnected devices, role readback mismatch, partial change, undo after manual user change, endpoint changes during volume/ducking. Candidate tests: no activation on first success, no learned pixel coordinates, app-version invalidation, quarantine on wrong target, no simulation/frozen-test leakage.

Live voice phrases: “Lower the volume to 30”; “increase it up to 70”; “what is it now”; “play Over the Moon by The Marias”; “make my speakers the default output”; “which output am I using”; “undo that output change.” Try Spotify both already open and freshly opened, and after moving/resizing its window. Record actual output/song and whether recovery was used, not just Otto's reply. A failure that stops without an unintended effect is safe handling, not successful task completion.

Exit gate: transcript regressions fixed, no effect after cancellation/stale snapshot, no false verified claim, correct device/role readback on the user's PC, and repeatable Spotify playback through both normal and recovery paths. Report observed latency and failures; do not equate unit-test count with live success rate.
