"""Volume pronouns refer to one recently observed endpoint, not arbitrary model history."""
from dataclasses import dataclass
import re
import time


def is_followup(text):
    return bool(re.fullmatch(r'(?:what is it (?:now|at)|how loud is it|(?:increase|decrease|raise|lower|turn) it .+)[.!?]*', text, re.I))


@dataclass
class VolumeContext:
    endpoint: str | None = None
    updated: float = 0

    def clear(self):
        self.endpoint = None

    def bind(self, endpoint):
        self.endpoint = endpoint
        self.updated = time.monotonic()

    def resolve(self, text, endpoint):
        if not self.endpoint or endpoint != self.endpoint or time.monotonic() - self.updated >= 120:
            self.clear()
            return None
        if re.match(r'what|how', text, re.I):
            return 'What is the volume now?'
        return re.sub(r'\bit\b', 'the volume', text, flags=re.I)
