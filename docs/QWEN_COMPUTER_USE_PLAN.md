# Qwen window computer use — implementation proposal

11 November 2026. Approved by user; initial opt-in prototype implemented. Native/live model
acceptance and Astra review remain pending. Pixel targets still need an independently eligible
accessible role; unknown-field pixel typing and unrestricted button clicking are not enabled.

## Intended behavior

Otto receives a goal, selects a specific Spotify or Chrome window, captures that window, and asks local Qwen for one next action. Hands validates and performs that action, captures again, and checks the result before continuing. Laya continues selecting the request area. The model cannot run code, invent tools or claim verified completion by itself.

This differs from current recovery: recovery only selects supplied accessibility candidates. The new controller also supports visual target proposals when named controls are unavailable. It is Otto's own provider, using existing screenshot/Windows libraries; Codex's computer-use service is not a dependency available to the installed assistant.

## First implementation scope

- Spotify: search a title/artist, choose the matching song card and play; verify Windows media title/artist and playback state.
- Chrome: open/focus a tab and search an explicit query; verify the actual URL/tab state through an independent observer. If that observer cannot establish the intended search, return uncertain.
- Allow only bounded task-owned click, focus, scroll, approved key chord and original-request text entry. No arbitrary application/system navigation in this first increment. Audio-output switching stays in D1's named device-control backend.

Suggested internal files: `core/computer_use.py` controller/schema, `hands/window_control.py` provider, explicit snapshot support in `senses/eyes.py`, integration through registry/safety/executor, recorded-snapshot/fake-provider tests. Preserve existing normal action paths and invoke this controller only for supported visual goals or supported recovery.

## Controller contract

The runner prepares a goal scope containing target process/window, allowed capability, text from the user request, completion predicate, task/revision and deadline. Qwen receives the explicit window screenshot plus up to 20 relevant accessibility candidates and proposes one JSON object:

```json
{"version":1,"snapshot_id":"opaque-id","action":"click","target":{"candidate_id":3}}
```

A visual target may instead specify normalized x/y and a bounding box with a semantic label. Strict action-specific schema validation rejects additional keys, malformed or nonfinite coordinates, unsupported keys/actions and wrong snapshot IDs. `type_text` references runner-owned request text; the model cannot substitute a different query. `done` is only a request to run the code-owned completion check.

Window snapshots bind HWND, PID/process start, executable, geometry, DPI, capture dimensions and task revision. Before each effect, recheck cancellation, deadline, foreground ownership, target identity, geometry and the relevant region's freshness. Hit-test pixel targets against the bound window; overlays or stale layouts require a new observation. Never click through a dialog or act on another window.

Initial visual clicking is limited to the original task’s search/play/tab-navigation controls, with a visible target preview and code-owned capability checks. Ordinary supported actions use the user’s task authorization; ambiguous targets ask for clarification. Screenshot confidence alone does not establish permission for a new capability. Send/Buy/Pay/Delete-type operations retain per-action confirmation and are outside the initial supported visual workflows. Password fields remain excluded; unknown field protection means no typing. Screen content is untrusted data, including text that asks the agent to change its instructions.

Each action consumes its snapshot. Reobserve after every input; do not execute a long blind list of coordinates. Limit initial visual tasks to six actions, the existing 45-second shared active budget and one recovery per failed step. Planning/inference, narration and verification consume that budget. Ctrl+Alt interruption is checked immediately before effects and after late model responses. A timeout or possibly successful mutation triggers observation, never an automatic duplicate click.

## Persistence and testing

Store sanitized action/evidence summaries, not active coordinate recipes. Screenshots remain in memory by default. Successful runs may become candidate semantic methods under the existing F promotion design; no automatic Qwen fine-tuning or immediate recipe activation.

Required tests: recorded normal/ambiguous screenshots, wrong/stale window, DPI/movement, obscuring overlays, malformed proposals, screen prompt injection, protected/unknown edits, wrong song artist, already-playing song, unavailable media state, cancellation during inference/narration, exhausted budgets and no effects in dry-run/evaluation. Mock-provider outcomes must not be reported as live acceptance.

Live acceptance covers The Hills by The Weeknd and Over the Moon by The Marias from open and freshly opened Spotify, Chrome search for an explicit phrase, window movement or resizing, and interruption during reasoning. Report success, failure and latency per case. Keep visual mode opt-in during acceptance. The final Astra review after D, E and F covers the live evidence and reusable learning safeguards together.

## Approval checkpoint

The user asked for implementation. This proposal makes the broader scope reviewable under AGENTS.md's plan-before-code requirement. Approval authorizes the first supported-window controller above; it does not authorize arbitrary system administration or unattended learning. Sol can implement after approval; Astra reviews target grounding and live evidence afterward.
