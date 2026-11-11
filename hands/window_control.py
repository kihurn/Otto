"""Window-bound native provider for the approved Qwen controller."""
import base64
import io
import time
import uuid
from core.action_runtime import check
from core.tasks import Evidence
from hands.registry import action, UNDOABLE


@action('visual_task', UNDOABLE, {'app': 'Spotify or Chrome', 'goal': 'play or search',
                                'query': 'original query', 'artist': 'optional artist'},
        lambda app, goal, query, artist='': f'{goal} {query} visually in {app}', for_brain=False)
def visual_task(app, goal, query, artist=''):
    from core.computer_use import run
    return run(app, goal, query, artist)


# Chrome's own toolbar controls Otto may use. Only these exact control types count, and only when they are
# part of Chrome itself: anything inside a web page (a "Document") is page content, even if a page names a
# button "New tab" or "Address and search bar" (review finding R1).
CHROME_CONTROLS = {'address and search bar': {'Edit'}, 'new tab': {'Button'}}


def inside_web_page(control, limit: int = 40) -> bool:
    """True if the control is (inside) a web page rather than part of the browser's own window frame.
    Unknown/unreadable ancestry counts as 'inside a page', so we fail safe."""
    node = control
    for _ in range(limit):
        if node is None:
            return False
        try:
            if node.element_info.control_type == 'Document':
                return True
            node = node.parent()
        except Exception:
            return True
    return True


def chrome_control_ok(control) -> bool:
    try:
        name = (control.element_info.name or '').casefold()
        kind = control.element_info.control_type
    except Exception:
        return False
    return kind in CHROME_CONTROLS.get(name, set()) and not inside_web_page(control)


OUTSIDE_CAPABILITY = 'Visual target is outside the allowed capability'


class WindowProvider:
    def __init__(self, app, goal=None):
        from hands import apps, win
        opened = apps.open_app('Spotify' if app.casefold() == 'spotify' else 'Google Chrome')
        window = win.find_window('Spotify' if app.casefold() == 'spotify' else 'Google Chrome')
        if not opened.ok or not window or not win.focus(window['hwnd']):
            raise ValueError('Target unavailable')
        self.hwnd = window['hwnd']
        self.exe = 'spotify.exe' if app.casefold() == 'spotify' else 'chrome.exe'
        self.bound = self.identity()
        self.query_submitted = False
        self.goal = goal

    def song_controls(self, goal):
        from pywinauto import Application
        from hands.spotify_desktop import play_candidates
        dialog = Application(backend='uia').connect(handle=self.hwnd).window(handle=self.hwnd)
        controls = play_candidates(dialog, goal['query'], goal['artist'])
        return sorted(controls, key=lambda control: (control.rectangle().top, control.rectangle().left))

    def identity(self):
        from hands import win
        import psutil
        info = win.window_info(self.hwnd)
        if info['exe'].casefold() != self.exe or win.foreground() != self.hwnd:
            raise ValueError('Window ownership/focus mismatch')
        return (info['pid'], psutil.Process(info['pid']).create_time(), tuple(info['rect']))

    def pixels(self):
        from PIL import Image
        import mss
        target = self.identity()
        l, t, r, b = target[2]
        import win32gui
        for x in range(l+8, r-8, 40):
            for y in range(t+8, b-8, 40):
                if win32gui.GetAncestor(win32gui.WindowFromPoint((x,y)),2) != self.hwnd:
                    raise ValueError('Window is obscured; no screenshot was taken')
        with mss.mss() as source:
            raw = source.grab({'left': l, 'top': t, 'width': r-l, 'height': b-t})
            image = Image.frombytes('RGB', raw.size, raw.rgb)
        if self.identity() != target:
            raise ValueError('Capture changed')
        return target, image

    def observe(self):
        target, full = self.pixels()
        if target[:2] != self.bound[:2]:
            raise ValueError('Process replaced')
        image = full.copy()
        image.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=80)
        songs = self.song_controls(self.goal) if self.query_submitted and self.exe == 'spotify.exe' and self.goal else []
        song_target = (songs[0].element_info.name, tuple(songs[0].rectangle())) if songs else None
        return {'id': uuid.uuid4().hex, 'identity': target, 'time': time.monotonic(),
                'image': base64.b64encode(buffer.getvalue()).decode(), 'pixels': full,
                'query_submitted': self.query_submitted, 'song_target': song_target}

    def fresh(self, snapshot, point):
        from PIL import ImageChops, ImageStat
        target, image = self.pixels()
        if target != snapshot['identity'] or time.monotonic()-snapshot['time'] > 20:
            return False
        if point:
            x, y = int(point['x']*(image.width-1)), int(point['y']*(image.height-1))
            region = (max(0,x-32), max(0,y-24), min(image.width,x+33), min(image.height,y+25))
            diff = ImageChops.difference(image.crop(region), snapshot['pixels'].crop(region))
            return max(ImageStat.Stat(diff).mean) < 8
        return True

    def act(self, action_name, target, snapshot, goal):
        from hands import win
        from pywinauto import mouse
        import win32gui
        check()
        if self.identity() != snapshot['identity']:
            raise ValueError('Stale target')
        if action_name in {'click', 'scroll_down'}:
            l,t,r,b = snapshot['identity'][2]
            x,y = (l+int(target['x']*(r-l-1)), t+int(target['y']*(b-t-1))) if action_name == 'click' else ((l+r)//2,(t+b)//2)
            hit = win32gui.WindowFromPoint((x,y))
            if win32gui.GetAncestor(hit,2) != self.hwnd:
                raise ValueError('Target obscured')
            if action_name == 'click':
                from pywinauto import Desktop
                control = Desktop(backend='uia').from_point(x,y)
                label = (control.element_info.name or '').casefold()
                if goal['app'].casefold() == 'chrome':
                    eligible = chrome_control_ok(control)
                else:
                    eligible = label in {'search', 'what do you want to play?'}
                    if not eligible:
                        from hands.spotify_desktop import play_candidates
                        from pywinauto import Application
                        dialog = Application(backend='uia').connect(handle=self.hwnd).window(handle=self.hwnd)
                        eligible = any(c.rectangle().left <= x <= c.rectangle().right and c.rectangle().top <= y <= c.rectangle().bottom
                                       for c in play_candidates(dialog, goal['query'], goal['artist']))
                if not eligible:
                    raise ValueError(OUTSIDE_CAPABILITY)
            check()
            if action_name == 'click' and goal['app'].casefold() == 'chrome':
                # Re-check right before clicking: the page may have changed under the pointer.
                from pywinauto import Desktop
                if self.identity() != snapshot['identity'] or not chrome_control_ok(Desktop(backend='uia').from_point(x,y)):
                    raise ValueError(OUTSIDE_CAPABILITY)
            if action_name == 'click':
                mouse.click(coords=(x,y))
            else:
                mouse.scroll(coords=(x,y), wheel_dist=-3)
        elif action_name == 'play_match':
            if not snapshot.get('song_target') or goal['app'].casefold() != 'spotify':
                raise ValueError(OUTSIDE_CAPABILITY)
            controls = self.song_controls(goal)
            if (not controls or self.identity() != snapshot['identity'] or
                    (controls[0].element_info.name, tuple(controls[0].rectangle())) != snapshot['song_target']):
                raise ValueError('Stale target')
            check()
            controls[0].invoke()
        elif action_name == 'type_query':
            if self.query_submitted:
                raise ValueError('Search was already submitted')
            from pywinauto import Application
            dialog = Application(backend='uia').connect(handle=self.hwnd).window(handle=self.hwnd)
            labels = ('what do you want to play',) if goal['app'].casefold() == 'spotify' else ('address and search bar',)
            candidates = [c for kind in ('ComboBox','Edit') for c in dialog.descendants(control_type=kind)
                          if c.is_visible() and c.is_enabled() and not c.element_info.element.CurrentIsPassword
                          and any(label in (c.element_info.name or '').casefold() for label in labels)
                          and (goal['app'].casefold() == 'spotify' or chrome_control_ok(c))]
            if len(candidates) != 1:
                raise ValueError('No uniquely identified query field')
            control = candidates[0]
            expected = goal['query'] + (' '+goal['artist'] if goal['artist'] else '')
            check()
            if self.identity() != snapshot['identity'] or control.iface_value.CurrentIsReadOnly:
                raise ValueError('Query target changed')
            control.iface_value.SetValue(expected)
            for _ in range(12):
                check()
                if self.identity() != snapshot['identity']:
                    raise ValueError('Query target changed')
                if control.iface_value.CurrentValue == expected:
                    break
                time.sleep(.1)
            else:
                raise ValueError('Query readback mismatch')
            control.set_focus()
            check()
            if (self.identity() != snapshot['identity'] or not control.has_keyboard_focus()
                    or control.iface_value.CurrentValue != expected):
                raise ValueError('Search text changed before submission')
            win.hotkey('enter')
            self.query_submitted = True
        else:
            raise ValueError('Unsupported effect')

    def verify(self, goal):
        check()
        self.identity()
        if goal['app'].casefold() == 'spotify':
            from hands import media
            from hands.spotify_desktop import normalized, same_recording
            for session in media.sessions() or []:
                if ('spotify' in session.get('app','').casefold() and session.get('status') == media.PLAYING
                        and same_recording(session.get('title',''), goal['query'])
                        and (not goal['artist'] or normalized(session.get('artist','')) == normalized(goal['artist']))):
                    return Evidence('windows.spotify_session', target=goal, observed=dict(session))
        else:
            from pywinauto import Application
            from urllib.parse import urlparse, parse_qs
            dialog = Application(backend='uia').connect(handle=self.hwnd).window(handle=self.hwnd)
            for ctrl in dialog.descendants(control_type='Edit'):
                if not chrome_control_ok(ctrl):      # only Chrome's real address bar, never a page's look-alike
                    continue
                url = ctrl.iface_value.CurrentValue
                parsed = urlparse(url if '://' in url else 'https://'+url)
                if parsed.hostname in {'google.com','www.google.com','google.com.my','www.google.com.my'} and parsed.path == '/search' and parse_qs(parsed.query).get('q') == [goal['query']]:
                    return Evidence('chrome.address_bar', target=goal, observed={'url':url})
        return None

    def success_text(self, goal):
        return 'Playing '+goal['query']+'.' if goal['goal']=='play' else 'The requested Google search is open.'
