"""Act inside any app using the controls Windows reports for it (see hands/ui_probe.py).

Every action here follows the same four steps: observe the window, pick one target by rules Otto's own
code can check, act, then look again to confirm. Nothing here is chosen by a model.
"""
from __future__ import annotations

import time

from core.tasks import Evidence, Outcome, OutcomeStatus
from hands.registry import UNDOABLE, action

NO_TARGET = {
    'none': "I can't see anywhere to type in {app}. Open a document or click the box first, then ask again.",
    'unclear': "I'm not sure where to type in {app}. Click the spot you want, then ask again.",
    'protected': "That looks like a password or private field, and I never type into those.",
}


def front_window(app: str):
    """Open the app if needed and bring it to the front. Returns (window, display name, problem)."""
    from core.action_runtime import check
    from hands import apps, win

    opened = apps.open_app(app)
    if not opened.ok:
        return None, app, opened.say
    name = opened.data.get('app', app)
    for _ in range(24):                       # up to ~6 seconds for a slow app to show its window
        check()
        window = win.find_window(name)
        if window and win.focus(window['hwnd']) and win.foreground() == window['hwnd']:
            return window, name, ''
        time.sleep(0.25)
    return None, name, f"I couldn't bring {name} to the front."


def _same(a: dict, b: dict) -> bool:
    return (a['type'], a['name'], a['automation_id']) == (b['type'], b['name'], b['automation_id'])


def _appeared(before: str | None, after: str | None, text: str) -> bool:
    """Did the typed text show up? Apps may auto-correct a letter or two, so allow for that."""
    if after is None:
        return False
    before = before or ''
    return after.count(text) > before.count(text) or len(after) - len(before) >= max(1, int(len(text) * 0.8))


@action('type_in_app', UNDOABLE, {'app': 'app name', 'text': "the user's own words to type"},
        lambda app, text: f'type "{text[:40]}" in {app}', for_brain=False)
def type_in_app(app: str, text: str) -> Outcome:
    from core.action_runtime import check
    from hands import ui_probe, win

    window, name, problem = front_window(app)
    if not window:
        return Outcome(OutcomeStatus.FAILED, problem)
    hwnd = window['hwnd']
    try:
        target, reason = ui_probe.text_target(ui_probe.list_controls(hwnd))
        if target and not target['focused']:
            target['element'].SetFocus()
            time.sleep(0.2)
            again, reason = ui_probe.text_target(ui_probe.list_controls(hwnd))
            target = again if again and again['focused'] and _same(again, target) else None
            reason = reason or 'unclear'
    except Exception:
        return Outcome(OutcomeStatus.FAILED, f"I couldn't read {name}'s window, so I didn't type anything.")
    if not target:
        return Outcome(OutcomeStatus.NEEDS_INPUT, NO_TARGET[reason].format(app=name))
    before = ui_probe.read_text(target)
    check()
    # Last look before any key is sent: still the same window in front, and not a password box.
    if win.foreground() != hwnd or win.focused_is_password():
        return Outcome(OutcomeStatus.UNCERTAIN, f'{name} lost focus, so I did not type.')
    win.type_text(text)
    for _ in range(8):
        time.sleep(0.2)
        if _appeared(before, ui_probe.read_text(target), text):
            return Outcome(OutcomeStatus.VERIFIED, f'Typed it in {name}.', {'app': name},
                           [Evidence('uia.text', target={'app': name, 'control': target['type']},
                                     expected={'typed_chars': len(text)}, observed={'appeared': True})],
                           side_effect_possible=True)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I typed it in {name}, but couldn't see the text appear.",
                   side_effect_possible=True)
