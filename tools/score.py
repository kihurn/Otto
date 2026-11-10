"""Test Laya on your test set: overall score, each area, the confidence zones, and its mistakes.

Run:  python -m tools.score
(or type :score while Otto is running)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


def show(router) -> dict:
    r = router.score()
    if not r["n"]:
        print("The test set is empty. Run: python -m tools.label_tests")
        return r
    print(f"{BOLD}Test score: {r['accuracy']:.0%}{RESET} on {r['n']} requests "
          f"({r['checked']} of them checked by you).")
    print("By area:  " + "  ".join(f"{a} {v:.0%}" for a, v in r["per_area"].items()))
    act, guess = router.bars()
    preds = r["preds"]
    alone = [p for p in preds if p["prob"] >= act]
    ask = [p for p in preds if guess <= p["prob"] < act]
    low = [p for p in preds if p["prob"] < guess]
    right = sum(p["right"] for p in alone)
    print(f"Zones in use: act alone above {act:.0%}, ask between {guess:.0%} and {act:.0%}, brain below {guess:.0%}.")
    if alone:
        print(f"  Acts alone on {len(alone)} of {len(preds)} ({len(alone) / len(preds):.0%}); "
              f"right {right}/{len(alone)} ({right / len(alone):.0%}) of those. Target: 95%+.")
    print(f"  Would ask you about {len(ask)}; would ask the brain about {len(low)}.")
    m = r["bars"]
    print(f"{DIM}  Measured from this test: act bar {m['act_bar']}, guess bar {m['guess_bar']} "
          f"(None = not enough test requests yet to measure){RESET}")
    wrong = [p for p in preds if not p["right"]]
    if wrong:
        print("Mistakes (request -> should be / said, confidence):")
        for p in sorted(wrong, key=lambda p: -p["prob"])[:15]:
            zone = "ACTS" if p["prob"] >= act else ("asks" if p["prob"] >= guess else "brain")
            print(f"  {p['text']!r:50} -> {p['gold']} / {p['pred']} ({p['prob']:.0%}, {zone})")
        if len(wrong) > 15:
            print(f"  ...and {len(wrong) - 15} more")
    return r


def main() -> None:
    from core import config
    from core.router import Router

    config.ensure_data()
    router = Router(config.load_settings())
    router.load()
    show(router)


if __name__ == "__main__":
    main()
