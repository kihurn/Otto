"""The new core inside the pipeline (agent core plan, task 7): the fast path or the agent loop, behind core.agent."""

import time
from types import SimpleNamespace

import pytest

from core.brain import BrainReply
from tests.test_pipeline import otto  # noqa: F401  (the fake-Laya, fake-brain Otto)


def call(tool, why="", **args):
    return {"tool": tool, "args": args, "why": why}


class Scripted:
    """Stands in for Qwen in the loop: replies with the next scripted tool call, records what it was sent."""
    def __init__(self, brain, *replies):
        self.brain = brain
        self.replies = list(replies)
        self.seen = []
        self.time_left = []

    def __call__(self, messages, job="decide", want_json=True, required=(), timeout=None):
        self.seen.append([dict(m) for m in messages])
        deadline = getattr(self.brain, "deadline", None)
        self.time_left.append(deadline - time.monotonic() if deadline else None)
        if not self.replies:
            raise AssertionError("Qwen was asked more often than scripted")
        return BrainReply("", self.replies.pop(0), "qwen", 0.1)


@pytest.fixture
def new(otto):  # noqa: F811
    otto.settings.setdefault("core", {})["agent"] = True
    return otto


def script(o, *replies):
    s = Scripted(o.brain, *replies)
    o.brain.chat = s
    return s


def no_agent(monkeypatch):
    from core import agent

    def refuse(*a, **k):
        raise AssertionError("the agent loop should not run for this")
    monkeypatch.setattr(agent, "run", refuse)


# ---- which path ----------------------------------------------------------------------------------

def test_flag_off_keeps_old_behaviour(otto, monkeypatch):  # noqa: F811
    no_agent(monkeypatch)
    assert otto.settings.get("core", {}).get("agent") is False
    assert "would open Spotify" in otto.handle("open spotify").text


def test_simple_volume_stays_fast_path(new, monkeypatch):
    no_agent(monkeypatch)
    assert "set the volume to 30" in new.handle("volume 30").text
    assert new.trace["rule"] == "whole_sentence"


def test_laya_sure_and_whole_sentence_is_fast(new, monkeypatch):
    no_agent(monkeypatch)
    assert "would open Spotify" in new.handle("open spotify").text


def test_laya_unsure_goes_to_agent(new):
    new.router.predict = lambda t: {"area": "apps", "prob": 0.5, "top": [], "ms": 1}
    s = script(new, call("open", what="Spotify"), call("done", say="Opened Spotify."))
    assert new.handle("open spotify").text == "Opened Spotify."
    assert len(s.seen) == 2


def test_joined_request_goes_to_agent(new):
    s = script(new, call("open", what="youtube"), call("done", say="Opened YouTube."))
    new.handle("open youtube and play the first video")
    assert s.seen and s.seen[0][-1]["content"] == "open youtube and play the first video"
    assert new.trace["agent"]["first"] == {"tool": "open", "args": {"what": "youtube"}}


def test_partial_rule_match_goes_to_agent(new):
    s = script(new, call("done", say="Which video?"))
    new.handle("play the first video")
    assert len(s.seen) == 1                 # the old music rule did not grab it


def test_maths_answered_locally(new, monkeypatch):
    no_agent(monkeypatch)
    assert "12" in new.handle("what's 15 percent of 80").text


@pytest.mark.parametrize("text", ["what's the time in tokyo", "google what time is it in london",
                                  "type 2+2 in notepad", "open 7-zip"])
def test_only_whole_questions_are_answered_locally(new, text):
    s = script(new, call("done", say="agent"))
    assert new.handle(text).text in ("agent", "") or new.trace.get("rule") == "whole_sentence"
    assert new.trace.get("answer_by") != "local"


def test_time_question_answered_locally(new, monkeypatch):
    no_agent(monkeypatch)
    assert new.handle("what time is it?").text.startswith("It's")


def test_youtube_video_by_someone_is_not_spotify(new):
    s = script(new, call("open", what="youtube"), call("done", say="On it."))
    new.handle("play the latest video by mrbeast on youtube")
    assert s.seen and new.trace["agent"]["first"]["tool"] == "open"


def test_unbound_volume_followup_reaches_the_agent(new):
    s = script(new, call("done", say="Which one?"))
    new.handle("increase it to 70")
    assert len(s.seen) == 1


def test_off_switch_as_text_is_off(otto, monkeypatch):  # noqa: F811
    otto.settings.setdefault("core", {})["agent"] = "false"
    no_agent(monkeypatch)
    assert "would open Spotify" in otto.handle("open spotify").text


def test_answer_clears_stale_screen_reads(new):
    s = script(new, call("ask_user", question="Which one?"), call("done", say="Done."))
    new.handle("swap my audio output")
    ctx = new.pending.agent["ctx"]
    ctx.controls, ctx.look = [{"id": 1, "name": "Old"}], {"region": (0, 0, 1, 1), "scale": 1}
    new.handle("the first")
    assert ctx.controls == [] and ctx.look == {}


def test_old_supervisor_is_off_with_the_new_core(new, monkeypatch):
    from core import interpreter
    monkeypatch.setattr(interpreter, "review", lambda *a, **k: (_ for _ in ()).throw(AssertionError("old layer")))
    new.dry_run = False
    res = SimpleNamespace(ok=False, data={"outcome_status": "failed"}, say="It failed.")
    plan = SimpleNamespace(steps=[{"do": "open_app", "with": {"app": "Notepad"}}])
    assert new._supervise("open notepad", plan, res) is None


def test_misheard_then_yes_uses_the_new_core(new):
    s = script(new, call("done", say="Okay."))
    assert "did you say" in new.handle("open youtube and play the first video", heard_conf=-2).text
    new.handle("yes")
    assert len(s.seen) == 1


# ---- asking and confirming ----------------------------------------------------------------------

def test_agent_question_then_answer_resumes(new):
    s = script(new, call("ask_user", question="Which output?", options="AirPods;Speakers"),
               call("done", say="Switched to your AirPods."))
    reply = new.handle("swap my audio output")
    assert "Which output?" in reply.text and "AirPods" in reply.text
    assert new.pending.kind == "agent_ask"
    assert new.handle("airpods").text == "Switched to your AirPods."
    assert any("The user answered: airpods" in m["content"] for m in s.seen[-1])
    assert new.pending is None


def _reply_flow(o):
    return script(o, call("open", what="Discord"), call("read_window", app="Discord"), call("type", text="see you soon"), call("keys", keys="enter"),
                  call("done", say="Sent."))


def test_confirm_yes_runs(new):
    _reply_flow(new)
    reply = new.handle("reply see you soon to john on discord")
    assert reply.text.startswith("Just checking: should I send")
    assert new.pending.kind == "agent_confirm"
    assert new.handle("yes").text == "Sent."
    calls = new.trace["agent"]["calls"]
    # The Enter appears twice: once when Otto asked, once when it ran after the yes.
    assert [c["tool"] for c in calls] == ["open", "read_window", "type", "keys", "keys", "done"] and calls[4]["ok"]


def test_confirm_no_cancels(new):
    s = _reply_flow(new)
    new.handle("reply see you soon to john on discord")
    assert new.handle("no").text == "Okay, I won't. What I typed is still in the box."
    assert len(s.replies) == 1              # Qwen was not asked again


def test_other_request_drops_the_waiting_step(new):
    _reply_flow(new)
    new.handle("reply see you soon to john on discord")
    assert "pause" in new.handle("pause").text.lower()
    assert new.pending is None
    assert "no current question" in new.handle("yes").text


def test_stale_yes_never_approves(new):
    s = _reply_flow(new)
    new.handle("reply see you soon to john on discord")
    new.pending.expires = time.time() - 1
    assert "no current question" in new.handle("yes").text
    assert len(s.replies) == 1


def test_yes_refused_when_the_window_changed(new, monkeypatch):
    from core import agent_safety, tools
    _reply_flow(new)
    new.handle("reply see you soon to john on discord")
    ran = []
    monkeypatch.setattr(tools.TOOLS["keys"], "run", lambda ctx, keys: ran.append(keys))
    new.pending.agent["ctx"].app = "Chrome"     # something else is in front now
    assert "window changed" in new.handle("yes").text
    assert ran == []
    assert agent_safety  # imported for clarity: same_place() made the call


def test_agent_has_its_own_deadline(new):
    s = script(new, call("ask_user", question="Which one?"), call("done", say="Done."))
    new.handle("swap my audio output")
    new.handle("the second one")             # handle() starts a 45 s turn; the resumed loop gets 90 s
    assert all(t is not None and t > 60 for t in s.time_left)


def test_conversation_reaches_the_agent(new):
    s = script(new, call("open", what="Notepad"), call("done", say="Opened Notepad."),
               call("done", say="Okay."))
    new.handle("open my notes app please and get ready")
    new.handle("now write something nice")
    contents = [m["content"] for m in s.seen[-1]]
    assert "open my notes app please and get ready" in contents
    assert any(c.startswith("Opened Notepad.") and "open Notepad" in c for c in contents)


# ---- the window in front when you typed into Otto ------------------------------------------------

def test_typed_yes_brings_the_asked_window_back(monkeypatch):
    from core import agent_safety, tools
    from hands import win
    state = {"fg": 99}                      # 99 = Otto's own console, where the yes was typed
    focused = []
    monkeypatch.setattr(win, "foreground", lambda: state["fg"])

    def focus(h):
        focused.append(h)
        state["fg"] = h
        return True
    monkeypatch.setattr(win, "focus", focus)
    monkeypatch.setattr(agent_safety, "front", lambda ctx: {"hwnd": state["fg"], "exe": "discord.exe",
                                                            "title": "Discord", "focused": ""})
    ctx = tools.ToolContext(dry_run=False)
    before = {"hwnd": 7, "exe": "discord.exe", "title": "Discord", "focused": ""}
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert agent_safety.same_place(before, ctx) and focused == [7]
    monkeypatch.setattr(win, "focus", lambda h: False)
    state["fg"] = 99
    assert not agent_safety.same_place(before, ctx)


def test_second_confirm_takes_a_new_snapshot(monkeypatch):
    from core import agent, agent_safety, tools
    from hands import registry
    registry.load_all()
    # The window in front follows the app the agent opened (Discord until Slack is opened).
    monkeypatch.setattr(agent_safety, "front", lambda ctx: {"hwnd": 0, "focused": "", "title": ctx.app or "Discord",
                                                            "exe": (ctx.app or "Discord").lower() + ".exe"})
    brain = SimpleNamespace(brief=lambda: "")
    s = Scripted(brain, call("read_window"), call("type", text="hi"), call("keys", keys="enter"),
                 call("open", what="Slack"), call("read_window", app="Slack"), call("type", text="hey"), call("keys", keys="enter"),
                 call("done", say="Both sent."))
    brain.chat = s
    ctx = tools.ToolContext(dry_run=True)
    r = agent.run("say hi on discord and hey on slack", [], brain, ctx)
    assert r.status == "confirm"
    r = agent.resume(r.pending, brain, yes=True)
    assert r.status == "confirm" and "Slack" in r.say    # asked again, about the new window
    r = agent.resume(r.pending, brain, yes=True)
    assert r.status == "done" and r.say == "Both sent."


# ---- saving -------------------------------------------------------------------------------------

def _finished(o, ok=True, step_ok=True):
    from core import agent
    calls = [{"tool": "open", "args": {"what": "youtube"}, "ok": True, "why": ""},
             {"tool": "click", "args": {"control": 1}, "ok": step_ok, "why": ""},
             {"tool": "done", "args": {"say": "Playing."}, "ok": ok, "why": ""}]
    return o._agent_reply("open youtube and play the first video", agent.AgentResult("done", "Playing.", calls, ok))


def test_save_that_saves_a_verified_agent_run(new):
    from core import examples
    new.dry_run = False
    _finished(new)
    assert "Saved" in new.handle("save that").text
    saved = examples.load()
    assert saved[-1]["request"] == "open youtube and play the first video"
    assert [c["tool"] for c in saved[-1]["calls"]] == ["open", "click", "done"]


def test_save_that_refuses_unverified_runs(new):
    from core import examples
    _finished(new)                            # a dry run: nothing really happened
    assert "won't save" in new.handle("save that").text
    new.dry_run = False
    _finished(new, step_ok=False)             # Qwen said done, but a step had failed
    assert "won't save" in new.handle("save that").text
    assert examples.load() == []


def test_save_that_after_a_yes_saves_each_step_once(new):
    from core import agent, examples
    new.dry_run = False
    calls = [{"tool": "type", "args": {"text": "hi"}, "ok": True},
             {"tool": "keys", "args": {"keys": "enter"}, "ok": False, "asked": True},
             {"tool": "keys", "args": {"keys": "enter"}, "ok": True},
             {"tool": "done", "args": {"say": "Sent."}, "ok": True}]
    new._agent_reply("say hi to john", agent.AgentResult("done", "Sent.", calls, True))
    assert "Saved" in new.handle("save that").text
    assert [c["tool"] for c in examples.load()[-1]["calls"]] == ["type", "keys", "done"]


def test_forget_removes_the_saved_example(new):
    from core import examples
    new.dry_run = False
    _finished(new)
    new.handle("save that")
    assert "Forget" in new.handle("forget that").text
    new.handle("yes")
    assert examples.load() == []


# ---- otto eval with the new core ------------------------------------------------------------------

def test_eval_judges_the_first_call(new):
    from core import evaluate
    s = script(new, call("open", what="youtube"), call("done", say="never reached"))
    d = evaluate.decide_only(new, "open youtube and play the first video")
    assert (d.route, d.tool, d.args) == ("loop", "open", {"what": "youtube"})
    assert len(s.seen) == 1                 # stopped after the first call


def test_eval_must_ask_runs_to_the_question(new):
    from core import evaluate
    _reply_flow(new)
    d = evaluate.decide_only(new, "reply see you soon to john on discord", must_ask=True)
    assert d.asks and not d.unsafe and d.tool == "open"


def test_eval_flags_a_risky_run_that_never_asked(new):
    from core import evaluate
    script(new, call("open", what="Notepad"), call("done", say="Deleted it."))
    d = evaluate.decide_only(new, "delete the file called old notes", must_ask=True)
    assert d.unsafe and not d.asks
    case = evaluate.EvalCase("delete the file called old notes", "loop", "", [], False, True)
    assert evaluate.score([case], lambda t: d).safety_regressions == [case.text]


def test_eval_asking_a_question_is_not_asking_permission(new):
    from core import evaluate
    script(new, call("ask_user", question="Which file?"))
    d = evaluate.decide_only(new, "delete the file called old notes", must_ask=True)
    assert not d.asks and not d.unsafe


def test_dry_run_knows_explorer_and_terminals():
    from core import agent_safety, tools
    for app, exe in (("File Explorer", "explorer.exe"), ("Command Prompt", "cmd.exe"), ("Terminal", "windowsterminal.exe")):
        assert agent_safety.front(tools.ToolContext(dry_run=True, app=app))["exe"] == exe


# ---- review round 2: stopping, Otto's own window, timing ------------------------------------------

def test_cancel_key_stops_the_loop(new):
    s = script(new, call("open", what="Notepad"), call("open", what="Spotify"), call("done", say="never"))
    real = s.__call__
    seen_task = []

    def chat(messages, **k):
        seen_task.append(new.active_task)
        reply = real(messages, **k)
        new.active_task.cancel.set()          # what the cancel key does, while Otto is working
        return reply
    new.brain.chat = chat
    assert "I stopped" in new.handle("open notepad and then spotify and tidy up").text
    assert len(s.seen) == 1 and seen_task[0] is not None
    assert new.active_task is None and new.pending is None


def test_cancel_interrupts_a_step_under_way(monkeypatch):
    from core import action_runtime, agent, tools
    stop = agent.Stopper()

    def pressing(ctx, keys):
        stop.cancel.set()
        action_runtime.check()                # hands/win does this before every key press
        raise AssertionError("the key was pressed after cancel")
    monkeypatch.setattr(tools.TOOLS["keys"], "run", pressing)
    brain = SimpleNamespace(brief=lambda: "")
    brain.chat = Scripted(brain, call("keys", keys="pagedown"), call("done", say="never"))
    r = agent.run("scroll down a page", [], brain, tools.ToolContext(dry_run=True), stop=stop)
    assert r.status == "stopped" and "I stopped" in r.say
    assert action_runtime.current.get() is None


def test_nothing_is_typed_into_ottos_own_window(monkeypatch):
    from core import tools
    from hands import registry, win
    from senses import eyes
    registry.load_all()
    monkeypatch.setattr(win, "foreground", lambda: 99)
    monkeypatch.setattr(win, "OTTO_WINDOWS", {99})
    monkeypatch.setattr(eyes, "last_other_window", lambda: None)      # nowhere to go back to
    ran = []
    for name in ("keys", "type", "read_window"):
        monkeypatch.setattr(tools.TOOLS[name], "run", lambda ctx, **k: ran.append(k))
    ctx = tools.ToolContext(dry_run=False)
    for name, args in (("keys", {"keys": "pagedown"}), ("type", {"text": "hi"}), ("read_window", {})):
        result = tools.call(name, args, ctx)
        assert not result.ok and "own window" in result.say
    assert ran == []


def test_unread_counter_in_the_title_is_not_a_different_window(monkeypatch):
    from core import agent_safety, tools
    from hands import win
    monkeypatch.setattr(win, "foreground", lambda: 7)
    now = {"hwnd": 7, "exe": "discord.exe", "title": "(3) #general - Discord", "focused": "Message #general"}
    monkeypatch.setattr(agent_safety, "front", lambda ctx: dict(now))
    ctx = tools.ToolContext(dry_run=False)
    before = {"hwnd": 7, "exe": "discord.exe", "title": "#general - Discord", "focused": "Message #general"}
    assert agent_safety.same_place(before, ctx)
    now["title"] = "#random - Discord"
    assert not agent_safety.same_place(before, ctx)
    now.update(title="#general - Discord", focused="Search")
    assert not agent_safety.same_place(before, ctx)


def test_agent_questions_wait_two_minutes(new):
    script(new, call("ask_user", question="Which one?"))
    new.handle("swap my audio output")
    assert new.pending.expires - time.time() > 100


def test_do_that_again_goes_to_the_agent(new):
    s = script(new, call("done", say="Did it again."))
    assert new.handle("do that again").text == "Did it again."
    assert len(s.seen) == 1


def test_old_conversation_is_left_out(new):
    new.history.append({"you": "an hour ago", "otto": "ok", "time": time.time() - 3600})
    new.history.append({"you": "just now", "otto": "sure", "time": time.time() - 5})
    assert [m["content"] for m in new._conversation()] == ["just now", "sure"]


def test_failed_steps_are_not_saved(new):
    from core import agent, examples
    new.dry_run = False
    calls = [{"tool": "read_window", "args": {"app": "Chrome"}, "ok": False},
             {"tool": "read_window", "args": {}, "ok": True},
             {"tool": "click", "args": {"control": 2}, "ok": True},
             {"tool": "done", "args": {"say": "Done."}, "ok": True}]
    new._agent_reply("click the first link", agent.AgentResult("done", "Done.", calls, True))
    new.handle("save that")
    assert [c["args"] for c in examples.load()[-1]["calls"]] == [{}, {"control": 2}, {"say": "Done."}]


def test_dashes_are_not_sums():
    from core import answers
    assert answers.whole_local_answer("10-4") is None
    assert answers.whole_local_answer("2026-11-12") is None
    assert answers.whole_local_answer("what's 10-4") == "That's 6."
    assert answers.whole_local_answer("12 times 12") == "That's 144."


def test_known_site_opens_the_fast_way(new, monkeypatch):
    from hands import web
    assert "youtube" in web.sites()
    no_agent(monkeypatch)
    new.handle("open youtube")
    assert new.trace["rule"] == "whole_sentence" and new.trace["intent"]["action"] == "open_site"
