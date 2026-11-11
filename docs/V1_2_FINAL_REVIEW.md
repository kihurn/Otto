# Otto 1.2 D–F review

11 November 2026. Review and cleanup on `codex/d-f-review`, preserving the inherited uncommitted implementation.

## Verdict

Not release-ready. D and E have useful implementations but unresolved correctness issues. F implements a narrow offline evaluator and staged Laya calibration. The recovery-recipe extension agreed in the recovery design is still absent. A passing unit suite does not establish the Phase 1 desktop or voice success rates.

This pass reviews the code and removes confirmed unused code and generated files. The findings below remain open. No model was trained or promoted, and no personal settings or learning data were changed.

## Findings, in priority order

### R1 — P1 — Bind Chrome controls to browser chrome, not accessible names

Location — `hands/window_control.py`, `WindowProvider.act`, Chrome click eligibility.

The hit-test proves that the point belongs to the Chrome window. It then accepts any UIA element named `New tab`, `Address and search bar`, or `Search Google or type a URL`. Page content can expose exactly those accessible names. A model-selected webpage button can therefore pass the allowlist and be clicked without the approval appropriate to its real action. The query-field and address-bar verifier also need trusted browser ancestry checks.

Reproduced with a fake Button named `New tab` under a Document ancestor. `act()` sent one mouse click. No real browser was clicked.

Required fix — identify browser-owned controls through verified UIA ancestry and supported control patterns, reject descendants of web Documents, and repeat those checks immediately before input. Add a regression proving that a page impersonating the browser's controls receives zero clicks or typing. Keep visual mode opt-in until this passes.

### R2 — P1 — Gate candidates at the threshold they will actually use

Location — `core/training.py`, `gate` and `stage_candidate`.

Both calibrations are evaluated at the active router's threshold. The saved candidate metadata instead contains newly measured bars, which `Router.bars()` uses after activation. A candidate can pass the gate and then act on a larger, less accurate set of requests in production.

Reproduced with 40 identical before/after predictions, 38 correct at 0.99 and two incorrect at 0.72. The gate passes at the baseline threshold 0.85 with 100% confident precision. The candidate's saved bar is 0.72, producing 95% confident precision after activation. This violates the explicit no-degradation requirement despite unchanged overall accuracy.

Required fix — derive each calibration's effective serving threshold using the actual settings, including floors and measured-bar policy. Evaluate confident precision separately at those thresholds, save both in the report, and validate the same policy at promotion. Existing staged reports should require reevaluation under the corrected gate.

### R3 — P1 — Evaluate confidence ties as complete groups

Location — `core/router.py`, `measure_bars`.

The loop records a threshold from a correct prefix of predictions with equal confidence. Later wrong predictions with that same confidence do not invalidate the recorded threshold. Serving uses `>=`, so it includes the entire group.

Reproduced with ten predictions at 0.9, the first eight correct and the final two incorrect. `measure_bars` returns an acting threshold of 0.9 even though its actual precision is 80%, below the requested 95%.

Required fix — assess complete equal-score groups, then verify precision using the exact inclusive threshold that will be stored. Avoid rounding a threshold down into an unevaluated group. Test invariance to row ordering and the behavior when no threshold qualifies.

### R4 — P1 — Verify the exact requested Spotify recording

Location — `hands/spotify_desktop.py`, `play_candidates` and the final playback observation in `play`.

The card fallback uses phrase containment, and the final observer calls the same containment matcher on the playing title. `The Hills Live` therefore satisfies a request for `The Hills`. This can report success for a live recording or remix the user did not request. The visual provider also chooses the topmost matching control instead of rejecting multiple distinct matches.

Reproduced through `play()` with fake UI controls and a Windows media session reporting `The Hills Live` by The Weeknd. The returned outcome was `verified` with the reply `Playing The Hills by The Weeknd.`

Required fix — separate card discovery from completion matching. Preserve version qualifiers, require an exact normalized title and artist for completion, and ask when distinct recordings remain ambiguous. Test live/remix titles, substring matches, and multiple matching cards.

### R5 — P2 — Restore healthy audio sessions even when one session expires

Location — `core/audio_focus.py`, `SessionCaps.update` and `AudioFocus._worker`.

A COM failure while reading or restoring one owned session aborts the whole update. The worker's final restore starts at the same failed session and can abort again, leaving other healthy applications capped at 20%. Session expiry and device changes are normal Windows events.

Reproduced with two fake capped sessions. The first raises `OSError` when queried after expiring. Restoration exits before the healthy second session, which remains at 0.2.

Required fix — isolate errors per session, continue restoring other sessions, retain only unresolved receipts, and retry transient enumeration failures within a bounded policy. Test expiration during capping and restoration, as well as device removal. Do not turn a journal-write failure into an unrecorded mutation.

### R6 — P2 — Handle “save that” after a successful task without an Intent

Location — `core/pipeline.py`, `_memory`.

Visual tasks, compiled compound tasks and numeric audio selections can call `_run` with `intent=None`. A verified result is stored in `self.last`, but `_memory('save')` unconditionally reads `i.area` and `i.action`.

Reproduced a successful visual-task history entry followed by `_memory('save')`. It raises `AttributeError`.

Required fix — define which task types can be saved. Reject unsupported saves with a short explanation, or create an appropriately scoped candidate. Never manufacture a routing label for a compound or visual task. Cover all three `intent=None` paths.

### R7 — P2 — Complete or explicitly defer recovery-recipe learning

Locations — `core/recipes.py`, `core/recovery.py`, `core/training.py`, and the F extension in `docs/V1_2_RECOVERY_DESIGN.md`.

The recovery design requires candidate records, app/version and verifier bindings, multiple independent verified successes, explicit promotion, and quarantine after wrong-target outcomes. The implemented trainer stages Laya classification calibrations. Recovery only writes diagnostic logs, and legacy recipes still use aggregate used/worked counters. There is no recovery-method candidate lifecycle.

Required follow-up — implement the agreed semantic recipe candidate lifecycle as a separate bounded batch, or explicitly defer it and narrow the 1.2 completion claim. The current implementation does not learn a successful visual method for reuse next time. Offline practice currently covers volume and timer templates, rather than the broader correction/entity curriculum in the design.

## Validation and cleanup

- Baseline suite passed 251 tests with three existing COM warnings when the fake localhost server was allowed. The sandbox-only run had 250 passes and the server-access failure.
- Six additional isolated probes reproduced R1–R6. These probes used fake controls, model predictions and audio sessions. They made no desktop, API or production learning changes.
- Removed unused router imports/history constant, a pipeline import, an unused window-edit helper, and the redundant standalone Enter action. `type_query` already submits once after readback. Added a rejection case for the removed action.
- Removed unused lifecycle/prepare/pending record scaffolding and an unused step field. Runtime task records and the pipeline's actual pending record remain. These removed types had no callers or test consumers.
- Replaced the obsolete root architecture copy with a link to the maintained document. Historical content remains in Git. Kept the mascot, Phase 0 evidence, personal data and training reports.
- Generated pytest directories were selected only from the workspace root and checked before deletion. Runtime data was excluded.

The final suite and cleanup counts are recorded in WORKLOG. No release or candidate promotion is approved by this review.

## Next implementation sequence

1. Fix R1 and R4 with adversarial UI and song-version tests.
2. Fix R2 and R3 together, then reevaluate staged candidates under the corrected thresholds.
3. Fix R5 and R6, including failure-path regression tests.
4. Resolve R7's scope, then perform fresh-launch Spotify, real voice ducking and two-device output acceptance.

The prior live evidence remains limited to an already displayed Spotify search, a Chrome URL observation, and per-session cap/readback checks. Those observations do not replace the remaining end-to-end acceptance runs.
