"""Live Whisper test: keeps listening and writes down everything you say, until you press Ctrl+C.

How it works: it listens to your microphone, notices when you start and stop talking,
then transcribes each sentence and shows how long that took. A level bar shows what the
microphone hears while you're quiet, so you can tell whether the right mic is being used.

Run:  python check_live.py
      python check_live.py --list-devices          (show your microphones)
      python check_live.py --device 3              (use microphone number 3 from that list)
      python check_live.py --model small --device-type cpu   (try the processor instead)

Everything you say is saved to results/live_transcript.txt (useful later for teaching Otto).
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
from collections import deque
from datetime import datetime

import numpy as np

from otto_check.common import RESULTS_DIR, add_nvidia_dll_dirs, info, title

RATE = 16000          # Whisper wants 16 kHz mono
BLOCK_S = 0.03        # look at the microphone 30 ms at a time
PRE_ROLL_S = 0.4      # keep a bit of audio from just before you started talking
END_SILENCE_S = 0.8   # this much quiet means you've finished the sentence
MAX_UTTER_S = 20      # cut very long speech into pieces
MIN_UTTER_S = 0.35    # ignore tiny clicks and bumps


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def resample(x: np.ndarray, src_rate: int) -> np.ndarray:
    if src_rate == RATE:
        return x
    n = int(len(x) * RATE / src_rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def next_block(blocks: queue.Queue) -> np.ndarray:
    # A timeout lets Ctrl+C work on Windows (a plain get() would ignore it)
    while True:
        try:
            return blocks.get(timeout=0.25)
        except queue.Empty:
            continue


def meter(level: float, threshold: float, width: int = 30) -> str:
    filled = min(width, int(level / max(threshold * 2, 1e-6) * width))
    mark = width // 2
    bar = "".join("#" if i < filled else ("|" if i == mark else "-") for i in range(width))
    return f"\r  mic [{bar}]  (talk past the | to be heard)   "


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    ap.add_argument("--device", type=int, help="microphone number from --list-devices")
    ap.add_argument("--model", default="large-v3-turbo", help="Whisper model (default large-v3-turbo)")
    ap.add_argument("--device-type", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--precision", help="default: int8_float16 on the GPU, int8 on the processor")
    ap.add_argument("--threshold", type=float, help="loudness that counts as talking (default: measured)")
    ap.add_argument("--no-hotword", action="store_true", help="don't nudge Whisper towards hearing 'Otto'")
    args = ap.parse_args()

    import sounddevice as sd

    if args.list_devices:
        title("Microphones")
        default_in = sd.default.device[0]
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                star = "  <- Windows default" if i == default_in else ""
                api = sd.query_hostapis(d["hostapi"])["name"]
                print(f"  {i:3}  {d['name'][:50]:50}  ({api}){star}")
        return

    # --- Load Whisper ------------------------------------------------------------------------
    title("Loading Whisper")
    add_nvidia_dll_dirs()
    from faster_whisper import WhisperModel

    precision = args.precision or ("int8_float16" if args.device_type == "cuda" else "int8")
    t0 = time.perf_counter()
    model = WhisperModel(args.model, device=args.device_type, compute_type=precision)
    info(f"{args.model} on {'GPU' if args.device_type == 'cuda' else 'processor'} ({precision}), "
         f"loaded in {time.perf_counter() - t0:.1f}s")
    model.transcribe(np.zeros(RATE, dtype=np.float32), language="en")  # warm-up

    # --- Open the microphone -----------------------------------------------------------------
    dev = args.device if args.device is not None else sd.default.device[0]
    dev_info = sd.query_devices(dev)
    blocks: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        blocks.put(indata[:, 0].copy())

    src_rate = RATE
    try:
        stream = sd.InputStream(device=dev, channels=1, samplerate=RATE, dtype="float32",
                                blocksize=int(RATE * BLOCK_S), callback=callback)
    except Exception:
        # Some microphones refuse 16 kHz: record at their own rate and convert
        src_rate = int(dev_info["default_samplerate"])
        stream = sd.InputStream(device=dev, channels=1, samplerate=src_rate, dtype="float32",
                                blocksize=int(src_rate * BLOCK_S), callback=callback)
    info(f"microphone: {dev_info['name']} ({src_rate} Hz)")

    RESULTS_DIR.mkdir(exist_ok=True)
    log_path = RESULTS_DIR / "live_transcript.txt"
    log = open(log_path, "a", encoding="utf-8")
    log.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M} | {args.model} {args.device_type} {precision} ===\n")

    with stream:
        # --- Measure the room's background noise ---------------------------------------------
        title("Measuring background noise: stay quiet for 2 seconds")
        noise = []
        end = time.time() + 2
        while time.time() < end:
            noise.append(rms(resample(next_block(blocks), src_rate)))
        floor = float(np.median(noise))
        threshold = args.threshold or max(floor * 3.5, 0.006)
        info(f"background {floor:.4f}, talking threshold {threshold:.4f}")
        if floor < 0.0005:
            info("very quiet: if nothing gets picked up, the mic may be muted or the wrong one "
                 "(try --list-devices)")

        title("Listening. Talk normally; press Ctrl+C to stop")
        hotwords = None if args.no_hotword else "Otto"
        pre_roll: deque = deque(maxlen=int(PRE_ROLL_S / BLOCK_S))
        speech: list[np.ndarray] = []
        quiet_for = 0.0
        last_meter = 0.0
        times: list[float] = []

        try:
            while True:
                block = resample(next_block(blocks), src_rate)
                level = rms(block)

                if not speech:
                    if level >= threshold:
                        speech = list(pre_roll) + [block]
                        quiet_for = 0.0
                        sys.stdout.write("\r  ...hearing you" + " " * 50)
                        sys.stdout.flush()
                    else:
                        pre_roll.append(block)
                        if time.time() - last_meter > 0.1:
                            sys.stdout.write(meter(level, threshold))
                            sys.stdout.flush()
                            last_meter = time.time()
                    continue

                speech.append(block)
                quiet_for = quiet_for + BLOCK_S if level < threshold else 0.0
                length = len(speech) * BLOCK_S
                if quiet_for < END_SILENCE_S and length < MAX_UTTER_S:
                    continue

                # You've stopped talking (or talked for a long time): transcribe it
                audio = np.concatenate(speech)
                speech, pre_roll = [], deque(maxlen=pre_roll.maxlen)
                if length < MIN_UTTER_S:
                    continue
                t0 = time.perf_counter()
                segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                               condition_on_previous_text=False, hotwords=hotwords)
                text = " ".join(s.text.strip() for s in segments).strip()
                took = time.perf_counter() - t0
                if not text:
                    sys.stdout.write("\r" + " " * 70 + "\r")
                    continue
                times.append(took)
                stamp = datetime.now().strftime("%H:%M:%S")
                sys.stdout.write("\r" + " " * 70 + "\r")
                print(f"  [{stamp}] ({length:4.1f}s of speech, written in {took:.2f}s)  {text}")
                log.write(f"[{stamp}] {text}\n")
                log.flush()
        except KeyboardInterrupt:
            pass

    log.close()
    print()
    title("Done")
    if times:
        info(f"{len(times)} sentences, average {np.mean(times):.2f}s to write each, slowest {max(times):.2f}s")
    else:
        info("Nothing was transcribed. Try: python check_live.py --list-devices, then --device N")
    info(f"saved to {log_path.relative_to(RESULTS_DIR.parent)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
