"""Observe the focused edit, with bounded waiting and distinct failure diagnostics."""
import time
from core.action_runtime import check
from core import log
from hands.registry import Result


def field_state(hwnd):
    from hands import win
    if win.foreground() != hwnd:
        return 'focus_lost', {}
    try:
        from pywinauto.uia_defines import IUIA
        field = IUIA().get_focused_element()
        kind = field.CurrentControlType
        protected = bool(field.CurrentIsPassword)
        named = any(label in (field.CurrentName or '').casefold() for label in ('search', 'what do you want to play'))
        observed = {'control_type': kind, 'protected': protected, 'search_label': named}
        if protected:
            return 'protected_field', observed
        if kind not in {50003, 50004}:  # Spotify exposes search as ComboBox, not Edit.
            return 'not_editable', observed
        return ('ready' if named else 'search_label_missing'), observed
    except Exception as error:
        return 'uia_unavailable', {'error_class': type(error).__name__}


def search(hwnd, query):
    from hands import win
    # Target the observed semantic control directly; Ctrl+L can select CEF's hidden address field.
    try:
        from pywinauto import Application
        dialog = Application(backend='uia').connect(handle=hwnd).window(handle=hwnd)
        controls = [c for c in dialog.descendants(control_type='ComboBox')
                    if c.is_visible() and c.is_enabled()
                    and 'what do you want to play' in (getattr(c.element_info, 'name', '') or c.window_text()).casefold()
                    and not c.element_info.element.CurrentIsPassword]
        if len(controls) == 1:
            control = controls[0]
            check()
            if win.foreground() != hwnd or control.iface_value.CurrentIsReadOnly:
                return Result(False, 'Spotify search lost focus.', {'error_code': 'focus_lost'})
            control.iface_value.SetValue(query)
            # Spotify reports the new text a moment after it is set (measured 80-400 ms on the user's PC),
            # so keep re-reading for up to ~2 seconds before deciding it did not take.
            for _ in range(40):
                if control.iface_value.CurrentValue == query:
                    break
                check()
                if win.foreground() != hwnd:
                    return Result(False, 'Spotify search lost focus.', {'error_code': 'focus_lost'})
                time.sleep(0.05)
            else:
                return Result(False, 'Spotify search value did not match.', {'error_code': 'value_mismatch'})
            check()
            control.set_focus()
            if control.has_keyboard_focus() and win.foreground() == hwnd:
                check()
                win.hotkey('enter')
            return Result(True, f'Searched Spotify for {query}.')
    except Exception as error:
        from core.action_runtime import ActionInterrupted
        if isinstance(error, ActionInterrupted):
            raise
        log.write({'type': 'spotify_combo_search', 'error_class': type(error).__name__})
    check()
    win.hotkey('ctrl+l')
    end = time.monotonic() + 2
    reason, observed = 'uia_unavailable', {}
    for _ in range(20):
        check()
        reason, observed = field_state(hwnd)
        if reason == 'ready' or reason in {'focus_lost', 'protected_field'}:
            break
        if time.monotonic() >= end:
            break
        time.sleep(0.1)
    def failure():
        log.write({'type': 'spotify_search_guard', 'reason': reason, 'observed': observed})
        return Result(False, f'Spotify search was not verified ({reason}); I stopped input.', {'error_code': reason})
    if reason != 'ready':
        if reason not in {'focus_lost', 'protected_field'}:
            from core.recovery import recover
            if recover(hwnd, 'focus_spotify_search'):
                reason, observed = field_state(hwnd)
        if reason != 'ready':
            return failure()
    for operation in (lambda: win.hotkey('ctrl+a'), lambda: win.type_text(query), lambda: win.hotkey('enter')):
        check()
        reason, observed = field_state(hwnd)
        if reason != 'ready':
            return failure()
        operation()
    return Result(True, f'Searched Spotify for {query}.')
