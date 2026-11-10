"""Ears: listens to the microphone, notices when you start and stop talking, and writes it down
with faster-whisper. Also reports how sure Whisper was, so Otto can ask "Did you say ...?".
While Otto is speaking, the microphone is ignored so Otto doesn't hear itself."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque

import numpy as np

RATE = 16000
BLOCK_S = 0.03
PRE_ROLL_S = 0.4
MAX_UTTER_S = 20
MIN_UTTER_S = 0.35


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def _resample(x: np.ndarray, src: int) -> np.ndarray:
    if src == RATE:
        return x
    n = int(len(x) * RATE / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Ears:
    def __init__(self, settings: dict, say=print):
        from senses.cuda_libs import add_nvidia_dll_dirs
        add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel

        w = settings.get("whisper", {})
        self.hotwords = w.get("hotwords") or None
        self.end_silence = float(w.get("end_silence_s", 0.8))
        device, precision = w.get("device", "cuda"), w.get("precision", "int8_float16")
        t0 = time.perf_counter()
        try:
            self.model = WhisperModel(w.get("model", "large-v3-turbo"), device=device, compute_type=precision)
        except Exception as e:
            say(f"  ! Whisper couldn't use the GPU ({type(e).__name__}); using the processor.")
            self.model = WhisperModel("small", device="cpu", compute_type="int8")
        self.model.transcribe(np.zeros(RATE, dtype=np.float32), language="en")
        say(f"  Whisper ready in {time.perf_counter() - t0:.0f}s")
        self.mic = w.get("mic_device")
        self.muted = threading.Event()   # set while Otto is speaking
        self.blocks: queue.Queue = queue.Queue()
        self.stream = None
        self.src_rate = RATE
        self.threshold = 0.006

    # ---- microphone ------------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status):
        if not self.muted.is_set():
            self.blocks.put(indata[:, 0].copy())

    def open(self, say=print) -> None:
        import sounddevice as sd

        dev = self.mic if self.mic is not None else sd.default.device[0]
        info = sd.query_devices(dev)
        try:
            self.stream = sd.InputStream(device=dev, channels=1, samplerate=RATE, dtype="float32",
                                         blocksize=int(RATE * BLOCK_S), callback=self._callback)
        except Exception:
            self.src_rate = int(info["default_samplerate"])
            self.stream = sd.InputStream(device=dev, channels=1, samplerate=self.src_rate, dtype="float32",
                                         blocksize=int(self.src_rate * BLOCK_S), callback=self._callback)
        self.stream.start()
        say(f"  Microphone: {info['name']}. Measuring background noise, stay quiet for 2 seconds...")
        levels, end = [], time.time() + 2
        while time.time() < end:
            levels.append(_rms(self._next()))
        floor = float(np.median(levels)) if levels else 0.002
        self.threshold = max(floor * 3.5, 0.006)

    def _next(self) -> np.ndarray:
        while True:
            try:
                return _resample(self.blocks.get(timeout=0.25), self.src_rate)
            except queue.Empty:
                continue

    def flush(self) -> None:
        while not self.blocks.empty():
            try:
                self.blocks.get_nowait()
            except queue.Empty:
                break

    # ---- listening -------------------------------------------------------------------------
    def listen(self) -> tuple[str, float, float]:
        """Wait for one sentence. Returns (text, confidence, seconds of speech).
        Confidence is Whisper's average log-probability: near 0 = sure, below about -1 = unsure."""
        pre: deque = deque(maxlen=int(PRE_ROLL_S / BLOCK_S))
        speech: list[np.ndarray] = []
        quiet = 0.0
        while True:
            block = self._next()
            level = _rms(block)
            if not speech:
                if level >= self.threshold:
                    speech = list(pre) + [block]
                    quiet = 0.0
                else:
                    pre.append(block)
                continue
            speech.append(block)
            quiet = quiet + BLOCK_S if level < self.threshold else 0.0
            length = len(speech) * BLOCK_S
            if quiet < self.end_silence and length < MAX_UTTER_S:
                continue
            audio = np.concatenate(speech)
            speech, pre = [], deque(maxlen=pre.maxlen)
            if length < MIN_UTTER_S:
                continue
            segments, _ = self.model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                                condition_on_previous_text=False, hotwords=self.hotwords)
            segments = list(segments)
            text = " ".join(s.text.strip() for s in segments).strip()
            if not text:
                continue
            total = sum(max(0.01, s.end - s.start) for s in segments)
            conf = sum(s.avg_logprob * max(0.01, s.end - s.start) for s in segments) / total
            return text, float(conf), length

    def close(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
