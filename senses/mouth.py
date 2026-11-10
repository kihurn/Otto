"""Mouth: Otto's spoken replies with Kokoro, sentence by sentence.

The next sentence is generated while the current one plays, so speech starts quickly.
While speaking, the ears are muted so Otto doesn't hear itself."""

from __future__ import annotations

import queue
import re
import threading
import time

import numpy as np

SAMPLE_RATE = 24000
VOICES = {"af_bella": "Bella (American female)", "am_michael": "Michael (American male)"}
VOICE_NAMES = {"bella": "af_bella", "michael": "am_michael"}


def speakable(text: str) -> str:
    t = re.sub(r"[*_`#>]+", "", text)
    t = re.sub(r"https?://\S+", "a link", t)
    t = re.sub(r"[A-Za-z]:\\\S+", "", t)                # file paths
    t = re.sub(r"\s*\n\s*\d+\.\s.*", "", t)             # numbered lists (shown on screen instead)
    return " ".join(t.split())


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if re.search(r"\w", p)]


class Mouth:
    def __init__(self, settings: dict, say=print):
        from kokoro import KPipeline

        v = settings.get("voice_out", {})
        self.voice = v.get("voice", "af_bella")
        self.speed = float(v.get("speed", 1.0))
        device = v.get("device", "cuda")
        try:
            import torch
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
        except ImportError:
            device = "cpu"
        t0 = time.perf_counter()
        lang = "b" if self.voice.startswith("b") else "a"
        self.pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device=device)
        self._audio("Ready.")  # warm-up
        say(f"  Voice ready ({VOICES.get(self.voice, self.voice)}, {device.upper()}) in {time.perf_counter() - t0:.0f}s")
        self.ears = None
        self._lock = threading.Lock()

    def set_voice(self, voice: str) -> str:
        voice = VOICE_NAMES.get(voice.lower(), voice)
        self.voice = voice
        return VOICES.get(voice, voice)

    def _audio(self, sentence: str) -> np.ndarray:
        chunks = [a.numpy() if hasattr(a, "numpy") else np.asarray(a)
                  for _, _, a in self.pipe(sentence, voice=self.voice, speed=self.speed)]
        return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)

    def say(self, text: str) -> None:
        import sounddevice as sd

        parts = sentences(speakable(text))
        if not parts:
            return
        with self._lock:
            if self.ears:
                self.ears.speaking.set()
            q: queue.Queue = queue.Queue(maxsize=2)

            def make():
                for p in parts:
                    try:
                        q.put(self._audio(p))
                    except Exception:
                        pass
                q.put(None)

            threading.Thread(target=make, daemon=True).start()
            try:
                while True:
                    audio = q.get()
                    if audio is None:
                        break
                    sd.play(audio, SAMPLE_RATE)
                    sd.wait()
            finally:
                if self.ears:
                    time.sleep(0.25)       # let the room go quiet
                    self.ears.flush()
                    self.ears.speaking.clear()
