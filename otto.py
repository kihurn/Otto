"""Otto, Phase 1.

  python otto.py              type to Otto
  python otto.py --speak      type to Otto, and it answers out loud
  python otto.py --voice      talk to Otto, and it answers out loud
  python otto.py --dry-run    show what Otto would do without doing it

While running, type :help for commands.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading

if os.name == "nt":
    os.system("")  # turn on colours in older Windows consoles

from core import config

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = ("\033[1m", "\033[2m", "\033[92m", "\033[93m", "\033[91m",
                                              "\033[96m", "\033[0m")

HELP = f"""
{BOLD}Commands{RESET}
  :retrain   teach Laya every example now and re-test it
  :score     test Laya on your test set (and show its mistakes)
  :timers    show running timers
  :details   show/hide the grey line explaining each decision
  :reload    re-read otto-data/settings.json and refresh the app list
  :quit      exit (Ctrl+C works too)
{BOLD}Things to try{RESET}
  open spotify and search lofi | pause | volume 30 | open youtube | google best keyboards
  find my resume | write a note saying buy milk | set a timer for 10 minutes
  what's 15 percent of 80 | who won the last world cup | what's on my screen
  and when it asks you something: yes / no / say it another way
  after something worked that it had to figure out: save that
"""

_print_lock = threading.Lock()


def out(text: str = "", colour: str = "") -> None:
    with _print_lock:
        print(f"{colour}{text}{RESET}" if colour else text, flush=True)


def check_key() -> bool:
    if config.c0re_key():
        return True
    out("OTTO_C0RE_KEY isn't set, so Otto can't reach its brain.", RED)
    out("Follow README step 2, then open a NEW PowerShell window.")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", action="store_true", help="talk to Otto (it answers out loud)")
    ap.add_argument("--speak", action="store_true", help="type to Otto, it answers out loud")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen, don't do it")
    args = ap.parse_args()

    config.ensure_data()
    settings = config.load_settings()
    out(f"{BOLD}Otto{RESET} {DIM}phase 1{RESET}")
    if not check_key():
        out("(Otto still starts, but anything needing the brain will fail.)", YELLOW)

    from core.pipeline import Otto
    from hands import timers

    otto = Otto(settings, dry_run=args.dry_run, say=lambda s: out(s, DIM))
    out("Starting up...", DIM)
    otto.start()

    mouth = ears = None
    if args.voice or args.speak:
        try:
            from senses.mouth import Mouth
            mouth = Mouth(settings, say=lambda s: out(s, DIM))
        except Exception as e:
            out(f"  ! Voice replies aren't available ({type(e).__name__}: {e}). Carrying on with text.", YELLOW)
    if args.voice:
        try:
            from senses.ears import Ears
            ears = Ears(settings, say=lambda s: out(s, DIM))
            ears.open(say=lambda s: out(s, DIM))
            if mouth:
                mouth.ears = ears
        except Exception as e:
            out(f"  ! The microphone isn't available ({type(e).__name__}: {e}). Switching to typing.", YELLOW)
            ears = None

    def speak(text: str) -> None:
        if mouth and text:
            try:
                mouth.say(text)
            except Exception as e:
                out(f"  (couldn't speak: {type(e).__name__})", DIM)

    def announce(msg: str) -> None:
        out(f"\n{CYAN}otto:{RESET} {msg}")
        if mouth:
            threading.Thread(target=speak, args=(msg,), daemon=True).start()

    timers.announce[0] = announce

    if args.dry_run:
        out("DRY RUN: Otto will say what it would do, without doing it.", YELLOW)
    out(("Listening. Say something like \"Otto, open Spotify\". Ctrl+C to stop." if ears else
         "Type to Otto. :help for commands and ideas."), GREEN)

    while True:
        try:
            if ears:
                text, conf, secs = ears.listen()
                out(f"{BOLD}you:{RESET} {text}  {DIM}(heard in {secs:.1f}s, sure {conf:.2f}){RESET}")
            else:
                conf = None
                text = input(f"{BOLD}you>{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            out("\nBye!", DIM)
            break
        if not text:
            continue

        if text.startswith(":"):
            cmd = text.lower()
            if cmd in (":quit", ":q", ":exit"):
                break
            if cmd == ":help":
                out(HELP)
            elif cmd == ":retrain":
                otto.router.retrain(say=lambda s: out(s, DIM))
            elif cmd == ":score":
                from tools.score import show
                show(otto.router)
            elif cmd == ":timers":
                out(timers.time_left().say)
            elif cmd == ":details":
                settings["show_details"] = not settings.get("show_details", True)
                out(f"Details {'on' if settings['show_details'] else 'off'}.", DIM)
            elif cmd == ":reload":
                settings.clear()
                settings.update(config.load_settings())
                otto.apps.refresh()
                out(f"Settings reloaded; {len(otto.apps.apps)} apps known.", DIM)
            else:
                out("Unknown command. :help shows them.", DIM)
            continue

        try:
            reply = otto.handle(text, heard_conf=conf)
        except KeyboardInterrupt:
            out("(cancelled)", DIM)
            continue
        except Exception as e:  # never crash the whole assistant on one bad request
            out(f"Something went wrong: {type(e).__name__}: {e}", RED)
            continue
        if reply.text:
            out(f"{CYAN}otto:{RESET} {reply.text}")
        if reply.details and settings.get("show_details", True):
            out(f"      {reply.details}", DIM)
        speak(reply.speak if reply.speak is not None else reply.text)

    if ears:
        ears.close()


if __name__ == "__main__":
    sys.exit(main())
