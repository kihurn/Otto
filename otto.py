"""Otto: one command for everything.

  otto                    type to Otto                (add --speak to hear replies, --dry-run to only pretend)
  otto voice              talk to Otto ("Hey Otto, ...")   --mode wake|always|push
  otto mic [N|default|test]        list, choose or test microphones
  otto mode [wake|always|push]     how Otto listens by default
  otto speed [1.15]                talking speed
  otto voices [bella|michael|test] choose or hear Otto's voice
  otto model [JOB [MODEL]]         which AI model does which job
  otto settings / otto set KEY VALUE   show or change any setting
  otto spotify            connect Spotify (once)
  otto check              check keys, C0RE, GPU, Everything, Spotify, microphone
  otto label | score | teach      test-set labels, Laya's score, teach Laya by typing
  otto train --offline --tasks 100 --seed 42   simulated practice and report
  otto candidate                   fit and evaluate a separate Laya calibration
  otto promote ID | otto rollback  explicitly activate a passing candidate or restore the previous calibration
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

if os.name == "nt":
    os.system("")  # colours in older Windows consoles

from core import config

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = ("\033[1m", "\033[2m", "\033[92m", "\033[93m", "\033[91m",
                                              "\033[96m", "\033[0m")
JOBS = ("extract", "decide", "screen", "answer", "chat")
JOB_HELP = {"extract": "pulling out details, rewriting follow-ups", "decide": "guessing when Laya isn't sure, planning, splitting",
            "screen": "looking at your screen", "answer": "answering questions, writing", "chat": "small talk"}
_print_lock = threading.Lock()


def out(text: str = "", colour: str = "") -> None:
    with _print_lock:
        print(f"{colour}{text}{RESET}" if colour else text, flush=True)


def dim(text: str) -> None:
    out(text, DIM)


# =============================================================================================
# Settings commands (work both as  otto speed 1.2  and, while running, as  :speed 1.2)
# =============================================================================================

def cmd_speed(settings, args, live=None) -> None:
    if not args:
        out(f"Talking speed: {settings['voice_out']['speed']}  (1.0 = normal; try 1.1 to 1.3)")
        return
    try:
        v = max(0.5, min(2.0, float(args[0])))
    except ValueError:
        out("Give a number, e.g.  otto speed 1.2")
        return
    config.set_setting("voice_out.speed", v, settings)
    if live and live.get("mouth"):
        live["mouth"].speed = v
    out(f"Talking speed set to {v}.", GREEN)


def cmd_voices(settings, args, live=None) -> None:
    from senses.mouth import VOICE_NAMES, VOICES
    current = settings["voice_out"]["voice"]
    if not args:
        for key, name in VOICES.items():
            out(f"  {'*' if key == current else ' '} {name}   (otto voices {key.split('_')[1]})")
        out("  otto voices test   plays both")
        return
    choice = args[0].lower()
    if choice == "test":
        from senses.mouth import Mouth
        for key, name in VOICES.items():
            settings["voice_out"]["voice"] = key
            out(name)
            Mouth(settings, say=dim).say("Hey Ki Hurn, I'm Otto. Playing The Hills by The Weeknd.")
        settings["voice_out"]["voice"] = current
        return
    voice = VOICE_NAMES.get(choice, choice)
    if voice not in VOICES:
        out(f"Unknown voice. Choose: {', '.join(VOICE_NAMES)}")
        return
    config.set_setting("voice_out.voice", voice, settings)
    if live and live.get("mouth"):
        live["mouth"].set_voice(voice)
    out(f"Voice set to {VOICES[voice]}.", GREEN)


def cmd_mode(settings, args, live=None) -> None:
    modes = {"wake": "only acts when you say \"Hey Otto\" (then a short window to carry on)",
             "always": "every sentence is for Otto", "push": "only hears you while you hold the push-to-talk key"}
    current = settings["listen"]["mode"]
    if not args:
        for m, d in modes.items():
            out(f"  {'*' if m == current else ' '} {m:7} {d}")
        lk = settings["listen"]
        out(f"  push-to-talk key: {lk['push_to_talk_key'].upper()}   mute key: {lk['mute_key'].upper()}")
        return
    m = args[0].lower()
    if m not in modes:
        out("Choose wake, always or push.")
        return
    config.set_setting("listen.mode", m, settings)
    if live and live.get("ears"):
        live["ears"].mode = m
        live["ears"].flush()
    out(f"Listening mode: {m} ({modes[m]}).", GREEN)


def cmd_mic(settings, args, live=None) -> None:
    from senses.ears import list_mics
    mics = list_mics()
    current = settings["whisper"].get("mic_device")
    if not args:
        out("Microphones (use the first line with your mic's name, usually 'MME'):")
        for n, name, api, is_default in mics:
            mark = "*" if (current == n or (current is None and is_default)) else " "
            out(f"  {mark} {n:3}  {name[:55]:55} {DIM}{api}{' (Windows default)' if is_default else ''}{RESET}")
        out("  otto mic N  to choose,  otto mic default  for Windows' default,  otto mic test  to try it")
        return
    if args[0] == "test":
        mic_test(settings)
        return
    n = None if args[0] in ("default", "none", "null") else int(args[0])
    if n is not None and n not in [m[0] for m in mics]:
        out(f"There's no microphone number {n}. Run  otto mic  to see the list.")
        return
    config.set_setting("whisper.mic_device", n, settings)
    name = "Windows' default" if n is None else next(m[1] for m in mics if m[0] == n)
    if live and live.get("ears"):
        live["ears"].switch_mic(n, say=dim)
    out(f"Microphone set to {name}.", GREEN)


def cmd_model(settings, args, live=None) -> None:
    brains = settings["brains"]
    if not args:
        for job in JOBS:
            out(f"  {job:8} {' -> '.join(brains.get(job, []))}   {DIM}({JOB_HELP[job]}){RESET}")
        out("  otto model JOB MODEL   puts MODEL first for that job (others stay as backups)")
        out("  otto model all MODEL   puts MODEL first for every job")
        return
    if len(args) < 2:
        job = args[0]
        out(f"  {job}: {' -> '.join(brains.get(job, []))}" if job in brains else f"Jobs: {', '.join(JOBS)}")
        return
    job, model = args[0], args[1]
    for j in (JOBS if job == "all" else (job,)):
        if j not in JOBS:
            out(f"Unknown job. Jobs: {', '.join(JOBS)}")
            return
        chain = [model] + [m for m in brains.get(j, []) if m != model]
        config.set_setting(f"brains.{j}", chain, settings)
    out(f"{model} is now first for {job}. Make sure your C0RE key allows it.", GREEN)


def cmd_set(settings, args, live=None) -> None:
    if len(args) < 2:
        out("Use:  otto set KEY VALUE   e.g.  otto set listen.follow_up_s 10")
        return
    key, value = args[0], config.parse_value(" ".join(args[1:]))
    if config.get_setting(settings, key) is None and "." in key and config.get_setting(settings, key.rsplit(".", 1)[0]) is None:
        out(f"There's no setting called {key}. See  otto settings")
        return
    config.set_setting(key, value, settings)
    out(f"{key} = {json.dumps(value)}  (some changes apply next time Otto starts)", GREEN)


def cmd_settings(settings, args=None, live=None) -> None:
    show = {k: v for k, v in settings.items() if not k.startswith("_")}
    out(json.dumps(show, indent=2))
    dim(f"(stored in {config.SETTINGS_FILE}; change with  otto set KEY VALUE)")


SETTING_COMMANDS = {"speed": cmd_speed, "voices": cmd_voices, "voice": cmd_voices, "mode": cmd_mode,
                    "mic": cmd_mic, "model": cmd_model, "set": cmd_set, "settings": cmd_settings}


# =============================================================================================
# Other commands
# =============================================================================================

def mic_test(settings) -> None:
    from senses.ears import Ears
    s = json.loads(json.dumps(settings))
    s["listen"]["mode"] = "always"
    ears = Ears(s, say=dim)
    ears.open(say=dim)
    out("Talk; I'll write down what I hear. Ctrl+C to stop.", GREEN)
    try:
        while True:
            text, conf, secs = ears.listen()
            out(f"  heard: {text}  {DIM}({secs:.1f}s, sure {conf:.2f}){RESET}")
    except KeyboardInterrupt:
        ears.close()


def cmd_spotify(settings) -> None:
    from connectors import spotify
    from hands.web import open_in_browser
    if not spotify.configured():
        out("Add OTTO_SPOTIFY_CLIENT_ID to your .env first (see .env.example).", YELLOW)
        return
    if spotify.sign_in(say=out, open_url=open_in_browser):
        try:
            devs = spotify.devices()
            out(f"Spotify players I can see: {', '.join(d['name'] for d in devs) or 'none (open the Spotify app)'}")
        except Exception as e:
            out(f"Signed in, but couldn't list players: {e}", YELLOW)


def cmd_check(settings) -> None:
    def line(ok, label, detail=""):
        mark = f"{GREEN}OK  {RESET}" if ok is True else (f"{YELLOW}NOTE{RESET}" if ok is None else f"{RED}FIX {RESET}")
        out(f"  {mark} {label}" + (f": {detail}" if detail else ""))
    out(f"{BOLD}Otto check{RESET}")
    line(bool(config.ENV_FILES_USED) or None, "Keys file", ", ".join(config.ENV_FILES_USED) or "no .env found (using Windows variables)")
    line(bool(config.c0re_key()), "C0RE key", "set" if config.c0re_key() else "missing: add OTTO_C0RE_KEY to .env")
    line(True if config.ollama_key() else None, "Ollama web search key", "set" if config.ollama_key() else "not set (optional)")
    try:
        import urllib.request
        req = urllib.request.Request(settings["c0re_url"].rstrip("/") + "/api/tags",
                                     headers={"Authorization": f"Bearer {config.c0re_key() or ''}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        line(True, "C0RE", f"reachable, {len(names)} models listed")
        wanted = sorted({m for chain in settings["brains"].values() for m in chain if "cloud" not in m})
        missing = [m for m in wanted if m not in names]
        line(not missing or None, "Local models", "all present" if not missing else f"not listed: {', '.join(missing)}")
    except Exception as e:
        line(False, "C0RE", f"can't reach it ({type(e).__name__}). Is C0RE running?")
    try:
        import torch
        line(torch.cuda.is_available(), "GPU for Laya", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "not visible")
    except Exception as e:
        line(False, "PyTorch", str(e)[:80])
    from hands import files
    files.configure(settings)
    es = files.es_path()
    line(bool(es) or None, "Everything (file search)", es or "es.exe not found (README step 3)")
    from connectors import spotify
    if not spotify.configured():
        line(None, "Spotify", "OTTO_SPOTIFY_CLIENT_ID not in .env")
    elif not spotify.signed_in():
        line(None, "Spotify", "not connected yet: run  otto spotify")
    else:
        try:
            devs = spotify.devices()
            line(True, "Spotify", f"connected; players: {', '.join(d['name'] for d in devs) or 'none open right now'}")
        except Exception as e:
            line(False, "Spotify", str(e)[:100])
    try:
        from senses.ears import list_mics
        mics = list_mics()
        cur = settings["whisper"].get("mic_device")
        name = next((m[1] for m in mics if (m[0] == cur if cur is not None else m[3])), "none")
        line(name != "none", "Microphone", f"{name} (change with  otto mic)")
    except Exception as e:
        line(False, "Microphone", str(e)[:80])
    try:
        from hands import media
        ss = media.sessions()
        line(ss is not None or None, "Windows media controls", "available" if ss is not None else "not available (reinstall: setup.ps1)")
    except Exception:
        line(None, "Windows media controls", "not available")
    mode = settings["listen"]
    out(f"  Listening mode: {mode['mode']}, push-to-talk {mode['push_to_talk_key'].upper()}, mute {mode['mute_key'].upper()}, "
        f"voice {settings['voice_out']['voice']} at speed {settings['voice_out']['speed']}")


# =============================================================================================
# Running Otto
# =============================================================================================

HELP_RUNNING = f"""
{BOLD}While Otto is running{RESET}
  :mic [N|test]   :mode [wake|always|push]   :speed [x]   :voice [bella|michael]   :model [JOB MODEL]
  :set KEY VALUE  :settings   :mute (voice mode)   :retrain   :score   :timers   :details   :reload   :quit
{BOLD}Things to try{RESET}
  play the hills by the weeknd | play my music | what's playing | pause | skip | volume 30
  open youtube | google best gaming mouse | find my resume | write down call the bank tomorrow
  set a timer for 10 minutes | what's 15 percent of 80 | what's on my screen
  open spotify and play my music, then set a timer for 20 minutes   (several steps)
  when it asks: yes / no / say it another way      after something it worked out: save that
"""


def run(settings, voice: bool, speak: bool, dry_run: bool, mode: str | None) -> None:
    out(f"{BOLD}Otto{RESET} {DIM}1.1{RESET}")
    if not config.c0re_key():
        out("OTTO_C0RE_KEY isn't set (add it to your .env), so anything needing the brain will fail.", YELLOW)

    from core.guards import wake_rest
    from core.pipeline import Otto
    from hands import timers

    otto = Otto(settings, dry_run=dry_run, say=dim)
    dim("Starting up...")
    otto.start()
    live: dict = {"otto": otto, "mouth": None, "ears": None}

    if voice or speak:
        try:
            from senses.mouth import Mouth
            live["mouth"] = Mouth(settings, say=dim)
        except Exception as e:
            out(f"  ! Voice replies aren't available ({type(e).__name__}: {e}). Carrying on with text.", YELLOW)
    if voice:
        if mode:
            settings["listen"]["mode"] = mode
        try:
            from senses.ears import Ears
            live["ears"] = Ears(settings, say=dim)
            live["ears"].open(say=dim)
            if live["mouth"]:
                live["mouth"].ears = live["ears"]
        except Exception as e:
            out(f"  ! The microphone isn't available ({type(e).__name__}: {e}). Switching to typing.", YELLOW)
            live["ears"] = None
    mouth, ears = live["mouth"], live["ears"]
    from core.audio_focus import AudioFocus
    duck_settings = settings.get('audio_duck', {})
    duck = AudioFocus(bool(ears and not dry_run and duck_settings.get('enabled', True)),
                      cap=max(0, min(100, float(duck_settings.get('cap_percent', 20)))) / 100,
                      idle_seconds=max(1, float(duck_settings.get('idle_timeout_s', 30))), warn=dim)

    def speak_text(text: str) -> None:
        if live["mouth"] and text:
            try:
                with duck.hold():
                    live["mouth"].say(text)
            except Exception as e:
                dim(f"  (couldn't speak: {type(e).__name__})")

    def announce(msg: str) -> None:
        out(f"\n{CYAN}otto:{RESET} {msg}")
        if live["mouth"]:
            threading.Thread(target=speak_text, args=(msg,), daemon=True).start()

    timers.announce[0] = announce

    def task_progress(msg):
        out(f"{CYAN}otto:{RESET} {msg}")
        speak_text(msg)

    otto.progress = task_progress

    def beep() -> None:
        if settings["listen"].get("beep", True) and os.name == "nt":
            import winsound
            threading.Thread(target=winsound.Beep, args=(988, 90), daemon=True).start()

    force = threading.Event()   # push-to-talk key held in wake mode: next sentence is for Otto

    def toggle_mute() -> None:
        if not ears:
            return
        if ears.muted.is_set():
            ears.muted.clear()
            out(f"{GREEN}(listening again){RESET}")
        else:
            ears.muted.set()
            duck.release('push')
            ears.flush()
            out(f"{YELLOW}(muted: press {settings['listen']['mute_key'].upper()} to unmute){RESET}")

    if ears:
        from senses import keys
        lk = settings["listen"]

        def down():
            if otto.active_task:
                otto.active_task.cancel.set()
            force.set()
            if not ears.muted.is_set():
                duck.acquire('push')
            ears.push_down()

        ok = keys.start(lk["push_to_talk_key"], lk["mute_key"], down, ears.push_up, toggle_mute)
        if not ok:
            out("  ! Hotkeys aren't available (pynput missing); push-to-talk and the mute key won't work.", YELLOW)

    if dry_run:
        out("DRY RUN: Otto will say what it would do, without doing it.", YELLOW)
    if ears:
        lk = settings["listen"]
        how = {"wake": "Say \"Hey Otto, ...\"", "always": "Just talk", "push": f"Hold {lk['push_to_talk_key'].upper()} and talk"}
        out(f"{how[ears.mode]}. {lk['push_to_talk_key'].upper()} = push to talk, {lk['mute_key'].upper()} = mute, Ctrl+C = quit.", GREEN)
    else:
        out("Type to Otto. :help for commands and ideas.", GREEN)

    try:
        awake_until = 0.0
        while True:
            conf = None
            try:
                if ears:
                    text, conf, secs = ears.listen()
                    forced = force.is_set()
                    force.clear()
                    lk = settings["listen"]
                    rest = wake_rest(text, lk.get("wake_words", []))
                    if ears.mode == "wake" and not forced and rest is None and time.time() > awake_until and not otto.pending:
                        if settings.get("show_details"):
                            dim(f"  (not for me: {text[:60]})")
                        continue
                    if rest is not None:
                        text = rest
                    if not text:
                        duck.release('push')
                        beep()
                        speak_text("Yeah?")
                        awake_until = time.time() + float(lk.get("follow_up_s", 8))
                        continue
                    if ears.mode == "wake":
                        beep()
                    out(f"{BOLD}you:{RESET} {text}  {DIM}({secs:.1f}s, sure {conf:.2f}){RESET}")
                    import re
                    if re.fullmatch(r"(?:stop listening|mute(?: yourself)?|go to sleep|be quiet)[.!]*", text.strip(), re.I):
                        toggle_mute()
                        continue
                else:
                    text = input(f"{BOLD}you>{RESET} ").strip()
            except (KeyboardInterrupt, EOFError):
                out("\nBye!", DIM)
                break
            if not text:
                continue

            if text.startswith(":"):
                parts = text[1:].split()
                cmd, args = (parts[0].lower(), parts[1:]) if parts else ("", [])
                if cmd in ("quit", "q", "exit"):
                    break
                if cmd == "help":
                    out(HELP_RUNNING)
                elif cmd in SETTING_COMMANDS:
                    if cmd == "mic" and args and args[0] == "test":
                        out("Stop Otto first, then run  otto mic test")
                    else:
                        SETTING_COMMANDS[cmd](settings, args, live)
                elif cmd == "mute":
                    toggle_mute()
                elif cmd == "retrain":
                    otto.router.retrain(say=dim)
                elif cmd == "score":
                    from tools.score import show
                    show(otto.router)
                elif cmd == "timers":
                    out(timers.time_left().say)
                elif cmd == "details":
                    settings["show_details"] = not settings.get("show_details", True)
                    dim(f"Details {'on' if settings['show_details'] else 'off'}.")
                elif cmd == "reload":
                    settings.clear()
                    settings.update(config.load_settings())
                    otto.apps.refresh()
                    dim(f"Settings reloaded; {len(otto.apps.apps)} apps known.")
                else:
                    dim("Unknown command. :help shows them.")
                continue

            with duck.hold():
                duck.release('push')
                try:
                    reply = otto.handle(text, heard_conf=conf)
                except KeyboardInterrupt:
                    dim("(cancelled)")
                    continue
                except Exception as e:  # never crash the whole assistant on one bad request
                    out(f"Something went wrong: {type(e).__name__}: {e}", RED)
                    continue
                if reply.text:
                    out(f"{CYAN}otto:{RESET} {reply.text}")
                if reply.details and settings.get("show_details", True):
                    dim(f"      {reply.details}")
                speak_text(reply.speak if reply.speak is not None else reply.text)
                awake_until = time.time() + float(settings["listen"].get("follow_up_s", 8))
    finally:
        duck.close()
        if ears:
            from senses import keys
            keys.stop()
            ears.close()


def main() -> int:
    ap = argparse.ArgumentParser(prog="otto", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="", help="see the list above")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--speak", action="store_true", help="answer out loud when typing")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen, don't do it")
    ap.add_argument("--mode", choices=["wake", "always", "push"], help="listening mode for this run")
    ap.add_argument("--voice", action="store_true", help=argparse.SUPPRESS)   # old style: otto --voice
    ap.add_argument('--offline', action='store_true', help='run isolated simulated training evaluation')
    ap.add_argument('--tasks', type=int, default=100, help='number of offline scenarios')
    ap.add_argument('--seed', type=int, default=42, help='offline scenario seed')
    ap.add_argument('--baseline', help='previous offline run ID for comparison')
    a = ap.parse_args()

    cmd = a.command.lower()
    if cmd == 'train':
        if not a.offline or a.args:
            out('Use otto train --offline --tasks 100 --seed 42.')
            return 1
        from core.offline_eval import run as evaluate
        try:
            directory, metrics = evaluate(a.tasks, a.seed, a.baseline)
        except ValueError as error:
            out(str(error), RED)
            return 1
        out(f'Simulated tasks passed {metrics["passed"]}/{metrics["total"]}.')
        out(str(directory/'REPORT.md'))
        return int(metrics['passed'] != metrics['total'])

    config.ensure_data()
    settings = config.load_settings()

    if cmd in ("", "type", "text"):
        run(settings, voice=a.voice, speak=a.speak, dry_run=a.dry_run, mode=a.mode)
    elif cmd in ("voice", "talk", "listen") and not a.args:
        run(settings, voice=True, speak=True, dry_run=a.dry_run, mode=a.mode)
    elif cmd in SETTING_COMMANDS:
        SETTING_COMMANDS[cmd](settings, a.args)
    elif cmd == "spotify":
        cmd_spotify(settings)
    elif cmd == "check":
        cmd_check(settings)
    elif cmd in ("label", "labels", "label_tests"):
        from tools import label_tests
        sys.argv = ["label_tests"] + a.args
        label_tests.main()
    elif cmd == "score":
        from tools import score
        score.main()
    elif cmd == 'candidate' and not a.args:
        from core.router import Router
        router = Router(settings)
        router.load()
        router.retrain()
    elif cmd == 'promote' and len(a.args) == 1:
        from core.router import Router
        from core.training import promote
        try:
            directory = promote(Router(settings), a.args[0])
        except (ValueError, OSError) as error:
            out(str(error), RED)
            return 1
        out(f'Active calibration is now {directory.name}. Restart Otto to load it.')
    elif cmd == 'rollback' and not a.args:
        from core.training import rollback
        try:
            target = rollback()
        except (ValueError, OSError) as error:
            out(str(error), RED)
            return 1
        out(f'Restored {target.name}. Restart Otto to load it.')
    elif cmd in ("teach", "try_laya"):
        from tools import try_laya
        try_laya.main()
    elif cmd in ("help", "-h"):
        out(__doc__)
    else:
        out(f"Unknown command {cmd!r}.\n{__doc__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
