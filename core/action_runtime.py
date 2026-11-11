"""Code-owned task guards, including inside multi-effect named actions."""
from contextvars import ContextVar
import time

current = ContextVar('otto_action_runtime', default=None)


class ActionInterrupted(Exception):
    pass


def check():
    state = current.get()
    if state:
        task, revision, deadline = state
        if task.cancel.is_set() or task.revision != revision or time.monotonic() >= deadline:
            raise ActionInterrupted('Task cancelled, changed or expired')
