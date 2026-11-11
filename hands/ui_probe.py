"""Read what is on screen in any app, without screenshots: the buttons, boxes, tabs and links that
Windows reports for a window ("UI Automation"), each with its name, type and position.

This is Otto's eyes for any-app control. It only reads; acting on a control lives in hands/app_control.py.
The design (one bounded list of interactive, on-screen controls; find by name; smallest control under a
point) follows Nus Companion's Windows probe (companion/src/win/probe.ps1, MIT licence), rewritten in
Python; the name-scoring rule is ported from it. See THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

# Windows' numeric codes for the kinds of control a person can act on.
INTERACTIVE = {50000: 'Button', 50011: 'MenuItem', 50019: 'TabItem', 50005: 'Hyperlink', 50004: 'Edit',
               50003: 'ComboBox', 50002: 'CheckBox', 50013: 'RadioButton', 50007: 'ListItem',
               50024: 'TreeItem', 50015: 'Slider', 50031: 'SplitButton', 50016: 'Spinner', 50030: 'Document'}
TEXT_TYPES = {'Edit', 'Document'}        # where typing can go
MAX_CONTROLS = 150                       # small lists keep a model accurate and the prompt short


def list_controls(hwnd: int, limit: int = MAX_CONTROLS) -> list[dict]:
    """The interactive, on-screen controls of one window, in reading order, each as a plain dict:
    id, name, type, automation_id, rect (left, top, right, bottom), password, enabled, focused, read_only, checked.
    'element' holds the live Windows handle for acting on it and must never be sent to a model."""
    from pywinauto.uia_defines import IUIA

    uia = IUIA()
    ids = uia.UIA_dll
    types = None
    for code in INTERACTIVE:
        one = uia.iuia.CreatePropertyCondition(ids.UIA_ControlTypePropertyId, code)
        types = one if types is None else uia.iuia.CreateOrCondition(types, one)
    visible = uia.iuia.CreatePropertyCondition(ids.UIA_IsOffscreenPropertyId, False)
    wanted = uia.iuia.CreateAndCondition(types, visible)
    cache = uia.iuia.CreateCacheRequest()
    for prop in (ids.UIA_NamePropertyId, ids.UIA_ControlTypePropertyId, ids.UIA_AutomationIdPropertyId,
                 ids.UIA_BoundingRectanglePropertyId, ids.UIA_IsPasswordPropertyId, ids.UIA_IsEnabledPropertyId,
                 ids.UIA_HasKeyboardFocusPropertyId, ids.UIA_IsValuePatternAvailablePropertyId,
                 ids.UIA_ValueIsReadOnlyPropertyId, ids.UIA_IsTogglePatternAvailablePropertyId,
                 ids.UIA_ToggleToggleStatePropertyId):
        cache.AddProperty(prop)
    # One round trip to the app: Windows returns every match with the properties above already filled in.
    found = uia.iuia.ElementFromHandle(hwnd).FindAllBuildCache(ids.TreeScope_Descendants, wanted, cache)
    controls = []
    for index in range(found.Length):
        if len(controls) >= limit:
            break
        element = found.GetElement(index)
        try:
            box = element.CachedBoundingRectangle
            if box.right - box.left <= 0 or box.bottom - box.top <= 0:
                continue
            controls.append({
                'id': len(controls) + 1,
                'name': (element.CachedName or '').strip(),
                'type': INTERACTIVE.get(element.CachedControlType, ''),
                'automation_id': element.CachedAutomationId or '',
                'rect': (box.left, box.top, box.right, box.bottom),
                'password': bool(element.CachedIsPassword),
                'enabled': bool(element.CachedIsEnabled),
                'focused': bool(element.CachedHasKeyboardFocus),
                # A web page is also a "Document", but a read-only one: it is not somewhere to type.
                'read_only': bool(element.GetCachedPropertyValue(ids.UIA_IsValuePatternAvailablePropertyId)
                                  and element.GetCachedPropertyValue(ids.UIA_ValueIsReadOnlyPropertyId)),
                # For tick boxes and switches: True = on, False = off, None = not a switch.
                'checked': (element.GetCachedPropertyValue(ids.UIA_ToggleToggleStatePropertyId) == 1
                            if element.GetCachedPropertyValue(ids.UIA_IsTogglePatternAvailablePropertyId) else None),
                'element': element,
            })
        except Exception:
            continue      # a control that vanished while we were reading
    return controls


def name_score(candidate: str, want: str) -> int:
    """How well a control's name matches the name asked for (100 exact ... 0 no match)."""
    c, w = (candidate or '').strip().casefold(), (want or '').strip().casefold()
    if not c or not w:
        return 0
    if c == w:
        return 100
    if c.startswith(w):
        return 80
    if w in c:
        return 60
    if c in w and len(c) >= 3:
        return 40
    return 0


def find_control(controls: list[dict], name: str, kind: str = '') -> tuple[dict | None, bool]:
    """The control whose name best matches, and whether that best match is the only one at its score.
    Callers must not act on an ambiguous match."""
    scored = []
    for control in controls:
        score = name_score(control['name'], name)
        if score and kind and control['type'] == kind:
            score += 15
        if score:
            scored.append((score, control))
    if not scored:
        return None, False
    best = max(score for score, _ in scored)
    top = [control for score, control in scored if score == best]
    return top[0], len(top) == 1


def control_at(controls: list[dict], x: int, y: int) -> dict | None:
    """The smallest listed control containing a screen point (a label inside a button is not the button)."""
    best, best_area = None, None
    for control in controls:
        left, top, right, bottom = control['rect']
        if left <= x < right and top <= y < bottom:
            area = (right - left) * (bottom - top)
            if best_area is None or area < best_area:
                best, best_area = control, area
    return best


def text_target(controls: list[dict]) -> tuple[dict | None, str]:
    """Where typed text should go in this window: the text box that has the keyboard, or the only one.
    Returns (control, '') or (None, reason) with reason one of: protected, none, unclear."""
    from core.sensitive import sensitive

    boxes = [c for c in controls if c['type'] in TEXT_TYPES and c['enabled'] and not c.get('read_only')]
    focused = [c for c in boxes if c['focused']]
    # Without keyboard focus, only a lone editor (a Document, as in Notepad or Word) is an obvious place to
    # type. A lone small box, such as a browser's address bar, is not: the user must click where they mean.
    editors = [c for c in boxes if c['type'] == 'Document']
    chosen = focused[0] if focused else (editors[0] if len(editors) == 1 else None)
    if chosen is None:
        return None, ('none' if not boxes else 'unclear')
    if sensitive(chosen):
        return None, 'protected'
    return chosen, ''


def read_text(control: dict, limit: int = 200_000) -> str | None:
    """The text currently in a text box, or None if the app does not let us read it."""
    from pywinauto.uia_defines import IUIA

    ids = IUIA().UIA_dll
    element = control['element']
    try:
        pattern = element.GetCurrentPattern(ids.UIA_TextPatternId)
        if pattern:
            return pattern.QueryInterface(ids.IUIAutomationTextPattern).DocumentRange.GetText(limit)
    except Exception:
        pass
    try:
        pattern = element.GetCurrentPattern(ids.UIA_ValuePatternId)
        if pattern:
            return pattern.QueryInterface(ids.IUIAutomationValuePattern).CurrentValue
    except Exception:
        pass
    return None


def _pattern(control: dict, pattern_id: str, interface: str):
    """One of the standard ways Windows lets a program operate a control, or None if this control lacks it."""
    from pywinauto.uia_defines import IUIA

    ids = IUIA().UIA_dll
    try:
        found = control['element'].GetCurrentPattern(getattr(ids, pattern_id))
        return found.QueryInterface(getattr(ids, interface)) if found else None
    except Exception:
        return None


def press(control: dict) -> bool:
    """Press a button, pick a tab or list item, or flip a switch, the way the app itself offers.
    No mouse pointer is moved, so nothing else on screen can be hit by mistake."""
    for pattern_id, interface, method in (
            ('UIA_InvokePatternId', 'IUIAutomationInvokePattern', 'Invoke'),
            ('UIA_SelectionItemPatternId', 'IUIAutomationSelectionItemPattern', 'Select'),
            ('UIA_TogglePatternId', 'IUIAutomationTogglePattern', 'Toggle')):
        pattern = _pattern(control, pattern_id, interface)
        if pattern is not None:
            getattr(pattern, method)()
            return True
    return False


def flip(control: dict) -> bool:
    """Flip a tick box or switch once."""
    pattern = _pattern(control, 'UIA_TogglePatternId', 'IUIAutomationTogglePattern')
    if pattern is None:
        return False
    pattern.Toggle()
    return True


def set_value(control: dict, text: str) -> bool:
    """Put text straight into a box (no keystrokes)."""
    pattern = _pattern(control, 'UIA_ValuePatternId', 'IUIAutomationValuePattern')
    if pattern is None or pattern.CurrentIsReadOnly:
        return False
    pattern.SetValue(text)
    return True


def fingerprint(controls: list[dict]) -> frozenset:
    """A summary of what a window shows, to tell whether a click changed anything."""
    return frozenset((c['type'], c['name'], c.get('checked'), c['enabled']) for c in controls)
