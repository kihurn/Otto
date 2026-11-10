"""Phase 0, check 3: speech-to-text with faster-whisper, on the GPU and on the processor.

It makes a short test recording with Windows' built-in voice (so you don't have to talk),
then transcribes it with a few Whisper sizes and settings, measuring speed, accuracy
and graphics memory for each.

Run:  python check_whisper.py
      python check_whisper.py --mic     (also records 5 seconds of YOUR voice at the end)
"""

from __future__ import annotations

import argparse
import gc
import subprocess
import time
import wave

from otto_check.common import RESULTS_DIR, Results, add_nvidia_dll_dirs, gb, gpu_memory, info, title

PHRASE = "Otto, open Spotify and search for lo-fi beats, then set a timer for ten minutes."
KEYWORDS = [("otto",), ("spotify",), ("search",), ("lo-fi", "lofi", "low-fi", "lo fi", "low fi"),
            ("timer",), ("ten", "10")]

# (model, device, precision). int8_float16 = compressed weights, fast maths on the GPU.
CONFIGS = [
    ("small", "cuda", "float16"),
    ("large-v3-turbo", "cuda", "int8_float16"),
    ("large-v3-turbo", "cuda", "float16"),
    ("small", "cpu", "int8"),
    ("large-v3-turbo", "cpu", "int8"),
]


def make_clip(path) -> float:
    """Speak PHRASE into a WAV file using Windows' built-in voice. Returns clip length in seconds."""
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak('{PHRASE}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=60)
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def score(text: str) -> tuple[int, int]:
    low = text.lower()
    hits = sum(1 for options in KEYWORDS if any(o in low for o in options))
    return hits, len(KEYWORDS)


def transcribe(model, audio) -> tuple[str, float]:
    t0 = time.perf_counter()
    segments, _ = model.transcribe(audio, language="en", beam_size=1, condition_on_previous_text=False)
    text = " ".join(s.text.strip() for s in segments)  # segments are produced lazily, here
    return text.strip(), time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mic", action="store_true", help="also record and transcribe 5 seconds of your voice")
    ap.add_argument("--quick", action="store_true", help="only test turbo on the GPU and small on the processor")
    args = ap.parse_args()
    res = Results("whisper")

    title("Setup")
    dirs = add_nvidia_dll_dirs()
    if dirs:
        res.passed("NVIDIA libraries found", f"{len(dirs)} folders")
    else:
        res.noted("NVIDIA libraries not found in this Python", "GPU tests will probably fail; see README step 4")
    try:
        import ctranslate2
        from faster_whisper import WhisperModel
    except ImportError as e:
        res.failed("faster-whisper installed", str(e), "Run README step 4 again.")
        res.save()
        return
    gpus = ctranslate2.get_cuda_device_count()
    res.passed("faster-whisper installed", f"CTranslate2 {ctranslate2.__version__}, sees {gpus} GPU(s)")

    RESULTS_DIR.mkdir(exist_ok=True)
    clip = RESULTS_DIR / "test_clip.wav"
    try:
        secs = make_clip(clip)
        res.passed("Test recording made", f"{secs:.1f}s: \"{PHRASE}\"")
    except Exception as e:
        res.failed("Test recording made", str(e)[:200], "This uses Windows' voice; run it on the PC.")
        res.save()
        return

    configs = CONFIGS
    if args.quick:
        configs = [("large-v3-turbo", "cuda", "int8_float16"), ("small", "cpu", "int8")]

    rows = []
    for name, device, ctype in configs:
        label = f"{name} on {'GPU' if device == 'cuda' else 'processor'} ({ctype})"
        title(label)
        if device == "cuda" and gpus == 0:
            res.noted(label, "skipped: no GPU visible to CTranslate2")
            continue
        model = None
        try:
            before = gpu_memory()
            t0 = time.perf_counter()
            info("loading (first time downloads the model)...")
            model = WhisperModel(name, device=device, compute_type=ctype)
            load_s = time.perf_counter() - t0
            transcribe(model, str(clip))  # warm-up run
            text, run_s = transcribe(model, str(clip))
            after = gpu_memory()
            hits, total = score(text)
            vram = (after["used_mb"] - before["used_mb"]) if (before and after and device == "cuda") else None
            row = {"model": name, "device": device, "precision": ctype, "load_s": round(load_s, 1),
                   "transcribe_s": round(run_s, 2), "keywords": f"{hits}/{total}",
                   "gpu_mb": vram, "text": text}
            rows.append(row)
            detail = f"{run_s:.2f}s for a {secs:.1f}s clip, {hits}/{total} key words"
            if vram is not None:
                detail += f", ~{gb(vram)} graphics memory"
            (res.passed if hits >= total - 1 else res.noted)(label, detail)
            info(f"heard: {text!r}")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"[:300]
            fix = None
            if "cublas" in msg.lower() or "cudnn" in msg.lower() or ".dll" in msg.lower():
                fix = "The CUDA 12 libraries are missing. Re-run the 'nvidia-...' pip line in README step 4."
            res.failed(label, msg, fix)
        finally:
            del model
            gc.collect()
            time.sleep(1)

    res.numbers["runs"] = rows

    # Recommendation: the fastest GPU setting that heard (nearly) everything
    good_gpu = [r for r in rows if r["device"] == "cuda" and int(r["keywords"].split("/")[0]) >= len(KEYWORDS) - 1]
    good_cpu = [r for r in rows if r["device"] == "cpu" and int(r["keywords"].split("/")[0]) >= len(KEYWORDS) - 1]
    title("Summary")
    if good_gpu:
        best = min(good_gpu, key=lambda r: r["transcribe_s"])
        res.numbers["recommended_gpu"] = best
        info(f"Best on GPU: {best['model']} ({best['precision']}), {best['transcribe_s']}s, ~{gb(best['gpu_mb'] or 0)}")
    if good_cpu:
        best = min(good_cpu, key=lambda r: r["transcribe_s"])
        res.numbers["recommended_cpu"] = best
        info(f"Best on processor: {best['model']} ({best['precision']}), {best['transcribe_s']}s")

    # Optional: your own voice
    if args.mic:
        title("Your voice")
        try:
            import sounddevice as sd

            model_cfg = res.numbers.get("recommended_gpu") or res.numbers.get("recommended_cpu")
            if not model_cfg:
                raise RuntimeError("no working Whisper setting to use")
            model = WhisperModel(model_cfg["model"], device=model_cfg["device"],
                                 compute_type=model_cfg["precision"])
            input("  Press Enter, then say: \"Otto, open Spotify and search for lo-fi beats\" (5 seconds)...")
            audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32")
            sd.wait()
            text, run_s = transcribe(model, audio[:, 0])
            hits, _ = score(text)
            res.numbers["mic"] = {"text": text, "transcribe_s": round(run_s, 2)}
            (res.passed if hits >= 3 else res.noted)("Your voice", f"{run_s:.2f}s, heard: {text!r}")
        except Exception as e:
            res.failed("Your voice", f"{type(e).__name__}: {e}"[:300],
                       "Check your microphone is the Windows default input device.")

    res.save()


if __name__ == "__main__":
    main()
