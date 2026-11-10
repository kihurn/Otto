"""Laya: decides which area a request belongs to, and how sure it is.

Uses Laya's trainable engine. Its learning lives in otto-data/laya/current/, older versions in
otto-data/laya/history/. A newly taught Laya only replaces the current one if it scores at least as
well on the test set.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime

from core import learning
from core.areas import AREA_QUESTION, AREAS
from core.config import LAYA_DIR, load_json, save_json

CURRENT = LAYA_DIR / "current"
HISTORY = LAYA_DIR / "history"
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
        self.meta: dict = load_json(CURRENT / META, {})
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
        if (CURRENT / META).exists() and self.meta.get("hash") == _rows_hash(rows):
            try:
                self.agent.load_calibration(str(CURRENT))
                say(f"  Laya's learning restored ({self.meta.get('n_rows')} examples, "
                    f"test score {self._score_text(self.meta)})")
                return
            except Exception as e:  # damaged or from another Laya version: just relearn
                say(f"  ! Couldn't restore Laya's learning ({type(e).__name__}); relearning.")
        self.retrain(say=say, force=True)

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
    def score(self) -> dict:
        tests = [r for r in learning.load_test() if r["area"] in AREAS]
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
        """Teach Laya every example, test it, and keep it only if it's at least as good."""
        rows = learning.training_rows(set(AREAS))
        say(f"  Teaching Laya {len(rows)} examples...")
        t0 = time.perf_counter()
        old_score = (self.meta.get("score") or {}).get("accuracy")
        self.agent.fit(rows, questions=AREA_QUESTION)
        result = self.score()
        took = time.perf_counter() - t0
        better = force or old_score is None or result["accuracy"] >= old_score
        if better:
            if CURRENT.exists():
                HISTORY.mkdir(parents=True, exist_ok=True)
                shutil.move(str(CURRENT), str(HISTORY / datetime.now().strftime("%Y%m%d-%H%M%S")))
            self.agent.save_calibration(str(CURRENT))
            self.meta = {"hash": _rows_hash(rows), "n_rows": len(rows), "device": self.device,
                         "saved": datetime.now().isoformat(timespec="seconds"),
                         "score": {k: result[k] for k in ("accuracy", "n", "checked", "per_area")},
                         "bars": result["bars"]}
            save_json(CURRENT / META, self.meta)
            say(f"  Done in {took:.0f}s. Test score {self._score_text(self.meta)}"
                + (f" (was {old_score:.0%})" if old_score is not None else "")
                + f". Confidence zones: act above {self.bars()[0]:.0%}, ask between, brain below {self.bars()[1]:.0%}.")
        else:
            say(f"  New learning scored {result['accuracy']:.0%}, worse than the current {old_score:.0%}; "
                f"keeping the current one.")
            self.agent.load_calibration(str(CURRENT))
        self.new_examples = 0
        return result

    def note_new_example(self, say=print) -> None:
        self.new_examples += 1
        if self.new_examples >= int(self.settings.get("laya", {}).get("retrain_every", 20)):
            self.retrain(say=say)
