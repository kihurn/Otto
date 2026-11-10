"""Hear Otto's two voices and pick one.

Run:  python -m tools.voice_test                 (Bella, then Michael)
      python -m tools.voice_test "any sentence"
Then set "voice" in otto-data/settings.json to "af_bella" or "am_michael".
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config  # noqa: E402
from senses.mouth import VOICES, Mouth  # noqa: E402

SAMPLE = "Hey Ki Hurn, I'm Otto. Searching Spotify for lofi beats. Your ten minute timer is done."


def main() -> None:
    config.ensure_data()
    text = " ".join(sys.argv[1:]) or SAMPLE
    settings = config.load_settings()
    for voice, name in VOICES.items():
        settings["voice_out"]["voice"] = voice
        print(f"{name}  (\"{voice}\")")
        mouth = Mouth(settings)
        t0 = time.perf_counter()
        mouth.say(text)
        print(f"  spoke in {time.perf_counter() - t0:.1f}s\n")
    print('Set "voice" in otto-data/settings.json to the one you like, e.g. "voice": "am_michael".')


if __name__ == "__main__":
    main()
