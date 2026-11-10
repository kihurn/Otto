"""Phase 0, check 1: can Otto talk to every brain through C0RE?

For each model it tests:
  1. a plain reply          (does it answer at all, and how fast)
  2. pulling out details    (returns clean JSON, e.g. app=spotify, query=lofi)
  3. reading an image       (needed for "what's on my screen")

Run:  python check_c0re.py
      python check_c0re.py --models gemma4:31b-cloud,qwen3-vl:8b-instruct
"""

from __future__ import annotations

import argparse
import base64
import io
import json

from otto_check.common import (
    CLOUD_MODELS, LOCAL_MODELS, C0REError, Results, c0re_request, c0re_url, chat,
    fix_for, info, require_key, title,
)


def make_test_image() -> str:
    """A small PNG that says 'OTTO 42', returned as base64."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (520, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", 110)
    except OSError:
        font = ImageFont.load_default(size=110)
    draw.text((30, 30), "OTTO 42", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_model(model: str, image_b64: str, res: Results, do_vision: bool) -> dict:
    row = {"model": model, "answers": False, "first_s": None, "warm_s": None,
           "json": False, "vision": None}
    title(model)

    # 1. Plain reply (twice: the first call may include loading time)
    try:
        reply, secs = chat(model, "Reply with exactly these words and nothing else: OTTO IS READY")
        row["first_s"] = round(secs, 2)
        if "otto is ready" in reply.lower():
            res.passed(f"{model} answers", f"{secs:.1f}s")
        else:
            res.noted(f"{model} answers, but not as asked", f"{secs:.1f}s, said: {reply[:80]!r}")
        row["answers"] = True
        _, secs2 = chat(model, "Reply with exactly: OK")
        row["warm_s"] = round(secs2, 2)
        info(f"second reply took {secs2:.1f}s")
    except C0REError as e:
        res.failed(f"{model} answers", f"{e.code}: {e.message[:160]}", fix_for(e))
        if e.retry_after:
            info(f"C0RE says retry after {e.retry_after}s")
        return row

    # 2. Pull details out as JSON
    try:
        prompt = ("Extract the app name and the search words from this request.\n"
                  "Request: \"open spotify and search lofi beats\"\n"
                  "Reply with only JSON like {\"app\": \"...\", \"query\": \"...\"}")
        reply, secs = chat(model, prompt, fmt="json")
        # Some cloud models wrap JSON in ```json ... ``` fences; Otto will strip those too
        cleaned = reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        app, query = str(data.get("app", "")).lower(), str(data.get("query", "")).lower()
        if "spotify" in app and "lofi" in query.replace("-", "").replace(" ", ""):
            row["json"] = True
            res.passed(f"{model} pulls out details", f"{data} in {secs:.1f}s")
        else:
            res.noted(f"{model} pulls out details", f"wrong values: {data}")
    except json.JSONDecodeError:
        res.noted(f"{model} pulls out details", f"reply wasn't clean JSON: {reply[:100]!r}")
    except C0REError as e:
        res.noted(f"{model} pulls out details", f"{e.code}: {e.message[:160]}")

    # 3. Read an image
    if do_vision:
        try:
            reply, secs = chat(model, "What word and number are written in this image? "
                                      "Reply with just the word and the number.",
                               images_b64=[image_b64])
            low = reply.lower()
            row["vision"] = "otto" in low and "42" in low
            if row["vision"]:
                res.passed(f"{model} reads images", f"{secs:.1f}s")
            else:
                res.noted(f"{model} can't read images (or misread)", f"said: {reply[:80]!r}")
        except C0REError as e:
            row["vision"] = False
            res.noted(f"{model} can't read images", f"{e.code}: {e.message[:120]}")
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", help="comma-separated list (default: all cloud + local models)")
    ap.add_argument("--skip-vision", action="store_true", help="don't run the image test")
    args = ap.parse_args()

    res = Results("c0re")
    title(f"C0RE at {c0re_url()}")
    if not require_key(res):
        res.save()
        return

    # Which models does C0RE list for this key?
    try:
        tags = c0re_request("/api/tags", timeout=20)
        names = sorted(m.get("name", "?") for m in tags.get("models", []))
        res.passed("C0RE reachable and key accepted", f"{len(names)} models listed")
        for n in names:
            info(n)
        info("(cloud models often don't appear in this list; that's fine, we test them by name)")
    except C0REError as e:
        res.failed("C0RE reachable and key accepted", f"{e.code}: {e.message[:160]}", fix_for(e))
        res.save()
        return

    models = args.models.split(",") if args.models else CLOUD_MODELS + LOCAL_MODELS
    image_b64 = make_test_image()
    rows = [test_model(m.strip(), image_b64, res, not args.skip_vision) for m in models if m.strip()]
    res.numbers["models"] = rows

    # Summary table + suggested chains
    title("Summary")
    print(f"  {'model':32} {'works':6} {'1st s':>7} {'warm s':>7} {'JSON':5} {'image':5}")
    for r in rows:
        v = {True: "yes", False: "no", None: "-"}[r["vision"]]
        print(f"  {r['model']:32} {('yes' if r['answers'] else 'NO'):6} "
              f"{r['first_s'] if r['first_s'] is not None else '-':>7} "
              f"{r['warm_s'] if r['warm_s'] is not None else '-':>7} "
              f"{('yes' if r['json'] else 'no'):5} {v:5}")

    text_chain = [r["model"] for r in rows if r["answers"] and r["json"]]
    vision_chain = [r["model"] for r in rows if r["vision"]]
    res.numbers["suggested_text_chain"] = text_chain
    res.numbers["suggested_vision_chain"] = vision_chain
    print()
    info("Suggested text chain:   " + (" -> ".join(text_chain) or "(none worked)"))
    info("Suggested screen chain: " + (" -> ".join(vision_chain) or "(none worked)"))
    res.save()


if __name__ == "__main__":
    main()
