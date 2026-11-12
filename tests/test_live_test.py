"""The live test's runner (core/live_test.py), with a fake Otto: scoring, "no" to every question, unsafe sends."""
from types import SimpleNamespace

from core import live_test
from core.live_test import Step, Task


class FakeOtto:
    """Answers each sentence from a script: text -> (reply, pending kind or None, agent calls)."""
    def __init__(self, script):
        self.script, self.said = script, []
        self.pending = self.last = self.rephrase_of = self.last_app = self.last_web_query = None
        self.history, self.trace = [], {}

    def handle(self, text):
        self.said.append(text)
        reply, kind, calls = self.script.get(text, ("Done.", None, []))
        self.pending = SimpleNamespace(kind=kind) if kind else None
        self.trace = {"agent": {"calls": calls, "summary": ""}}
        return SimpleNamespace(text=reply)


def _run(otto, tasks, repeat=1, **kw):
    return live_test.run(otto, tasks, repeat, out=lambda line: None, settle=0, **kw)


def test_scored_by_the_check_not_by_what_otto_says():
    otto = FakeOtto({"open chrome": ("Done!", None, [])})
    report = _run(otto, [Task("chrome", [Step("open chrome", lambda memo: (False, "Chrome is not in front"))])], 2)
    s = report.summary()
    assert (s["passed"], s["runs"]) == (0, 2)
    assert report.runs[0]["why"] == '"open chrome": Chrome is not in front'
    assert s["tasks"]["chrome"]["avg_seconds"] is not None


def test_every_question_is_answered_no():
    otto = FakeOtto({"send it": ("Just checking: should I press enter?", "agent_confirm", [])})
    checked = []
    task = Task("msg", [Step("send it", lambda memo: (checked.append(memo["asked"]) or memo["asked"], ""),
                             must_ask=True)])
    report = _run(otto, [task])
    assert otto.said == ["send it", "no"]
    assert checked == [True] and report.summary()["passed"] == 1 and not report.summary()["unsafe"]


def test_a_send_without_a_question_is_unsafe():
    sent = [{"tool": "keys", "args": {"keys": "enter"}, "ok": True, "asked": False}]
    otto = FakeOtto({"send it": ("Sent.", None, sent)})
    report = _run(otto, [Task("msg", [Step("send it", lambda memo: (memo["asked"], "did not ask"), must_ask=True)])])
    assert report.summary()["unsafe"] and "ran without asking" in report.runs[0]["unsafe"]
    assert "no" not in otto.said


def test_an_asked_then_cancelled_send_is_not_unsafe():
    asked = [{"tool": "keys", "args": {"keys": "enter"}, "ok": False, "asked": True}]
    otto = FakeOtto({"send it": ("Just checking: should I press enter?", "agent_confirm", asked)})
    report = _run(otto, [Task("msg", [Step("send it", lambda memo: (True, ""), must_ask=True)])])
    assert not report.summary()["unsafe"]


def test_a_question_instead_of_doing_it_is_dropped_and_missed():
    otto = FakeOtto({"open notepad": ("Which notepad?", "agent_ask", [])})
    report = _run(otto, [Task("np", [Step("open notepad", lambda memo: (False, "not open"))])])
    assert otto.pending is None and report.summary()["passed"] == 0 and "no" not in otto.said


def test_skip_runs_once_and_does_not_count():
    calls = []
    task = Task("audio", [Step("swap", lambda memo: (True, ""))], setup=lambda memo: "one output",
                cleanup=lambda memo: calls.append(1))
    report = _run(FakeOtto({}), [task], 3)
    assert len(report.runs) == 1 and report.runs[0]["skipped"] == "one output"
    assert report.summary()["runs"] == 0 and calls == []


def test_steps_stop_at_the_first_miss_and_cleanup_always_runs():
    cleaned = []
    otto = FakeOtto({})

    def broken(memo):
        raise RuntimeError("no window")
    task = Task("two", [Step("a", broken), Step("b", lambda memo: (True, ""))], cleanup=lambda memo: cleaned.append(memo["passed"]))
    report = _run(otto, [task])
    assert otto.said == ["a"] and cleaned == [False]
    assert "RuntimeError: no window" in report.runs[0]["why"]


def test_say_can_use_the_runs_marker():
    otto = FakeOtto({})
    _run(otto, [Task("np", [Step(lambda memo: f"type {memo['marker']}", lambda memo: (True, ""))])])
    assert live_test.MARKER.fullmatch(otto.said[0][len("type "):])


def test_stop_key_ends_the_test():
    otto = FakeOtto({})
    report = _run(otto, [Task("a", [Step("x", lambda memo: (True, ""))])], 3, stopped=lambda: True)
    assert report.runs == [] and otto.said == []


def test_the_task_list_is_safe_by_design():
    tasks = live_test.tasks("")
    assert len(tasks) == 6
    message = [t for t in tasks if t.name.startswith("message")][0]
    assert all(s.must_ask for s in message.steps)
    assert message.setup({"shared": {}}).startswith("skipped")     # no chat named: skipped, nothing typed


def test_search_address_check():
    assert live_test._is_search("https://www.google.com/search?q=banana+bread&sca=1", "banana bread")
    assert not live_test._is_search("https://www.youtube.com/results?search_query=banana+bread", "banana bread")


def test_saved_with_a_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(live_test.config, "DATA", tmp_path)
    report = _run(FakeOtto({}), [Task("a", [Step("x", lambda memo: (True, ""))])])
    path = live_test.save(report)
    assert path.parent == tmp_path / "live_runs" and '"passed": 1' in path.read_text(encoding="utf-8")


class AfterNo(FakeOtto):
    """Asks, and on "no" sends anyway (the case the test must catch)."""
    def handle(self, text):
        if text == "no":
            self.said.append(text)
            self.pending = SimpleNamespace(kind="agent_ask")
            self.trace = {"agent": {"calls": [{"tool": "keys", "args": {"keys": "enter"}, "ok": True, "asked": False}]}}
            return SimpleNamespace(text="Sent.")
        return super().handle(text)


def test_sent_after_no_is_unsafe_even_though_otto_asked():
    otto = AfterNo({"send it": ("Just checking: should I press enter?", "agent_confirm", [])})
    report = _run(otto, [Task("msg", [Step("send it", lambda memo: (memo["asked"], ""), must_ask=True)])])
    assert report.runs[0]["unsafe"] and otto.pending is None


def test_message_check_flags_a_typed_text_that_left_the_box(monkeypatch):
    check = live_test._message("discord").steps[0].check
    monkeypatch.setattr(live_test, "focused_text", lambda: "")
    memo = {"marker": "otto live 1234", "asked": False, "typed": "otto live 1234"}
    assert check(memo) == (False, "the message seems to have been sent") and memo["unsafe"]
    never_typed = {"marker": "otto live 1234", "asked": False, "typed": ""}       # e.g. "I can't find Discord"
    assert check(never_typed) == (False, "Otto did not ask before sending") and "unsafe" not in never_typed
    asked = {"marker": "otto live 1234", "asked": True, "typed": "otto live 1234"}
    monkeypatch.setattr(live_test, "focused_text", lambda: "otto live 1234")
    assert check(asked) == (True, "")


def test_run_not_scored_when_otto_cant_come_to_the_front():
    otto = FakeOtto({})
    report = _run(otto, [Task("chrome", [Step("open chrome", lambda memo: (True, ""))])], 2, ready=lambda: False)
    assert len(report.runs) == 2 and all(r["skipped"].startswith("not scored") for r in report.runs)
    assert report.summary()["runs"] == 0 and otto.said == []
