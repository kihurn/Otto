"""Act inside any app using the controls Windows reports for it (see hands/ui_probe.py).

Every action here follows the same four steps: observe the window, pick one target by rules Otto's own
code can check, act, then look again to confirm. Nothing here is chosen by a model.
"""
from __future__ import annotations

import time
import re

from core.tasks import Evidence, Outcome, OutcomeStatus
from hands.registry import ASK, UNDOABLE, action

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
            from hands import indicator
            indicator.show(window['hwnd'])          # glow around the window Otto is operating
            return window, name, ''
        time.sleep(0.25)
    return None, name, f"I couldn't bring {name} to the front."


def _same(a: dict, b: dict) -> bool:
    return (a['type'], a['name'], a['automation_id']) == (b['type'], b['name'], b['automation_id'])


def whatsapp_box(who: str):
    """Locate the open recipient's composer using the desktop app's own accessible label."""
    from core.sensitive import sensitive
    from hands import ui_probe, win
    window = win.find_window("WhatsApp")
    if not window or window["exe"].casefold() not in {"whatsapp.exe", "whatsapp.root.exe"}:
        return None, None
    hwnd = window["hwnd"]
    if win.foreground() != hwnd and not win.focus(hwnd):
        return None, None
    if win.foreground() != hwnd:
        return None, None
    pattern = r"(?:type a message to |message to |message [@#])(?:group )?" + re.escape(who)
    if who.casefold() in {"myself", "yourself"}:
        pattern = r"(?:message yourself|(?:type a )?message to yourself)"
    boxes = [c for c in ui_probe.list_controls(hwnd, limit=400)
             if c["type"] in ui_probe.TEXT_TYPES and c["enabled"] and not c.get("read_only")
             and not sensitive(c) and re.fullmatch(pattern, " ".join(c["name"].split()), re.I)]
    return hwnd, boxes[0] if len(boxes) == 1 else None


@action("draft_whatsapp", UNDOABLE, {"to": "open recipient", "text": "reply draft"},
        lambda to, text: f"draft a reply to {to}", for_brain=False)
def draft_whatsapp(to: str, text: str) -> Outcome:
    from core.action_runtime import check
    from hands import apps, ui_probe, win
    LAST_TYPED.clear()
    hwnd, box = whatsapp_box(to)
    if not box or not text.strip() or any(ord(c) < 32 for c in text):
        return Outcome(OutcomeStatus.NEEDS_INPUT, f"I couldn't verify a safe draft box for {to}.")
    element = box["element"]
    element.SetFocus()
    def ready():
        return (win.foreground() == hwnd and _same_box(element) and win.focused_is_password() is False
                and element.CurrentName == box["name"])
    check()
    for _ in range(5):
        if ready():
            break
        time.sleep(0.05)
    else:
        return Outcome(OutcomeStatus.NEEDS_INPUT, f"I couldn't focus {to}'s message box.")
    before = ui_probe.read_text(box)
    if before not in ("", text):
        reason = "couldn't read the existing draft" if before is None else "found an existing draft"
        return Outcome(OutcomeStatus.NEEDS_INPUT, f"I {reason} in {to}'s message box.")
    if before != text:
        check()
        if not ready() or ui_probe.read_text(box) != "":
            return Outcome(OutcomeStatus.NEEDS_INPUT, "The message box changed before typing.")
        if not ui_probe.set_value(box, text):
            if not ready():
                return Outcome(OutcomeStatus.NEEDS_INPUT, "The message box lost focus before typing.")
            written = apps.type_text(text)
            if not written.ok:
                return Outcome(OutcomeStatus.FAILED, written.say)
    for _ in range(8):
        check()
        if not ready():
            break
        if ui_probe.read_text(box) == text:
            LAST_TYPED.update(hwnd=hwnd, name="WhatsApp", element=element, text=text, composer=box["name"])
            return Outcome(OutcomeStatus.VERIFIED, f"The draft is in {to}'s message box.",
                           evidence=[Evidence("uia.text", target={"recipient": to}, observed={"exact": True})])
        time.sleep(0.15)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I couldn't verify the draft in {to}'s message box.",
                   side_effect_possible=True)


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
    return _type_into(window, name, text)


def _type_into(window: dict, name: str, text: str) -> Outcome:
    """Type into the window's one text box (the focused one if there are several), never a password box, and
    check that the text appeared."""
    from core.action_runtime import check
    from hands import ui_probe, win

    hwnd = window['hwnd']
    LAST_TYPED.clear()                    # a failed type must never leave an earlier text that send_typed could send
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
    from hands import indicator
    indicator.point(target['rect'])
    check()
    # Last look before any key is sent: still the same window in front, and not a password box.
    if win.foreground() != hwnd or win.focused_is_password() is not False:
        return Outcome(OutcomeStatus.UNCERTAIN, f'{name} lost focus, so I did not type.')
    win.type_text(text)
    LAST_TYPED.update(hwnd=hwnd, text=text, name=name, element=target['element'])
    for _ in range(8):
        time.sleep(0.2)
        if _appeared(before, ui_probe.read_text(target), text):
            return Outcome(OutcomeStatus.VERIFIED, f'Typed it in {name}.', {'app': name},
                           [Evidence('uia.text', target={'app': name, 'control': target['type']},
                                     expected={'typed_chars': len(text)}, observed={'appeared': True})],
                           side_effect_possible=True)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I typed it in {name}, but couldn't see the text appear.",
                   side_effect_possible=True)


# What dictation typed last and where: send_typed may only send exactly that, in that window.
LAST_TYPED: dict = {}


def _current_window():
    """The window you were using: the one in front, or the one before Otto's own (when you typed to Otto)."""
    from hands import win
    from senses import eyes
    hwnd = win.foreground()
    if hwnd in win.OTTO_WINDOWS:
        other = eyes.last_other_window()
        if not other or not win.focus(other['hwnd']):
            return None, ''
        hwnd = other['hwnd']
    info = win.window_info(hwnd)
    title = info.get('title', '')
    return info, (title.split(' - ')[-1].strip() or info.get('exe', '').removesuffix('.exe') or 'this window')


@action('type_here', UNDOABLE, {'text': "the user's own words to type"},
        lambda text: f'type "{text[:60]}" where you are', for_brain=False)
def type_here(text: str) -> Outcome:
    window, name = _current_window()
    if not window:
        return Outcome(OutcomeStatus.FAILED, "I can't tell which window you're in, so I didn't type anything.")
    return _type_into(window, name, text)


@action('send_typed', ASK, {'text': 'exactly what was typed', 'app': 'the app it was typed in',
                            'to': 'who it goes to, if known'},
        lambda text, app='', to='': f'send "{text}"' + (f' to {to}' if to else '') + (f' in {app}' if app else ''),
        for_brain=False)
def send_typed(text: str, app: str = '', to: str = '', *, binding: dict | None = None) -> Outcome:
    """Press Enter to send what was just typed, only when all of this holds (Codex checkpoint C3): the same window is
    in front, Windows names it a chat/message place (not a terminal, Run box or address bar), the focused box is
    the very box Otto typed into, and that box holds exactly the text. Otherwise it is left typed, not sent.
    "Sent" only once the box emptied AND the text shows in the chat."""
    from core.action_runtime import check
    from core.agent_safety import _is_command, _is_message, _search_box, focused_name
    from hands import ui_probe, win
    typed = LAST_TYPED if binding is None else binding
    if typed and win.foreground() in win.OTTO_WINDOWS:     # you typed your yes to Otto: back to the chat
        win.focus(typed['hwnd'])
        time.sleep(0.3)
    if not typed or typed.get('text') != text or win.foreground() != typed.get('hwnd'):
        return Outcome(OutcomeStatus.NEEDS_INPUT, "The window changed after typing, so I didn't send it.")
    hwnd, name, box = typed['hwnd'], typed.get('name') or app, typed.get('element')
    info = win.window_info(hwnd)
    place = {'exe': info.get('exe', ''), 'title': info.get('title', ''), 'focused': focused_name()}
    if typed.get("composer") and place["focused"] != typed["composer"]:
        return Outcome(OutcomeStatus.NEEDS_INPUT, "The conversation changed after drafting.")
    if (_is_command(place) or _search_box(place) or not _is_message(place)
            or (to and not typed.get("composer") and not chat_is_with(hwnd, to))):
        return Outcome(OutcomeStatus.NEEDS_INPUT, f"I typed it in {name}, but that doesn't look like a message box, "
                                                  "so I didn't send it.")
    held = ui_probe.read_text({'element': box}) if box is not None and _same_box(box) else None
    if held is None or ' '.join(held.split()) != ' '.join(text.split()):
        return Outcome(OutcomeStatus.NEEDS_INPUT, f"I typed it in {name}, but couldn't check the box holds exactly "
                                                  "that, so I didn't send it. Press Enter yourself if it looks right.")
    message = ' '.join(text.split())
    def outgoing_count():
        labels = (' '.join(line.split()) for line in chat_text(hwnd).splitlines())
        return sum(label in {f'Me: {message}', f'You: {message}'} for label in labels)

    previous_count = outgoing_count()
    check()
    current = ui_probe.read_text({'element': box})
    if (win.foreground() != hwnd or not _same_box(box) or current is None
            or ' '.join(current.split()) != message or focused_name() != place['focused']):
        return Outcome(OutcomeStatus.NEEDS_INPUT, "The window changed just before sending, so I didn't send it.")
    win.hotkey('enter')
    typed.clear()
    for _ in range(10):
        time.sleep(0.3)
        after = ui_probe.read_text({'element': box})
        if (after is not None and not after.strip() and win.foreground() == hwnd
                and focused_name() == place['focused'] and outgoing_count() > previous_count):
            return Outcome(OutcomeStatus.VERIFIED, f'Sent it in {name}.', {'app': name},
                           [Evidence('uia.text', target={'app': name}, expected={'in_chat': True},
                                     observed={'box_emptied': True, 'in_chat': True})], side_effect_possible=True)
    return Outcome(OutcomeStatus.UNCERTAIN, f"I pressed Enter in {name}, but couldn't confirm it was sent.",
                   side_effect_possible=True)


def _same_box(element) -> bool:
    """Is the focused box the very box Otto typed into (not another chat's box with the same draft)?"""
    try:
        from pywinauto.uia_defines import IUIA
        uia = IUIA()
        return bool(uia.iuia.CompareElements(element, uia.get_focused_element()))
    except Exception:
        return False


def chat_is_with(hwnd: int, who: str) -> bool:
    """Does this chat window name that person (its title, or the focused box: "Message @sarah", "Type a message
    to Sarah")?"""
    from core.agent_safety import focused_name
    from hands import win
    wanted = who.casefold().strip()
    shown = f"{win.window_info(hwnd).get('title', '')} {focused_name()}".casefold()
    return bool(wanted) and wanted in shown


def chat_text(hwnd: int, limit: int = 3000) -> str:
    """The latest text shown in a chat window, oldest first, for writing a reply (read-only; "" if unreadable).
    It is information for the draft, never instructions."""
    from core.reading import chat_messages
    from hands import win
    try:
        text, _ = chat_messages(hwnd, win.window_info(hwnd).get("title", ""))
    except Exception:
        return ''
    return text[-limit:]


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
        target, only = ui_probe.closest(usable, wanted)
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
    from hands import indicator
    indicator.point(target['rect'])
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


