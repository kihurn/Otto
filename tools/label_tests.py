"""Check the labels on Laya's test set (otto-data/test_set.csv), one request at a time.

For each request you see my draft answer. Press Enter if it's right, or type the right area's
number. You can also add your own test requests. Progress is saved after every answer.

Run:  python -m tools.label_tests
      python -m tools.label_tests --all     (also re-check ones you've already checked)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, learning  # noqa: E402
from core.areas import AREAS  # noqa: E402

BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[92m", "\033[0m"
NAMES = list(AREAS)


def legend() -> str:
    return "  ".join(f"{i + 1}={a}" for i, a in enumerate(NAMES))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    config.ensure_data()
    rows = learning.load_test()
    todo = [r for r in rows if args.all or r["checked"].lower() != "y"]
    print(f"{BOLD}{len(rows)} test requests, {len(todo)} to check.{RESET}")
    print(f"{DIM}Enter = right   number = change area   d = delete   + = add your own   q = save and quit{RESET}")
    print(f"{DIM}Areas: {legend()}{RESET}\n")
    done = 0
    for r in todo:
        while True:
            ans = input(f"  {r['text']!r:55} -> {BOLD}{r['area']}{RESET}  ").strip().lower()
            if ans == "":
                r["checked"] = "y"
                break
            if ans == "q":
                learning.save_test(rows)
                print(f"Saved. {done} checked this time.")
                return
            if ans == "d":
                rows.remove(r)
                break
            if ans == "+":
                text = input("    your request: ").strip()
                area = input(f"    area ({legend()}): ").strip().lower()
                if text and (area.isdigit() and 1 <= int(area) <= len(NAMES) or area in NAMES):
                    area = NAMES[int(area) - 1] if area.isdigit() else area
                    rows.append({"text": text, "area": area, "checked": "y"})
                    print(f"    {GREEN}added{RESET}")
                continue
            if ans.isdigit() and 1 <= int(ans) <= len(NAMES):
                r["area"], r["checked"] = NAMES[int(ans) - 1], "y"
                break
            if ans in NAMES:
                r["area"], r["checked"] = ans, "y"
                break
            print(f"    {DIM}{legend()}{RESET}")
        done += 1
        learning.save_test(rows)
    learning.save_test(rows)
    print(f"{GREEN}All checked.{RESET} Next time Otto starts it will re-test Laya with these, "
          "or type :score / :retrain in Otto.")


if __name__ == "__main__":
    main()
