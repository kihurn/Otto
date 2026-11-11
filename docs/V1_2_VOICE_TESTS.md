# Voice acceptance checks for 1.2

## D–F handoff

- D: “List audio outputs”, “Which output am I using?”, “Make my speakers the default output”,
  and “Undo that output change”. Connect a second output to verify a real switch and restoration.
  Re-run the Qwen Spotify and Chrome tests from a freshly opened app.
- E: Start audio in another app, then run `.\otto.cmd voice --mode push`. Hold Ctrl+Alt and speak.
  Verify the app session is capped at 20% and returns to its original setting after the reply.
  Try cancellation, a muted app and adjusting the app slider while Otto is speaking.
- F: Run `.\otto.cmd train --offline --tasks 100 --seed 42`. Read the printed report path. To compare
  another run, use the same options plus `--baseline RUN_ID`. `otto candidate` trains a separate
  Laya calibration and prints its report. Candidate activation is an explicit `otto promote ID`.

## Qwen window-controller prototype — opt-in

Start `.\otto.cmd` for typing, or `.\otto.cmd voice --mode push` for voice. Enter the console
command `:set computer_use.enabled true` to opt in. Then type or say:

- “Use Qwen to play The Hills by The Weeknd.”
- “Use Qwen to search what is Otto.”

Keep the target window unobscured. Expect at most six visual actions; verify the actual song or
Chrome query. If the controller cannot establish a safe field/control, it stops; Qwen's guess is
not enough. Ctrl+Alt requests interruption in voice mode; Ctrl+C quits. To disable, enter
`:set computer_use.enabled false`. This prototype has automated fake-provider coverage but no
live native/model acceptance yet. Ordinary “play…”/“search…” requests retain their normal path.

## 11 November regression check (typing is fine)

Restart `.\otto.cmd` to type, or `.\otto.cmd voice --mode push` for voice. Set volume to 70,
then “lower it by thirty two”: expect 38. Then “play The Hills by The Weeknd”: expect the full
query in Spotify's ComboBox and verified playback. Tool-assisted playback succeeded in the live
app; the patched full Otto pipeline still needs this acceptance run.

## Initial D2 acceptance

Restart `.\otto.cmd voice --mode push`. Say “Set volume to thirty”, “increase it to seventy”,
“lower it by five”, then “what is it now”. Expect 30, 70, 65, 65.
Say “Play The Hills by The Weeknd”. If normal search targeting fails, one local-Qwen recovery may
select an accessible safe search field. No accessible safe field means it still stops; screenshot
recognition alone never authorizes typing. Report the reply and diagnostic code. Recovery records
are logged with result dispatched/stopped/no_safe_candidates; screenshots are not retained.
Live recovery is not yet verified and does not save a learned method. Audio-device control is D1.

## D0 — test now

Restart `.\otto.cmd voice --mode push`. Hold Ctrl+Alt while speaking each phrase:

1. “Set volume to 30.” Then “Increase it up to 70.” Expect 30 then 70, not 40.
2. “Lower it by 5.” Expect 65. “What is it now?” must read without changing the level.
3. “Open Spotify.” Then “Increase it to 70.” Expect a target question because the topic changed.
4. “Play The Hills by The Weeknd.” If the search field cannot be verified, copy the new diagnostic
   code: focus_lost, protected_field, not_editable, search_label_missing or uia_unavailable.
5. During a narrated compound action press Ctrl+Alt to interrupt. No subsequent action should be sent.

Visual Qwen recovery has not been enabled. These changes diagnose and guard the normal path;
they do not establish that Spotify's real accessible search field is now correctly exposed.

## C3 plus volume/Spotify fixes — test now

Run `.\otto.cmd voice --mode push`. Hold Ctrl+Alt through each phrase, release when finished.

1. “Lower the volume down to 30.” Expect actual volume near 30%, not a relative ten-point decrease.
2. “What is it now?” Expect a read-only current-volume answer, no level change.
3. “Play Over the Moon by The Marias.” Search should contain spaces and the matching song card's
   generic Play control may be used. Check actual audio. Success still requires Windows media state.
4. “Set volume to 30, then set volume to 20.” Expect sequential actions; final observed level near 20%.
5. “Set volume to 30, then set volume to 101.” Expect rejection with no first volume change.
6. “Close Spotify.” Do not say yes; give a new request such as “What is the volume now?” Then say
   “Yes.” The stale approval must not close Spotify. This sequence is meant to test replacement,
   not actually close the app.

You can preview steps 4–6 with `.\otto.cmd voice --mode push --dry-run`; previews cannot count as
verified success or create recipes. For “open Discord, then set a timer,” app focus must verify before
the timer is sent. Timer/notes/file verification is D; those actions may stop with an unverified
message even when dispatched. General output references remain unsupported except the typed
read-volume-to-set-volume case. Record the transcript, observed level and actual playing song.

## Desktop/search follow-up — current user configuration

Run `.\otto.cmd voice --mode push`, holding Ctrl+Alt through pauses and releasing when finished.
This user's Spotify backend is now desktop, so the earlier API checklist below is historical unless
the backend is changed back to api.

- Hold Ctrl+Alt and say “um… uh…”, release: expect no clarification prompt.
- Say “Play Over the Moon by The Marias”: expect Spotify open/search, one matched Play control,
  and success only when Windows reports that song playing. If no matching button is accessible,
  report Otto's message; it will stop rather than click the first result blindly.
- Say “Search what is Otto”: expect a Chrome web search, no screen question.
- Say “What's the weather like in Selangor?”: expect an internal SearxNG-backed answer without
  opening Chrome. If search is unavailable Otto must say so.
- Desktop mode currently supports song requests, not Liked Songs or collections. Qwen screenshot
  clicking has not been added; named-control availability needs Windows acceptance.

## C1 — targeting, with simulated actions

Run in PowerShell from the project folder:

```powershell
.\otto.cmd voice --dry-run
```

Hold Ctrl+Alt to talk, then release either key to finish, or say “Hey Otto” before each phrase. Restart Otto after changing hotkeys. Check the printed `you:` transcript first: if the title was misheard, record that separately from routing. These checks describe intended actions; playback is not tested yet.

| Say | Expected |
|---|---|
| Hey Otto, open Spotify and search for The Hills by The Weeknd and play it. | One dry-run play action retaining title and artist; no Google search or three-step split |
| Hey Otto, can you search on Spotify The Shade by Rex Orange County? | Search in Spotify; no playback and no Google search |
| Hey Otto, open Spotify and search for The Hills by the weekend. | Spotify search only; no Chrome confirmation |
| Hey Otto, search on Spotify, The Shade by Rex Orange County. | Spotify search despite transcription punctuation |
| No, I want you to search on Spotify The Shade by Rex Orange County. | Explicit corrected search; no playback |
| Hey Otto, play the first result. | Asks which song; no search for a song named The First Result |
| Hey Otto, play Bruno Mars. | Spotify music action; never opens Run |
| Hey Otto, play Valorant. | Launches the configured exact game in dry-run |
| Hey Otto, play Over the Moon by The Marias. | Music target retains title and artist |

Ctrl+C quits. Report the `you:`, `otto:` and details lines for any mismatch. C1 still has legacy execution outside these narrow workflows; a correct dry-run is not evidence of successful playback.

## Subsequent batch checkpoints

## C2 — actual Spotify playback

Restart with `.\otto.cmd voice` (no `--dry-run`). Have Spotify signed in on this PC and Otto connected via `otto spotify`. Hold Ctrl+Alt to speak; release it when finished. A new Ctrl+Alt press while a music task is running requests cancellation. Ctrl+C quits. Cancellation cannot undo a playback command already sent, and an in-flight network call must return or time out before the task finishes stopping.

1. Say “Play The Hills by The Weeknd.” Expect search/player/checking progress, followed by “Playing…” only after matching playback is observed. Listen and check the actual song.
2. Say “Play Over the Moon by The Marias.” Verify the song changes; an old song remaining must produce an unconfirmed result, not success.
3. Say “It was not played on Spotify.” Expect an observation/report, with no automatic replay. If Spotify reports playback but you hear nothing, Otto asks about the audio rather than claiming it fixed it.
4. Say “Play my Liked Songs.” Expect a selection from up to 50 saved songs, verified against the selection and device; full-library shuffle is not implemented by this path.
5. Say “Open Spotify and search for The Hills by The Weeknd and play it.” Expect one music goal, not repeated play commands. This API workflow does not promise to show a UI search page or bring Spotify forward if its player is already available.
6. During a music attempt, press Ctrl+Alt again. Expect cancellation and no later success claim. Test this with Spotify initially closed so there is time to interrupt.

Record `you:`, `otto:` and details lines, whether the correct song was audible, and which Spotify device was used. Do not share token files. If device identification fails, tell us the Spotify device name so it can be configured. General multi-step apps/timers and task-bound clarification are still C3; this checklist is the music path only.

## Later checkpoints

Exact pass criteria will be updated as each batch lands.

- C2: voice requests for The Hills, then Over the Moon; confirm actual song/device, report “You did not play it,” and test cancellation. Requires the implemented verifier before live acceptance.
- C3/D: voice compound music/timer and app/input tasks, including failure in the first step; check dependent effects stop.
- E: speak while music plays; check volume drops and restores after success, cancellation and an empty F8 recording.
- F: invoke the offline evaluation/report flow; voice playback tests remain separate from simulated learning results.
