"""Laya: decides which area a request belongs to, and how sure it is.

Uses Laya's trainable engine. The original calibration lives in otto-data/laya/current/.
Candidate calibrations are staged separately and selected through an explicit active pointer.
"""

from __future__ import annotations

import hashlib
import time

from core import learning
from core.areas import AREA_QUESTION, AREAS
from core.config import LAYA_DIR, load_json

CURRENT = LAYA_DIR / "current"
META = "otto_meta.json"


def _rows_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r["state"]):
        h.update(f"{r['state']}\t{r['gold']['area']}\n".encode())
    return h.hexdigest()[:16]


def measure_bars(preds: list[dict], act_precision: float = 0.95, guess_precision: float = 0.6,
                 min_count: int = 8) -> dict:
    """Find the lowest confidence where Laya is right often enough. preds: [{prob, right}]."""
    out = {"act_bar": None, "guess_bar": None}
    ordered = sorted(preds, key=lambda p: -p["prob"])
    right = 0
    for i, p in enumerate(ordered, 1):
        right += p["right"]
        precision = right / i
        if i >= min_count and precision >= act_precision:
            out["act_bar"] = round(p["prob"], 3)
        if i >= min_count and precision >= guess_precision:
            out["guess_bar"] = round(p["prob"], 3)
    if out["act_bar"] is not None and out["guess_bar"] is not None and out["guess_bar"] > out["act_bar"]:
        out["guess_bar"] = out["act_bar"]
    return out


class Router:
    def __init__(self, settings: dict):
        self.settings = settings
        self.agent = None
        self.device = None
        pointer = load_json(CURRENT.parent / 'active.json', {})
        name = pointer.get('candidate', '') if isinstance(pointer, dict) else ''
        candidate = CURRENT.parent / 'candidates' / name if isinstance(name, str) and len(name) == 32 and name.isalnum() else CURRENT
        self.calibration = candidate if (candidate / META).is_file() else CURRENT
        self.meta: dict = load_json(self.calibration / META, {})
        self.new_examples = 0

    # ---- loading ---------------------------------------------------------------------------
    def load(self, say=print) -> None:
        import torch
        import laya

        want = self.settings.get("laya", {}).get("device", "cuda")
        self.device = "cuda" if (want == "cuda" and torch.cuda.is_available()) else "cpu"
        if want == "cuda" and self.device == "cpu":
            say("  ! The GPU isn't visible to PyTorch, so Laya runs on the processor (slower).")
        t0 = time.perf_counter()
        self.agent = laya.load(vegaml=True, device=self.device)
        say(f"  Laya loaded on {self.device.upper()} in {time.perf_counter() - t0:.0f}s")

        rows = learning.training_rows(set(AREAS))
        if (self.calibration / META).exists():
            try:
                self.agent.load_calibration(str(self.calibration))
                say(f"  Laya's learning restored ({self.meta.get('n_rows')} examples, "
                    f"test score {self._score_text(self.meta)})")
                if self.meta.get('hash') != _rows_hash(rows):
                    say('  New examples are ready for candidate training with :retrain.')
                return
            except Exception as e:
                say(f"  ! Couldn't restore Laya's learning ({type(e).__name__}).")
        say('  No usable saved calibration. Use :retrain to create a reviewable candidate.')

    # ---- deciding --------------------------------------------------------------------------
    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        a = self.agent.predict(text, AREA_QUESTION)["answers"]["area"]
        probs = a.get("probabilities") or {}
        area = a.get("choice")
        prob = probs.get(area, a.get("answer_confidence") or 0.0)
        top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
        return {"area": area, "prob": float(prob), "top": top, "ms": (time.perf_counter() - t0) * 1000}

    def bars(self) -> tuple[float, float]:
        """(act_bar, guess_bar). Measured on the test set when possible, but never bolder than the floors:
        a 100-request exam is small, so Otto stays a little cautious and always keeps an 'ask you' zone."""
        z = self.settings.get("zones", {})
        act, guess = float(z.get("act_bar", 0.85)), float(z.get("guess_bar", 0.40))
        if z.get("use_measured", True):
            m = self.meta.get("bars") or {}
            if m.get("act_bar") is not None:
                act = max(float(m["act_bar"]), float(z.get("act_bar_floor", 0.70)))
            if m.get("guess_bar") is not None:
                guess = float(m["guess_bar"])
        gap = float(z.get("ask_zone_min", 0.20))
        guess = max(0.15, min(guess, act - gap))
        return float(act), float(guess)

    def zone(self, prob: float) -> str:
        act, guess = self.bars()
        return "high" if prob >= act else ("middle" if prob >= guess else "low")

    # ---- testing and learning --------------------------------------------------------------
    def score(self, tests=None) -> dict:
        tests = [r for r in (learning.load_test() if tests is None else tests) if r['area'] in AREAS]
        preds = []
        for r in tests:
            p = self.predict(r["text"])
            preds.append({"text": r["text"], "gold": r["area"], "pred": p["area"],
                          "prob": round(p["prob"], 3), "right": p["area"] == r["area"]})
        n = len(preds)
        acc = sum(p["right"] for p in preds) / n if n else 0.0
        per_area = {}
        for a in AREAS:
            rows = [p for p in preds if p["gold"] == a]
            if rows:
                per_area[a] = round(sum(p["right"] for p in rows) / len(rows), 3)
        return {"accuracy": round(acc, 3), "n": n, "checked": sum(r["checked"].lower() == "y" for r in tests),
                "per_area": per_area, "bars": measure_bars(preds), "preds": preds}

    @staticmethod
    def _score_text(meta: dict) -> str:
        s = meta.get("score") or {}
        return f"{s.get('accuracy', 0):.0%} on {s.get('n', 0)} test requests" if s else "not measured"

    def retrain(self, say=print, force: bool = False) -> dict:
        """Stage a separate candidate. The active calibration is never fitted in place."""
        from core.training import stage_candidate
        result = stage_candidate(self, say)
        self.new_examples = 0
        return result

    def note_new_example(self, say=print) -> None:
        self.new_examples += 1
        if self.new_examples == int(self.settings.get('laya', {}).get('retrain_every', 20)):
            say('  New examples are ready. Use :retrain to evaluate a separate candidate.')
