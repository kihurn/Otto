"""Ears: the microphone and faster-whisper.

Three ways to listen (settings: listen.mode, or  otto mode ...):
  wake    - always listening, but only acts on sentences starting with "Hey Otto" (default).
            After Otto replies, or while it's asking you something, you can answer without "Hey Otto".
  always  - every sentence is for Otto.
  push    - only hears you while you hold the push-to-talk key (F8 by default).
Plus a mute key (F9 by default) in every mode. While Otto is speaking, the mic is ignored so Otto
doesn't hear itself. Whisper also reports how sure it was, so Otto can ask "did you say ...?".
"""

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


def list_mics() -> list[tuple[int, str, str, bool]]:
    """(number, name, audio system, is_default) for every input device."""
    import sounddevice as sd

    default = sd.default.device[0]
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append((i, d["name"], sd.query_hostapis(d["hostapi"])["name"], i == default))
    return out


class Ears:
    def __init__(self, settings: dict, say=print):
        from senses.cuda_libs import add_nvidia_dll_dirs
        add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel

        w = settings.get("whisper", {})
        self.settings = settings
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
        self.mode = settings.get("listen", {}).get("mode", "wake")
        self.speaking = threading.Event()   # Otto is talking: ignore the mic
        self.muted = threading.Event()      # you pressed mute
        self.ptt = threading.Event()        # push-to-talk key is held
        self.blocks: queue.Queue = queue.Queue()
        self.stream = None
        self.src_rate = RATE
        self.threshold = 0.006

    # ---- microphone ------------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status):
        if self.speaking.is_set() or self.muted.is_set():
            return
        if self.mode == "push" and not self.ptt.is_set():
            return
        self.blocks.put(indata[:, 0].copy())

    def open(self, say=print, calibrate: bool = True) -> None:
        import sounddevice as sd

        dev = self.mic if self.mic is not None else sd.default.device[0]
        info = sd.query_devices(dev)
        self.src_rate = RATE
        try:
            self.stream = sd.InputStream(device=dev, channels=1, samplerate=RATE, dtype="float32",
                                         blocksize=int(RATE * BLOCK_S), callback=self._callback)
        except Exception:
            self.src_rate = int(info["default_samplerate"])
            self.stream = sd.InputStream(device=dev, channels=1, samplerate=self.src_rate, dtype="float32",
                                         blocksize=int(self.src_rate * BLOCK_S), callback=self._callback)
        self.stream.start()
        self.mic_name = info["name"]
        if calibrate and self.mode != "push":
            say(f"  Microphone: {info['name']}. Measuring background noise, stay quiet for 2 seconds...")
            levels, end = [], time.time() + 2
            while time.time() < end:
                b = self._next(0.3)
                if b is not None:
                    levels.append(_rms(b))
            floor = float(np.median(levels)) if levels else 0.002
            self.threshold = max(floor * 3.5, 0.006)
        else:
            say(f"  Microphone: {info['name']}.")

    def switch_mic(self, number: int | None, say=print) -> None:
        self.close()
        self.mic = number
        self.flush()
        self.open(say=say)

    def _next(self, timeout: float | None = None) -> np.ndarray | None:
        end = None if timeout is None else time.time() + timeout
        while True:
            try:
                return _resample(self.blocks.get(timeout=0.25), self.src_rate)
            except queue.Empty:
                if end is not None and time.time() > end:
                    return None
                if self.mode == "push" and self._ptt_released_with_audio:
                    return None

    def flush(self) -> None:
        while not self.blocks.empty():
            try:
                self.blocks.get_nowait()
            except queue.Empty:
                break

    _ptt_released_with_audio = False

    def push_down(self) -> None:
        self.flush()
        self.ptt.set()

    def push_up(self) -> None:
        threading.Timer(0.25, self._release).start()   # keep the last syllable

    def _release(self) -> None:
        self.ptt.clear()
        self._ptt_released_with_audio = True

    # ---- listening -------------------------------------------------------------------------
    def _transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                            condition_on_previous_text=False, hotwords=self.hotwords)
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            return "", 0.0
        total = sum(max(0.01, s.end - s.start) for s in segments)
        conf = sum(s.avg_logprob * max(0.01, s.end - s.start) for s in segments) / total
        return text, float(conf)

    def listen(self) -> tuple[str, float, float]:
        """Wait for one sentence. Returns (text, confidence, seconds of speech).
        Confidence is Whisper's average log-probability: near 0 = sure, below about -1 = unsure."""
        if self.mode == "push":
            return self._listen_push()
        pre: deque = deque(maxlen=int(PRE_ROLL_S / BLOCK_S))
        speech: list[np.ndarray] = []
        quiet = 0.0
        while True:
            block = self._next()
            if block is None:
                continue
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
            text, conf = self._transcribe(audio)
            if text:
                return text, conf, length

    def _listen_push(self) -> tuple[str, float, float]:
        while True:
            self._ptt_released_with_audio = False
            while not self.ptt.is_set():
                time.sleep(0.03)
            chunks = []
            while self.ptt.is_set() or not self.blocks.empty():
                b = self._next(0.3)
                if b is not None:
                    chunks.append(b)
                elif not self.ptt.is_set():
                    break
            if not chunks:
                continue
            audio = np.concatenate(chunks)
            length = len(audio) / RATE
            if length < MIN_UTTER_S:
                continue
            text, conf = self._transcribe(audio)
            if text:
                return text, conf, length

    def close(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
