"""Background mode (step 4c, 20 Nov): YouTube found without the screen, and windows given back. Windows is faked."""
import io
import json
import urllib.error

import pytest

from hands import win, youtube


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_key_goes_in_a_header_never_in_the_address(monkeypatch):
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "secret-123")
    seen = {}

    def urlopen(req, timeout=0):
        seen.update(url=req.full_url, key=req.get_header("X-goog-api-key"))
        return Reply(json.dumps({"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "Lofi &amp; chill"}}]}).encode())
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    assert youtube.find_video("lofi") == ("abc", "Lofi & chill")
    assert seen["key"] == "secret-123" and "secret" not in seen["url"] and "q=lofi" in seen["url"]


@pytest.mark.parametrize("code, reason, said", [
    (403, "quotaExceeded", "daily search limit"), (400, "keyInvalid", "refused the key"), (500, "", "error 500")])
def test_youtube_errors_are_one_plain_sentence(monkeypatch, code, reason, said):
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "secret-123")
    body = io.BytesIO(json.dumps({"error": {"errors": [{"reason": reason}]}}).encode())

    def urlopen(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, code, "no", {}, body)
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    with pytest.raises(youtube.YouTubeError) as e:
        youtube.find_video("lofi")
    assert said in str(e.value) and "secret" not in str(e.value)


def test_without_a_key_otto_names_the_setting(monkeypatch):
    monkeypatch.delenv("OTTO_YOUTUBE_API_KEY", raising=False)
    result = youtube.play_video("lofi")
    assert not result.ok and "OTTO_YOUTUBE_API_KEY" in result.say


class FakeDesktop:
    """Windows: hwnd -> exe; a foreground; minimise and focus are recorded."""
    def __init__(self, monkeypatch, windows, front):
        self.windows, self.front, self.minimised, self.focused = dict(windows), front, [], []
        monkeypatch.setattr(win, "IS_WINDOWS", True)
        monkeypatch.setattr(win, "windows", lambda: [{"hwnd": h, "exe": e, "title": "t"} for h, e in self.windows.items()])
        monkeypatch.setattr(win, "foreground", lambda: self.front)
        monkeypatch.setattr(win, "minimise", self.minimised.append)
        monkeypatch.setattr(win, "focus", lambda h: self.focused.append(h) or True)
        monkeypatch.setattr(win, "exists", lambda h: h in self.windows)
        monkeypatch.setattr(win, "idle_seconds", lambda: 10.0)
        monkeypatch.setattr(win, "NEW_WINDOW_WAIT", 0.01)

    def opens(self, hwnd, exe, front=True):
        self.windows[hwnd] = exe
        if front:
            self.front = hwnd


def test_only_the_new_window_is_minimised_and_yours_comes_back(monkeypatch):
    pc = FakeDesktop(monkeypatch, {1: "powershell.exe", 2: "chrome.exe"}, front=1)
    with win.screen_borrowed("chrome.exe") as b:
        pc.opens(3, "chrome.exe")
    assert b.new == [3] and pc.minimised == [3] and pc.focused == [1]       # your own Chrome window (2) untouched


def test_if_you_moved_on_otto_leaves_you_alone(monkeypatch):
    pc = FakeDesktop(monkeypatch, {1: "powershell.exe"}, front=1)
    with win.screen_borrowed("chrome.exe"):
        pc.opens(3, "chrome.exe")
        pc.front = 4                                     # you clicked somewhere else meanwhile
    assert pc.minimised == [3] and pc.focused == []


def test_no_new_window_means_nothing_is_minimised(monkeypatch):
    pc = FakeDesktop(monkeypatch, {1: "powershell.exe", 2: "spotify.exe"}, front=2)
    with win.screen_borrowed("spotify.exe"):
        pass                                             # Spotify was already open: not Otto's to hide
    assert pc.minimised == [] and pc.focused == []


def test_the_window_comes_back_even_when_the_step_fails(monkeypatch):
    pc = FakeDesktop(monkeypatch, {1: "powershell.exe"}, front=1)
    with pytest.raises(RuntimeError):
        with win.screen_borrowed("chrome.exe"):
            pc.opens(3, "chrome.exe")
            raise RuntimeError("cancelled")
    assert pc.minimised == [3] and pc.focused == [1]


def test_otto_waits_for_a_pause_in_typing_but_not_forever(monkeypatch):
    import time
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    idle = iter([0.1, 0.3, 1.2])
    monkeypatch.setattr(win, "idle_seconds", lambda: next(idle))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    win.wait_for_pause()                                 # returns once 1 s passes without a key
    monkeypatch.setattr(win, "idle_seconds", lambda: 0.0)
    monkeypatch.setattr(win, "PAUSE_WAIT", 0.02)
    start = time.monotonic()
    win.wait_for_pause()                                 # always typing: gives up after PAUSE_WAIT
    assert time.monotonic() - start < 1


def test_a_video_is_minimised_only_once_it_plays(monkeypatch):
    from hands import web
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "secret-123")
    monkeypatch.setattr(youtube, "find_video", lambda q, n=1: ("abc", "Lofi girl"))
    pc = FakeDesktop(monkeypatch, {1: "powershell.exe"}, front=1)
    playing = [set(), set(), {"Lofi girl"}]               # before; still loading; playing
    monkeypatch.setattr(youtube, "_chrome_playing", lambda: playing.pop(0) if len(playing) > 1 else playing[0])
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    opened = []
    monkeypatch.setattr(web, "open_in_browser", lambda url, new_window=False: opened.append((url, new_window))
                        or pc.opens(3, "chrome.exe"))
    result = youtube.play_video("lofi")
    assert opened == [("https://www.youtube.com/watch?v=abc", True)]
    assert result.ok and result.say == "Playing Lofi girl in the background." and result.data["window"] == 3
    assert pc.minimised == [3] and pc.focused == [1]


def test_spotify_opened_for_music_goes_to_the_background(monkeypatch):
    from hands import apps, media
    pc = FakeDesktop(monkeypatch, {1: "code.exe"}, front=1)
    monkeypatch.setattr(apps, "open_app", lambda name: pc.opens(5, "spotify.exe"))
    media._launch_spotify()
    assert pc.minimised == [5] and pc.focused == [1]


def test_live_task_passes_only_when_it_plays_hidden_and_you_keep_the_front(monkeypatch):
    from core import live_test
    task = live_test._background_video()
    monkeypatch.delenv("OTTO_YOUTUBE_API_KEY", raising=False)
    assert "OTTO_YOUTUBE_API_KEY" in task.setup({})
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "k")
    pc = FakeDesktop(monkeypatch, {1: "windowsterminal.exe", 2: "chrome.exe"}, front=1)
    monkeypatch.setattr(win, "windows", lambda: [{"hwnd": h, "exe": e, "title": "Lofi - YouTube - Google Chrome"}
                                                 for h, e in pc.windows.items()])
    playing = set()
    monkeypatch.setattr(youtube, "_chrome_playing", lambda: set(playing))
    monkeypatch.setattr(live_test, "wait_for", lambda test, seconds=4.0: bool(test()))
    memo = {}
    assert task.setup(memo) is None and task.steps[0].say(memo) == "play a lofi video in the background"
    pc.opens(3, "chrome.exe", front=False)
    playing.add("Lofi")
    monkeypatch.setattr(win, "is_minimised", lambda h: h == 3)
    assert task.steps[0].check(memo) == (True, "")
    pc.front = 3
    monkeypatch.setattr(live_test, "front", lambda: {"title": "Lofi - YouTube"})
    assert task.steps[0].check(memo)[0] is False
    closed = []
    monkeypatch.setattr(win, "close", closed.append)
    task.cleanup(memo)
    assert closed == [3]                                   # never your own Chrome window (2)


def test_live_task_repeats_wait_for_the_last_video_to_stop(monkeypatch):
    # The same lofi video comes up each run: run 2 must not start while run 1's video still plays (Opus review).
    from core import live_test
    task = live_test._background_video()
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "k")
    pc = FakeDesktop(monkeypatch, {1: "windowsterminal.exe"}, front=1)
    monkeypatch.setattr(win, "windows", lambda: [{"hwnd": h, "exe": e, "title": "Lofi - YouTube"}
                                                 for h, e in pc.windows.items()])
    playing = {"Lofi"}
    monkeypatch.setattr(youtube, "_chrome_playing", lambda: set(playing))
    memo = {"playing": set()}
    task.setup(memo)
    pc.opens(3, "chrome.exe", front=False)

    def close(hwnd):                     # closing takes a moment: the window and its sound go on the next look
        pc.windows.pop(hwnd)
        playing.clear()
    waited = []
    monkeypatch.setattr(win, "close", lambda h: None)
    monkeypatch.setattr(live_test, "wait_for", lambda test, seconds=4.0: waited.append(test()) or close(3) or test())
    task.cleanup(memo)
    assert waited == [False] and not playing and 3 not in pc.windows


# ---- playing a chosen YouTube result (20 Nov live run: a Mix and the sidebar were clicked) ------------------

def test_live_streams_are_skipped_and_the_nth_result_is_picked(monkeypatch):
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "k")
    items = [{"id": {"videoId": "live"}, "snippet": {"title": "24/7 radio", "liveBroadcastContent": "live"}},
             {"id": {"videoId": "a"}, "snippet": {"title": "A", "liveBroadcastContent": "none"}},
             {"id": {"videoId": "b"}, "snippet": {"title": "B", "liveBroadcastContent": "none"}}]
    monkeypatch.setattr(youtube.urllib.request, "urlopen", lambda req, timeout=0: Reply(json.dumps({"items": items}).encode()))
    assert youtube.find_video("lofi", 2) == ("b", "B") and youtube.find_video("lofi", 3) is None


def test_a_video_in_front_counts_only_when_chrome_shows_that_video(monkeypatch):
    from hands import web
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(youtube, "find_video", lambda q, n=1: ("abc", "Lofi girl"))
    monkeypatch.setattr(youtube, "SHOW_WAIT", 0.01)
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    pc = FakeDesktop(monkeypatch, {1: "chrome.exe"}, front=1)
    monkeypatch.setattr(web, "open_in_browser", lambda url, new_window=False: None)
    shown = ["https://www.youtube.com/watch?v=xyz"]
    monkeypatch.setattr(web, "chrome_addresses", lambda only=None: list(shown))
    assert not youtube.play_video("lofi", "2", "no").ok                       # another video: not done
    shown[0] = "youtube.com/watch?v=abc&list=RDabc"
    result = youtube.play_video("lofi", "2", "no")
    assert result.ok and result.say == "Playing Lofi girl." and pc.minimised == []


def test_search_with_play_ends_the_request_with_the_checked_result(monkeypatch):
    from core import skills, tools
    calls = []

    def action(ctx, do, **args):
        calls.append((do, args))
        return tools.ToolResult(True, "Playing Lofi girl.", {"video": "abc", "window": 7})
    monkeypatch.setattr(skills, "_action", action)
    ctx = tools.ToolContext(dry_run=False, brain=None)
    result = skills.search(ctx, "lofi", "youtube", play="the 2nd")
    assert calls == [("play_video", {"query": "lofi", "which": "2", "background": "no"})]
    assert result.ok and result.observed["end"] == "done" and ctx.hwnd == 7


def test_without_a_key_search_falls_back_to_the_results_page(monkeypatch):
    from core import skills, tools
    calls = []

    def action(ctx, do, **args):
        calls.append(do)
        if do == "play_video":
            return tools.ToolResult(False, "no key", {"fallback": True})
        return tools.ToolResult(False, "Chrome isn't there")
    monkeypatch.setattr(skills, "_action", action)
    result = skills.search(tools.ToolContext(dry_run=False, brain=None), "lofi", "youtube", play="2", background="yes")
    assert calls == ["play_video", "open_site"] and result.say == "Chrome isn't there"
