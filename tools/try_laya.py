"""Type requests to Laya only (no actions), correct it, and watch it learn.

Every answer you confirm or correct is saved to otto-data/examples.csv, the same examples Otto
learns from. Laya relearns every 20 new examples, or when you type :retrain.

Run:  python -m tools.try_laya
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, guards, learning  # noqa: E402
from core.areas import AREAS  # noqa: E402
from core.router import Router  # noqa: E402

BOLD, DIM, GREEN, YELLOW, RESET = "\033[1m", "\033[2m", "\033[92m", "\033[93m", "\033[0m"
NAMES = list(AREAS)


def main() -> None:
    config.ensure_data()
    router = Router(config.load_settings())
    router.load()
    legend = "  ".join(f"{i + 1}={a}" for i, a in enumerate(NAMES))
    print(f"\n{BOLD}Type a request. Enter = right, a number = the right area, s = skip. "
          f":retrain, :score, :quit{RESET}\n{DIM}{legend}{RESET}")
    while True:
        try:
            text = input(f"{BOLD}laya>{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue
        if text in (":quit", ":q"):
            break
        if text == ":retrain":
            router.retrain()
            continue
        if text == ":score":
            from tools.score import show
            show(router)
            continue
        text, _ = guards.strip_wake(text)
        if guards.is_gibberish(text):
            print("  -> no real words: Otto would say \"Sorry, I didn't catch that.\"")
            continue
        p = router.predict(text)
        zone = router.zone(p["prob"])
        colour = {"high": GREEN, "middle": YELLOW}.get(zone, "")
        others = ", ".join(f"{a} {x:.0%}" for a, x in p["top"][1:3])
        what = {"high": "Otto would act", "middle": "Otto would ask you", "low": "Otto would ask the brain"}[zone]
        print(f"  -> {BOLD}{p['area']}{RESET} {p['prob']:.0%}  (then {others})  {colour}{what}{RESET}  {p['ms']:.0f} ms")
        ans = input("  right? ").strip().lower()
        if ans == "s":
            continue
        area = p["area"]
        if ans.isdigit() and 1 <= int(ans) <= len(NAMES):
            area = NAMES[int(ans) - 1]
        elif ans in NAMES:
            area = ans
        elif ans:
            print(f"  {DIM}(not understood, skipped){RESET}")
            continue
        if learning.add_example(text, area, source="you"):
            router.note_new_example()
        else:
            print(f"  {YELLOW}That's a test-set request, so it isn't taught (keeps the test honest).{RESET}")


if __name__ == "__main__":
    main()
