"""Talk to Laya by typing, correct it, and watch it learn.

Type any request (like "open spotify and search lofi"). Laya shows which area it thinks
it is, how sure it is, and whether Otto would act on its own (AUTO) or ask Gemma (ASK).
Then you say whether it was right. Every answer you confirm or correct is saved to
data/my_examples.csv, and Laya relearns from all examples every 10 new ones
(or whenever you type :retrain).

Laya is never taught the 44 requests in its test set, so ":test" stays an honest score.

Commands:
  :retrain   relearn now from every example          :test    score on the 44 test requests
  :stats     how many examples each area has          :help    show this again
  :quit      exit (Ctrl+C works too)

Run:  python try_laya.py
"""

from __future__ import annotations

import csv
import time
from collections import Counter

from otto_check.common import DATA_DIR, RESULTS_DIR, BOLD, GREEN, RED, RESET, YELLOW, info, title
from otto_check.intents import DOMAIN_QUESTION, DOMAINS

AREAS = list(DOMAINS)
MY_FILE = DATA_DIR / "my_examples.csv"
RETRAIN_EVERY = 10


def read_csv(path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(open(path, encoding="utf-8")))


def split_starter():
    """Same split as check_laya.py: every 3rd starter example per area is kept for testing."""
    rows = read_csv(DATA_DIR / "otto_intents_starter.csv")
    seen: Counter = Counter()
    train, test = [], []
    for r in rows:
        (test if seen[r["domain"]] % 3 == 2 else train).append(r)
        seen[r["domain"]] += 1
    return train, test


def load_my_examples() -> dict[str, str]:
    return {r["state"]: r["domain"] for r in read_csv(MY_FILE)}


def save_my_examples(mine: dict[str, str]) -> None:
    with open(MY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["state", "domain"])
        for state, domain in mine.items():
            w.writerow([state, domain])


def is_gibberish(text: str) -> bool:
    """True if not one word is a real word (English, slang or a known name).
    Checked before Laya, because Laya always picks *some* area, even for keyboard mashing."""
    from wordfreq import tokenize, zipf_frequency

    words = tokenize(text, "en")
    return bool(words) and not any(zipf_frequency(w, "en") >= 1.5 for w in words)


def norm(text: str) -> str:
    return " ".join(text.lower().strip().split())


class Session:
    def __init__(self, agent):
        self.agent = agent
        self.starter_train, self.test = split_starter()
        self.test_states = {norm(r["state"]) for r in self.test}
        self.more = read_csv(DATA_DIR / "otto_intents_more.csv")
        self.mine = load_my_examples()
        self.new_since_fit = 0

    def training_rows(self) -> list[dict]:
        rows = {norm(r["state"]): r["domain"] for r in self.starter_train + self.more}
        rows.update({norm(s): d for s, d in self.mine.items()})  # your labels win
        return [{"state": s, "gold": {"domain": d}} for s, d in rows.items() if s not in self.test_states]

    def retrain(self) -> None:
        rows = self.training_rows()
        t0 = time.perf_counter()
        print(f"  relearning from {len(rows)} examples...", end="", flush=True)
        self.agent.fit(rows, questions=DOMAIN_QUESTION)
        print(f" done in {time.perf_counter() - t0:.1f}s")
        self.agent.save_calibration(str(RESULTS_DIR / "laya_taught"))
        self.new_since_fit = 0

    def predict(self, text: str):
        t0 = time.perf_counter()
        a = self.agent.predict(text, DOMAIN_QUESTION)["answers"]["domain"]
        ms = (time.perf_counter() - t0) * 1000
        probs = sorted((a.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
        return a.get("choice"), probs, a.get("route"), ms

    def test_score(self) -> None:
        right = auto = auto_right = 0
        wrong = []
        for r in self.test:
            choice, probs, route, _ = self.predict(r["state"])
            ok = choice == r["domain"]
            right += ok
            if route == "auto":
                auto += 1
                auto_right += ok
            if not ok:
                wrong.append((r["state"], r["domain"], choice, route))
        n = len(self.test)
        print(f"  {BOLD}Test: {right}/{n} right ({right / n:.0%}).{RESET} "
              f"It would act alone on {auto}, and got {auto_right} of those right"
              + (f" ({auto_right / auto:.0%})." if auto else "."))
        for s, exp, got, route in wrong[:8]:
            print(f"    {s!r:48} should be {exp}, said {got} ({route})")
        if len(wrong) > 8:
            print(f"    ...and {len(wrong) - 8} more")

    def stats(self) -> None:
        counts = Counter(r["gold"]["domain"] for r in self.training_rows())
        mine = Counter(self.mine.values())
        for area in AREAS:
            print(f"  {area:9} {counts[area]:4} examples  ({mine[area]} of them yours)")
        print(f"  total     {sum(counts.values()):4}")

    def ask_label(self, text: str, guess: str) -> str | None:
        legend = "  ".join(f"{i + 1}={a}" for i, a in enumerate(AREAS))
        while True:
            reply = input(f"  Right? Enter = yes, s = skip, or the right area ({legend}): ").strip().lower()
            if reply == "":
                return guess
            if reply in ("s", "skip"):
                return None
            if reply.isdigit() and 1 <= int(reply) <= len(AREAS):
                return AREAS[int(reply) - 1]
            if reply in AREAS:
                return reply
            print("  (type a number from the list, an area name, Enter or s)")

    def handle(self, text: str) -> None:
        if is_gibberish(text):
            print(f"  -> {BOLD}unsure{RESET}: no real words found, so Laya isn't asked. "
                  f"Otto would say \"Sorry, I didn't catch that.\"")
            return
        choice, probs, route, ms = self.predict(text)
        top = probs[0][1] if probs else 0
        others = ", ".join(f"{a} {p:.0%}" for a, p in probs[1:3])
        if route == "auto":
            tag = f"{GREEN}AUTO: Otto would act{RESET}"
        else:
            tag = f"{YELLOW}ASK: Otto would check with Gemma{RESET}"
        print(f"  -> {BOLD}{choice}{RESET} {top:.0%}   (then {others})   {tag}   {ms:.0f} ms")

        label = self.ask_label(text, choice)
        if label is None:
            return
        if norm(text) in self.test_states:
            print(f"  {RED}That's one of the test requests, so it isn't saved (keeps :test honest).{RESET}")
            return
        if label != choice:
            print(f"  noted: {text!r} is {BOLD}{label}{RESET}")
        self.mine[text.strip()] = label
        save_my_examples(self.mine)
        self.new_since_fit += 1
        if self.new_since_fit >= RETRAIN_EVERY:
            print(f"  {RETRAIN_EVERY} new examples:", end="")
            self.retrain()


def main() -> None:
    title("Loading Laya's trainable engine")
    import torch
    import laya

    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.perf_counter()
    agent = laya.load(vegaml=True, device=device)
    info(f"loaded on {device} in {time.perf_counter() - t0:.0f}s")

    s = Session(agent)
    title("Teaching it the examples")
    s.retrain()
    s.test_score()

    title("Your turn")
    print(__doc__.split("Commands:")[1].split("Run:")[0].rstrip())
    print()
    while True:
        try:
            text = input(f"{BOLD}laya>{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not text:
            continue
        cmd = text.lower()
        try:
            if cmd in (":quit", ":q", ":exit"):
                break
            elif cmd in (":retrain", ":r"):
                s.retrain()
            elif cmd == ":test":
                s.test_score()
            elif cmd == ":stats":
                s.stats()
            elif cmd == ":help":
                print(__doc__)
            elif cmd.startswith(":"):
                print("  unknown command, try :help")
            else:
                s.handle(text)
        except KeyboardInterrupt:
            print("\n  (cancelled)")
    if s.new_since_fit:
        print(f"  {s.new_since_fit} new examples will be used next time you start.")
    print(f"  Your examples are in {MY_FILE.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
