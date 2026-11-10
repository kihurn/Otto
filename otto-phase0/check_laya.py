"""Phase 0, check 2: does Laya run on your GPU, how fast, and how good is it out of the box?

Part A (always): loads Laya's fast English model on the GPU and the processor, then asks it
  "which area is this request?" for 44 example requests it has never seen.
Part B (--train): loads Laya's trainable engine, teaches it from 88 other examples
  (takes seconds, no long training run), and measures the same 44 requests again.
  This is a first taste of how "Otto, save that" will make it smarter.

The examples are in data/otto_intents_starter.csv. They're a rough starter set I wrote,
not your real test set; that comes in Phase 1.

Run:  python check_laya.py
      python check_laya.py --train      (downloads about 2 GB more the first time)
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from collections import Counter, defaultdict

from otto_check.common import DATA_DIR, RESULTS_DIR, Results, gb, gpu_memory, info, title
from otto_check.intents import DOMAIN_QUESTION

FAST_MODEL = "convaiinnovations/laya"


def load_rows():
    rows = list(csv.DictReader(open(DATA_DIR / "otto_intents_starter.csv", encoding="utf-8")))
    by_domain = defaultdict(list)
    for r in rows:
        by_domain[r["domain"]].append(r)
    fit, held = [], []
    for domain_rows in by_domain.values():
        for i, r in enumerate(domain_rows):
            (held if i % 3 == 2 else fit).append(r)
    return fit, held


def answer_of(result) -> tuple[str, float, str | None]:
    a = result["answers"]["domain"]
    conf = a.get("answer_confidence")
    if conf is None and a.get("probabilities"):
        conf = max(a["probabilities"].values())
    return a.get("choice"), float(conf or 0.0), a.get("route")


def evaluate(agent, rows, label: str, res: Results, key: str) -> dict:
    # warm up so the first-call setup isn't counted
    for _ in range(3):
        agent.predict("open spotify", DOMAIN_QUESTION)
    times, correct, misses, routes = [], 0, [], Counter()
    for r in rows:
        t0 = time.perf_counter()
        out = agent.predict(r["state"], DOMAIN_QUESTION)
        times.append((time.perf_counter() - t0) * 1000)
        got, conf, route = answer_of(out)
        if route:
            routes[route] += 1
        if got == r["domain"]:
            correct += 1
        else:
            misses.append((r["state"], r["domain"], got, conf))
    acc = correct / len(rows)
    med = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95) - 1]
    res.numbers[key] = {"accuracy": round(acc, 3), "correct": correct, "total": len(rows),
                        "median_ms": round(med, 1), "p95_ms": round(p95, 1),
                        "routes": dict(routes),
                        "misses": [{"request": s, "expected": e, "got": g, "confidence": round(c, 2)}
                                   for s, e, g, c in misses]}
    info(f"{label}: {correct}/{len(rows)} correct ({acc:.0%}), "
         f"median {med:.0f} ms, slowest 5% {p95:.0f} ms" +
         (f", routes {dict(routes)}" if routes else ""))
    return res.numbers[key]


def show_misses(stats: dict, limit: int = 12) -> None:
    if not stats["misses"]:
        return
    info("Mistakes (request -> expected / got, confidence):")
    for m in stats["misses"][:limit]:
        info(f"  {m['request']!r:52} -> {m['expected']} / {m['got']} ({m['confidence']:.2f})")
    if len(stats["misses"]) > limit:
        info(f"  ...and {len(stats['misses']) - limit} more (see results/laya.json)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true", help="also test teaching Laya from examples")
    args = ap.parse_args()
    res = Results("laya")

    # --- PyTorch and the GPU ---------------------------------------------------------------
    title("PyTorch and the GPU")
    try:
        import torch
    except ImportError:
        res.failed("PyTorch installed", "not found", "Run README step 4 again.")
        res.save()
        return
    cuda = torch.cuda.is_available()
    res.numbers["torch"] = {"version": torch.__version__, "cuda": torch.version.cuda, "gpu": cuda}
    if cuda:
        res.passed("PyTorch sees the GPU", f"{torch.cuda.get_device_name(0)}, torch {torch.__version__}")
    else:
        res.failed("PyTorch sees the GPU", f"torch {torch.__version__} is the processor-only build",
                   "Run the 'pip install torch ... --index-url' line from README step 4 again.")

    try:
        import laya
        res.passed("Laya installed", f"version {laya.__version__}")
    except ImportError:
        res.failed("Laya installed", "not found", "Run README step 4 again.")
        res.save()
        return

    fit_rows, held_rows = load_rows()
    info(f"{len(held_rows)} test requests, {len(fit_rows)} teaching examples, "
         f"{len(DOMAIN_QUESTION['domain']['criteria'])} areas")

    # --- Part A: fast model, out of the box ------------------------------------------------
    title("Part A: Laya fast model, untrained")
    if cuda:
        torch.cuda.reset_peak_memory_stats()
        before = gpu_memory()
        t0 = time.perf_counter()
        info("loading on the GPU (first time downloads ~0.8 GB)...")
        try:
            agent = laya.load(FAST_MODEL, device="cuda")
        except Exception as e:
            res.failed("Laya loads on the GPU", f"{type(e).__name__}: {e}"[:300])
            res.save()
            return
        load_s = time.perf_counter() - t0
        res.passed("Laya loads on the GPU", f"{load_s:.1f}s")
        stats = evaluate(agent, held_rows, "GPU", res, "fast_gpu")
        peak = torch.cuda.max_memory_allocated() / 1024 / 1024
        after = gpu_memory()
        res.numbers["fast_gpu"]["torch_peak_mb"] = round(peak)
        if before and after:
            res.numbers["fast_gpu"]["gpu_used_delta_mb"] = after["used_mb"] - before["used_mb"]
            info(f"graphics memory: about {gb(after['used_mb'] - before['used_mb'])} "
                 f"(PyTorch peak {gb(peak)})")
        if stats["median_ms"] < 100:
            res.passed("Laya is fast on the GPU", f"{stats['median_ms']:.0f} ms per decision")
        else:
            res.noted("Laya is slower than expected on the GPU", f"{stats['median_ms']:.0f} ms")
        res.noted("Untrained accuracy (just a first look)",
                  f"{stats['correct']}/{stats['total']} = {stats['accuracy']:.0%}")
        show_misses(stats)
        del agent
        torch.cuda.empty_cache()

    info("loading on the processor for comparison...")
    try:
        cpu_agent = laya.load(FAST_MODEL, device="cpu")
        cpu_stats = evaluate(cpu_agent, held_rows[:15], "Processor (15 requests)", res, "fast_cpu")
        res.passed("Laya runs on the processor", f"{cpu_stats['median_ms']:.0f} ms per decision")
        if not cuda:
            res.noted("Untrained accuracy (15 requests)", f"{cpu_stats['accuracy']:.0%}")
            show_misses(cpu_stats)
        del cpu_agent
    except Exception as e:
        res.failed("Laya runs on the processor", f"{type(e).__name__}: {e}"[:300])

    # --- Part B: teach it from examples ------------------------------------------------------
    if args.train:
        title("Part B: teaching Laya from 88 examples")
        device = "cuda" if cuda else "cpu"
        try:
            if cuda:
                torch.cuda.reset_peak_memory_stats()
            before = gpu_memory()
            info("loading the trainable engine (first time downloads ~2 GB)...")
            t0 = time.perf_counter()
            vagent = laya.load(vegaml=True, device=device)
            res.passed("Trainable engine loads", f"{time.perf_counter() - t0:.1f}s on {device}")

            need = laya.VegaAgent.min_rows(DOMAIN_QUESTION)
            info(f"it needs at least {need} examples for {len(DOMAIN_QUESTION['domain']['criteria'])} areas; we have {len(fit_rows)}")
            info("untrained first:")
            evaluate(vagent, held_rows, "  before teaching", res, "vega_before")

            t0 = time.perf_counter()
            report = vagent.fit([{"state": r["state"], "gold": {"domain": r["domain"]}} for r in fit_rows],
                                questions=DOMAIN_QUESTION)
            fit_s = time.perf_counter() - t0
            serving = report.get("serving")
            res.passed("Teaching works", f"{fit_s:.1f}s, using the new knowledge for: {serving}")
            res.numbers["fit_report_keys"] = sorted(report.keys())

            after_stats = evaluate(vagent, held_rows, "  after teaching", res, "vega_after")
            before_acc = res.numbers["vega_before"]["accuracy"]
            msg = f"{before_acc:.0%} -> {after_stats['accuracy']:.0%}"
            if after_stats["accuracy"] > before_acc:
                res.passed("Teaching made it better", msg)
            else:
                res.noted("Teaching didn't help on this small set", msg)
            show_misses(after_stats)

            after = gpu_memory()
            if cuda:
                peak = torch.cuda.max_memory_allocated() / 1024 / 1024
                res.numbers["vega_after"]["torch_peak_mb"] = round(peak)
                info(f"graphics memory peak (PyTorch): {gb(peak)}")
            if before and after:
                res.numbers["vega_after"]["gpu_used_delta_mb"] = after["used_mb"] - before["used_mb"]
            vagent.save_calibration(str(RESULTS_DIR / "laya_taught"))
            info("saved what it learned to results/laya_taught/")
        except Exception as e:
            res.failed("Teaching test", f"{type(e).__name__}: {e}"[:400])
    else:
        info("")
        info("Tip: run 'python check_laya.py --train' to also test teaching Laya from examples.")

    res.save()


if __name__ == "__main__":
    main()
