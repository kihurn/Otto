# Otto work log

Shared by every agent (Claude Code, Codex) and the user. Newest first inside each section.

## In progress
<!-- Claim before starting: - [agent] task – started YYYY-MM-DD (files you expect to touch) -->
- (nothing yet)

## Next up
See the backlog in `AGENTS.md`, section 8. First: confirm Otto 1.1 on Windows (`otto check`, `otto voice`,
`otto spotify`, music, follow-ups), then the training mode with an AI judge.

## Done

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
