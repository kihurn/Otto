"""Phase 0, check 4: does everything fit in the 12 GB graphics card at the same time?

Loads, one after another:
  1. Laya (fast model) on the GPU
  2. Whisper on the GPU
  3. Qwen through C0RE (the local backup brain)
then shows how much graphics memory is used and checks each still runs at full speed.

Close games and heavy GPU apps first, so the numbers reflect normal use.

Run:  python check_memory.py
      python check_memory.py --whisper small      (try the smaller Whisper instead)
"""

from __future__ import annotations

import argparse
import time

from otto_check.common import (
    C0REError, Results, add_nvidia_dll_dirs, c0re_request, chat, fix_for, gb, gpu_memory, info,
    require_key, title,
)
from otto_check.intents import DOMAIN_QUESTION

QWEN = "qwen3-vl:8b-instruct"


def show(step: str, mem: dict | None, res: Results) -> None:
    if mem:
        info(f"{step:28} used {gb(mem['used_mb'])} of {gb(mem['total_mb'])}  (free {gb(mem['free_mb'])})")
        res.numbers.setdefault("steps", []).append({"step": step, **mem})


def time_laya(agent) -> float:
    t0 = time.perf_counter()
    agent.predict("open spotify and search lofi", DOMAIN_QUESTION)
    return (time.perf_counter() - t0) * 1000


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--whisper", default="large-v3-turbo", help="Whisper model (default large-v3-turbo)")
    ap.add_argument("--precision", default="int8_float16", help="Whisper precision on the GPU")
    args = ap.parse_args()
    res = Results("memory")

    title("Starting point")
    mem = gpu_memory()
    if not mem:
        res.failed("nvidia-smi available", "not found", "Update the NVIDIA driver; nvidia-smi comes with it.")
        res.save()
        return
    res.passed("Graphics card", f"{mem['name']}, driver {mem['driver']}")
    show("before loading anything", mem, res)
    if mem["used_mb"] > 3000:
        res.noted("Something is already using the GPU",
                  f"{gb(mem['used_mb'])} in use. Close games/heavy apps, or Ollama may already have a model loaded.")
    if not require_key(res):
        res.save()
        return

    # 1. Laya
    title("1. Laya")
    import torch
    import laya
    agent = laya.load("convaiinnovations/laya", device="cuda")
    for _ in range(3):
        time_laya(agent)
    laya_alone = min(time_laya(agent) for _ in range(5))
    show("+ Laya", gpu_memory(), res)
    info(f"Laya decision: {laya_alone:.0f} ms")

    # 2. Whisper
    title("2. Whisper")
    add_nvidia_dll_dirs()
    from faster_whisper import WhisperModel
    import numpy as np
    whisper = WhisperModel(args.whisper, device="cuda", compute_type=args.precision)
    silence = np.zeros(16000 * 3, dtype=np.float32)
    def time_whisper() -> float:
        t0 = time.perf_counter()
        list(whisper.transcribe(silence, language="en", beam_size=1)[0])
        return time.perf_counter() - t0
    time_whisper()
    whisper_alone = time_whisper()
    show(f"+ Whisper {args.whisper}", gpu_memory(), res)
    info(f"Whisper on 3s of audio: {whisper_alone:.2f}s")

    # 3. Qwen via C0RE
    title(f"3. {QWEN} through C0RE")
    try:
        chat(QWEN, "Reply with exactly: OK", timeout=300)  # loads the model
        _, qwen_s = chat(QWEN, "In one short sentence, what is a CRM?")
        show(f"+ {QWEN}", gpu_memory(), res)
        info(f"Qwen short answer: {qwen_s:.1f}s")
    except C0REError as e:
        res.failed("Qwen loads", f"{e.code}: {e.message[:200]}", fix_for(e))
        res.save()
        return

    # Is Ollama keeping all of Qwen on the GPU? (C0RE may not pass this through; that's fine)
    try:
        ps = c0re_request("/api/ps", timeout=20)
        for m in ps.get("models", []):
            if m.get("name", "").startswith(QWEN.split(":")[0]):
                size, vram = m.get("size", 0), m.get("size_vram", 0)
                share = vram / size if size else 0
                res.numbers["qwen_on_gpu_share"] = round(share, 3)
                if share >= 0.99:
                    res.passed("Qwen is fully on the GPU", f"{gb(vram / 1024 / 1024)}")
                else:
                    res.noted("Part of Qwen spilled to normal memory",
                              f"{share:.0%} on the GPU; it will be slower. Try --whisper small.")
    except C0REError:
        info("(C0RE doesn't share Ollama's /api/ps; skipping that detail)")

    # All together: does each still run at full speed?
    title("Everything loaded together")
    final = gpu_memory()
    laya_now = min(time_laya(agent) for _ in range(5))
    whisper_now = time_whisper()
    _, qwen_now = chat(QWEN, "In one short sentence, what is a CRM?")
    res.numbers["together"] = {"laya_ms": round(laya_now, 1), "whisper_s": round(whisper_now, 2),
                               "qwen_s": round(qwen_now, 1), "laya_alone_ms": round(laya_alone, 1),
                               "whisper_alone_s": round(whisper_alone, 2), "qwen_alone_s": round(qwen_s, 1),
                               "torch_peak_mb": round(torch.cuda.max_memory_allocated() / 1024 / 1024)}
    info(f"Laya {laya_now:.0f} ms (alone {laya_alone:.0f}), Whisper {whisper_now:.2f}s "
         f"(alone {whisper_alone:.2f}), Qwen {qwen_now:.1f}s (alone {qwen_s:.1f})")

    if final and final["free_mb"] >= 500:
        res.passed("Everything fits", f"{gb(final['used_mb'])} used, {gb(final['free_mb'])} free")
    elif final:
        res.failed("Everything fits", f"only {gb(final['free_mb'])} free",
                   "Run again with --whisper small, or Otto keeps Whisper on the processor.")
    if qwen_now > qwen_s * 2 + 1:
        res.noted("Qwen got much slower with everything loaded", "probably spilled into normal memory")

    res.save()


if __name__ == "__main__":
    main()
