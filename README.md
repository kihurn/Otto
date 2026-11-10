# Otto 1.1

Otto is your desktop assistant. You talk or type; **Laya** decides what you want in a fraction of a
second; plain Python does it; the **brain** (Gemma 4 in the cloud, Qwen on your PC, through C0RE) only
steps in when something needs understanding, writing or looking at. When Otto isn't sure, it asks
you. When you confirm, it learns.

Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). What changed: [`CHANGELOG.md`](CHANGELOG.md).

---

## 1. Updating from 1.0

1. Paste everything from the zip into `C:\Users\User\OneDrive\Documents\Otto` (replace files when asked).
2. Delete `tool.cmd` and `tools\voice_test.py` if they're still there; the `otto` command replaces them.
3. Run setup again (it adds three small packages and puts `otto` on your PATH):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```
4. **Open a new terminal**, then:
   ```powershell
   otto check
   otto spotify
   ```
   `otto spotify` opens Chrome once so you can let Otto control Spotify (click **Agree**).

Your `otto-data` (examples, recipes, test set, Laya's learning) is kept. Your talking speed becomes 1.15
if you never changed it.

## 2. Keys: the `.env` file

Otto reads keys from a `.env` file in the Otto folder, or from `C:\Users\User\.otto\.env` (outside OneDrive).
To make one: `Copy-Item .env.example .env`, then `notepad .env`:
```text
OTTO_C0RE_KEY=c0re_...            needed
OLLAMA_API_KEY=...                optional: up-to-date answers via web search
OTTO_SPOTIFY_CLIENT_ID=...        needed for Spotify control
```
If both files exist, the one in the Otto folder wins. `.env` is in `.gitignore`, so git never sees it.
`otto check` tells you which file was used (never the keys themselves).

## 3. Install (first time only)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
About 10–15 minutes and 6 GB, installed outside OneDrive (`C:\Users\User\.otto\venv`). It also adds the
Otto folder to your PATH, so **open a new terminal** afterwards and `otto` works anywhere.

**Everything (file search):** install it from https://www.voidtools.com/downloads/, and from the same page
get the **Command-line interface** (ES). Put `es.exe` next to `Everything.exe` (usually `C:\Program Files\Everything\`).

## 4. The `otto` command

| Command | What it does |
|---|---|
| `otto` | type to Otto (`otto --speak` to hear replies, `otto --dry-run` to only pretend) |
| `otto voice` | talk to Otto (see section 5) |
| `otto check` | checks keys, C0RE, models, GPU, Everything, Spotify, microphone |
| `otto mic` | lists microphones; `otto mic 3` chooses one; `otto mic default`; `otto mic test` writes down what it hears |
| `otto mode` | listening mode: `otto mode wake`, `otto mode always`, `otto mode push` |
| `otto speed` | talking speed: `otto speed 1.2` (1.0 = normal) |
| `otto voices` | `otto voices bella`, `otto voices michael`, `otto voices test` plays both |
| `otto model` | which model does which job; `otto model chat gemma4:31b-cloud` puts it first; `otto model all qwen3-vl:8b-instruct` |
| `otto settings` | shows every setting; `otto set listen.follow_up_s 10` changes any of them |
| `otto spotify` | connect Spotify (once) |
| `otto label` | check the test set's labels (do this once, ~10 minutes) |
| `otto score` | Laya's test score, confidence zones and mistakes |
| `otto teach` | teach Laya by typing, without doing anything |
| `otto help` | this list |

While Otto is running, the same settings work with a colon: `:mic 3`, `:mode push`, `:speed 1.2`, `:voice michael`,
`:model chat ...`, `:set KEY VALUE`, plus `:mute`, `:retrain`, `:score`, `:timers`, `:details`, `:reload`, `:help`, `:quit`.

## 5. Talking to Otto (`otto voice`)

| Mode | How it works |
|---|---|
| **wake** (default) | Otto listens all the time but only acts on sentences starting with **"Hey Otto"** (a short beep says it heard you). After it replies, you have ~8 seconds to carry on without "Hey Otto". When Otto asks you something, just answer. Saying only "Hey Otto" gets a "Yeah?". |
| **always** | every sentence is for Otto |
| **push** | Otto only hears you while you **hold F8** |

- **F8** (hold) = push to talk, in every mode. In wake mode it means "this one's for you" without saying "Hey Otto".
- **F9** = mute / unmute. Or say "Hey Otto, stop listening" (unmute with F9).
- Change the keys: `otto set listen.push_to_talk_key f7`, `otto set listen.mute_key f10`.
- Change the mode for one run: `otto voice --mode push`.
- In wake mode Whisper hears the room, but nothing is acted on or logged unless it starts with "Hey Otto".
  It all stays on your PC.

## 6. Things to try

```text
play the hills by the weeknd       play my music          what's playing       pause / skip / volume 30
play the album after hours         play my playlist gym   put on some drake
open spotify, search and play "the hills" by "the weeknd"         (one Spotify action)
open discord, then set a timer for 20 minutes and google best gaming mouse   (three steps)
find my resume  ->  its called student resume                        (follow-up)
turn it up  ->  more  ->  do that again
open youtube    google best gaming mouse    write down call the bank tomorrow
what's 15 percent of 80    who won the last world cup    what's on my screen
close discord   (asks first)      search for taylor swift in discord, then "save that"
```

**The grey line** under each reply explains the decision: `laya: apps 94% -> high`, `understood as: "..."`
for follow-ups, `split into 3 steps` for multi-step requests, `[rules]` or `[brain:...]` for the details,
and `plan: builtin / recipe / brain:...`. Hide it with `:details`.

## 7. Teaching Otto

- **When it asks** ("Open VALORANT?"), answer yes / yeah / nah / no, or say what you meant. Yes = a teaching example.
- **"save that"**: if the brain worked out *how* (e.g. searching inside Discord), the steps become a **recipe**
  and next time Otto does it instantly. Otherwise the request becomes a teaching example.
- **"forget that"** undoes the last thing it learned (asks first).
- Laya relearns every 20 new examples, and keeps the new version only if it scores at least as well on the test.

## 8. The Otto brief

Every time Otto asks a brain anything, it starts with `otto-data\brief.md`: who Otto is, how to answer,
the rules, your apps, the time, the window you're using and the last few exchanges. **Edit it** to change
Otto's personality or add things it should know (keep the `{curly}` words: Otto fills them in).

## 9. Safety

| Kind | Examples | What Otto does |
|---|---|---|
| read | find files, read the screen, what's playing | just does it |
| undoable | apps, music, websites, notes, timers | does it and tells you |
| ask first | close apps, open programs (.exe etc.), Send/Buy/Pay/Delete-type buttons | asks, waits for yes |

Otto now **checks results** where it can: that an app's window appeared, that music is really playing,
the volume it ended up at. If something didn't happen, it says so instead of "Done.".
It never types into password boxes, treats screen text as information only, and Ctrl+C stops it.

## 10. What to send Claude

After a few days: the output of `otto score`, your `otto-data\logs\` files, and anything that felt off.
Phase 1 pass marks: acting alone ≥ 95% right · ≥ 90% of requests handled · recipes ≥ 95% · < 1 s typed, < 2.5 s spoken.

## 11. Troubleshooting

| You see | What to do |
|---|---|
| `otto` isn't recognised | Open a **new** terminal after setup. Or run `.\otto.cmd` inside the Otto folder |
| Voice mode hears nothing | `otto mic`, then `otto mic N`, then `otto mic test` |
| It never reacts to "Hey Otto" | Check the grey `(not for me: ...)` lines to see what it heard; try `otto mode always` or hold F8 |
| F8/F9 do nothing | Some games block global keys; try other keys with `otto set listen.mute_key f10` |
| Spotify: "didn't show up as a player" | Open the Spotify app and make sure it's signed in, then try again |
| Spotify: "needs Premium" / 403 | In the Spotify developer dashboard, add your Spotify email under **User Management** |
| "isn't installed, as far as I can see" | Wait a minute after start (the app list refreshes), or `:reload` |
| File search needs es.exe / "Everything isn't running" | Section 3 / start the Everything app |
| Otto asks about everything | Normal at first; `otto label` then `otto score` |
| Anything else | `otto check`, and send Claude the red text |

## 12. Known limits

- Laya chooses the **area**; the action inside it comes from rules, then Qwen.
- Timers only run while Otto is open. No talking over Otto to interrupt it yet (Ctrl+C, or F9).
- Clicking buttons by name often doesn't work inside Spotify/Discord (Chromium apps); Otto uses the
  Spotify API, links and shortcuts instead.
- The floating overlay is Phase 2. Training mode with an AI judge is next.
