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


CLICKABLE = {'Button', 'MenuItem', 'Hyperlink', 'TabItem', 'ListItem', 'CheckBox', 'RadioButton',
             'SplitButton', 'TreeItem'}


def _find(app: str, wanted: str, kinds: set[str], what: str):
    """Shared first half of every by-name action: bring the app forward, read its controls, and find exactly
    one control with that name. Returns (window, app name, controls, control, problem Outcome or None)."""
    from hands import ui_probe

    window, name, problem = front_window(app)
    if not window:
        return None, name, [], None, Outcome(OutcomeStatus.FAILED, problem)
    try:
        controls = ui_probe.list_controls(window['hwnd'], limit=400)
    except Exception:
        return window, name, [], None, Outcome(OutcomeStatus.FAILED, f"I couldn't read {name}'s window.")
    usable = [c for c in controls if c['type'] in kinds and c['enabled'] and c['name']]
    target, only = ui_probe.find_control(usable, wanted)
    if not target:
        return window, name, controls, None, Outcome(
            OutcomeStatus.NEEDS_INPUT, f'I can\'t see a {what} called "{wanted}" in {name}.')
    if not only:
        return window, name, controls, None, Outcome(
            OutcomeStatus.NEEDS_INPUT, f'I can see more than one "{wanted}" in {name}; tell me its exact name.')
    return window, name, controls, target, None


def _still_in_front(window: dict, name: str):
    from core.action_runtime import check
    from hands import win

    check()
    if win.foreground() != window['hwnd']:
        return Outcome(OutcomeStatus.UNCERTAIN, f'{name} lost focus, so I did nothing.')
    return None


def click_named(app: str, button: str) -> Outcome:
    """Press one named control and confirm that the window reacted."""
    from hands import ui_probe, win
    from hands.apps import RISKY_WORDS

    window, name, controls, target, problem = _find(app, button, CLICKABLE, 'button')
    if problem:
        return problem
    if RISKY_WORDS.search(target['name']) and not RISKY_WORDS.search(button):
        # The real button does something the request did not spell out (Send, Delete, Pay...). Asking for it
        # by its full name sends the request through the "ask first" check instead.
        return Outcome(OutcomeStatus.NEEDS_INPUT,
                       f'The closest button is "{target["name"]}". Say that full name if you want it pressed.')
    lost = _still_in_front(window, name)
    if lost:
        return lost
    before, title = ui_probe.fingerprint(controls), window.get('title', '')
    try:
        pressed = ui_probe.press(target)
    except Exception:
        pressed = False
    if not pressed:
        return Outcome(OutcomeStatus.UNCERTAIN, f'"{target["name"]}" in {name} did not respond.', side_effect_possible=True)
    for _ in range(8):
        time.sleep(0.25)
        try:
            moved = win.foreground() != window['hwnd'] or win.window_info(window['hwnd'])['title'] != title
            changed = moved or ui_probe.fingerprint(ui_probe.list_controls(window['hwnd'], limit=400)) != before
        except Exception:
            changed = True          # the window closed or was replaced: that is a reaction
        if changed:
            return Outcome(OutcomeStatus.VERIFIED, f'Clicked "{target["name"]}".', {'app': name},
                           [Evidence('uia.window_changed', target={'app': name, 'control': target['name']},
                                     expected={'changed': True}, observed={'changed': True})],
                           side_effect_possible=True)
    return Outcome(OutcomeStatus.UNCERTAIN, f'I pressed "{target["name"]}" in {name}, but nothing seemed to change.',
                   side_effect_possible=True)


@action('set_field', UNDOABLE, {'app': 'app name', 'field': "the box's name as shown", 'text': "the user's own words"},
        lambda app, field, text: f'put "{text[:40]}" in the {field} box in {app}', for_brain=False)
def set_field(app: str, field: str, text: str) -> Outcome:
    from core.sensitive import sensitive
    from hands import ui_probe

    window, name, _, target, problem = _find(app, field, {'Edit', 'ComboBox'}, 'box')
    if problem:
        return problem
    if sensitive(target):
        return Outcome(OutcomeStatus.NEEDS_INPUT, NO_TARGET['protected'])
    lost = _still_in_front(window, name)
    if lost:
        return lost
    try:
        done = not target.get('read_only') and ui_probe.set_value(target, text)
    except Exception:
        done = False
    if not done:
        return Outcome(OutcomeStatus.FAILED, f'The "{target["name"]}" box in {name} can\'t be filled in directly.')
    for _ in range(10):                      # some apps report the new text a moment late
        if ui_probe.read_text(target) == text:
            return Outcome(OutcomeStatus.VERIFIED, f'Set {target["name"]} to {text}.', {'app': name},
                           [Evidence('uia.value', target={'app': name, 'control': target['name']},
                                     expected={'matches': True}, observed={'matches': True})],
                           side_effect_possible=True)
        time.sleep(0.2)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I filled in {target['name']}, but it doesn't show what I entered.",
                   side_effect_possible=True)


@action('toggle', UNDOABLE, {'app': 'app name', 'name': "the switch or tick box's name", 'state': 'on or off'},
        lambda app, name, state: f'turn {state} "{name}" in {app}', for_brain=False)
def toggle(app: str, name: str, state: str) -> Outcome:
    from hands import ui_probe

    want = str(state).strip().lower() == 'on'
    window, shown, _, target, problem = _find(app, name, {'CheckBox', 'RadioButton', 'Button', 'MenuItem', 'ListItem'}, 'switch')
    if problem:
        return problem
    if target['checked'] is None:
        return Outcome(OutcomeStatus.NEEDS_INPUT, f'"{target["name"]}" in {shown} isn\'t an on/off switch.')
    word = 'on' if want else 'off'
    if target['checked'] is want:
        return Outcome(OutcomeStatus.VERIFIED, f'{target["name"]} is already {word}.', {'app': shown},
                       [Evidence('uia.toggle', expected={'on': want}, observed={'on': want})])
    lost = _still_in_front(window, shown)
    if lost:
        return lost
    try:
        flipped = ui_probe.flip(target)
    except Exception:
        flipped = False
    if not flipped:
        return Outcome(OutcomeStatus.UNCERTAIN, f'"{target["name"]}" in {shown} did not respond.', side_effect_possible=True)
    for _ in range(8):
        time.sleep(0.25)
        try:
            now, only = ui_probe.find_control(
                [c for c in ui_probe.list_controls(window['hwnd'], limit=400) if c['checked'] is not None], target['name'])
        except Exception:
            now, only = None, False
        if now and only and now['checked'] is want:
            return Outcome(OutcomeStatus.VERIFIED, f'Turned {word} {target["name"]}.', {'app': shown},
                           [Evidence('uia.toggle', expected={'on': want}, observed={'on': want})],
                           side_effect_possible=True)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I flipped {target['name']}, but it doesn't show as {word}.",
                   side_effect_possible=True)
