# Changelog

## 1.2 (in development)
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
