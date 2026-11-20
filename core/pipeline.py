"""The request flow, start to finish (see docs/ARCHITECTURE.md, section 4).

guards -> Laya (area) -> zone: high = do it / middle = ask you / low = brain guesses, then ask you
       -> details -> plan -> safety gate -> hands -> reply -> log + learn
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from copy import deepcopy
import hashlib
import json


def plan_scope(steps):
    return hashlib.sha256(json.dumps(steps, sort_keys=True, allow_nan=False).encode()).hexdigest()

from core import answers, details, guards, learning, log, planner, safety
from core.areas import ACTIONS, AREA_PHRASES, AREAS
from core.brain import Brain, NoBrainAvailable
from core.details import Intent
from core.router import Router
from hands import apps, files, registry

# Thanks and goodbyes need no model at all (19 Nov: "Thank you." went to Gemma and ended "I got confused").
CLOSERS = {"thanks": "Anytime.", "thank you": "You're welcome.", "thanks otto": "Anytime.",
           "thank you otto": "You're welcome.", "thank you so much": "You're welcome!", "thanks a lot": "Anytime.",
           "cheers": "Anytime.", "ok thanks": "Anytime.", "okay thanks": "Anytime.", "ok thank you": "You're welcome.",
           "okay thank you": "You're welcome.", "bye": "Bye!", "goodbye": "Bye!", "bye otto": "Bye!",
           "good night": "Good night!", "goodnight": "Good night!"}


_STOP = {"the", "a", "an", "can", "you", "could", "please", "pls", "my", "me", "to", "on", "in", "it", "this",
         "that", "and", "for", "of", "otto", "auto", "open", "up", "do", "what", "whats", "is", "i", "want"}


def _shared_words(a: str, b: str) -> bool:
    words = lambda s: {w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) > 2 and w not in _STOP}
    return bool(words(a) & words(b))


EARLIER = ("Earlier in this conversation (all of it is already finished: never redo any of it unless the new request "
           "asks. Use it to understand what words like it, that, there or the same mean in the new request):\n")


@dataclass
class Reply:
    text: str
    details: str = ""
    speak: str | None = None      # what to say aloud, if different from text


@dataclass
class Pending:
    kind: str                     # heard / confirm_area / confirm_plan / pick / rephrase / confirm_forget
    text: str = ""
    area: str = ""
    intent: Intent | None = None
    plan: planner.Plan | None = None
    files: list = field(default_factory=list)
    expires: float = 0.0
    task: object | None = None
    scope: str = ''
    revision: int = 0
    agent: dict | None = None     # the agent loop's state, for agent_ask / agent_confirm


def _rates(calls: list[dict]) -> str:
    """Ollama's reading and writing speed over this turn's calls, e.g. ", reads 1,800 tok/s, writes 38 tok/s".
    Slow reading points at the prompt (no reuse), slow writing at the card (model partly off the GPU)."""
    calls = [c for c in calls if not c.get("failed")]
    # Reading speed only when Ollama said how much it reused: otherwise the count includes reused tokens and the
    # speed would look far higher than it is (Codex re-review 20 Nov).
    known = calls and all(c.get("reuse_reported") for c in calls)
    read = sum(c.get("prompt_read") or 0 for c in calls) if known else 0
    read_s = sum(c.get("read_s") or 0 for c in calls)
    wrote = sum(c.get("reply_tokens") or 0 for c in calls)
    write_s = sum(c.get("write_s") or 0 for c in calls)
    load = sum(c.get("load_s") or 0 for c in calls)
    out = ""
    if read and read_s:
        out += f", reads {read / read_s:,.0f} tok/s"
    if wrote and write_s:
        out += f", writes {wrote / write_s:,.0f} tok/s"
    if load >= 1:
        out += f", loading {load:.1f} s"
    return out


class Otto:
    def __init__(self, settings: dict, dry_run: bool = False, say=print):
        self.settings = settings
        self.dry_run = dry_run
        self.say = say
        self.brain = Brain(settings)
        self.router = Router(settings)
        self.apps = apps.INDEX
        self.pending: Pending | None = None
        self.rephrase_of: str | None = None
        self.last: dict | None = None
        self.trace: dict = {}
        self.history: deque = deque(maxlen=8)   # recent exchanges, for follow-ups and the brief
        self.active_task = None
        self.progress = lambda message: None
        self.last_web_query = None
        self.last_app = None          # (app name, time) of the last app Otto acted in
        self.turn_deadline = None
        self.agent_stop_after = None  # otto eval: judge only the agent's first call
        from core.context import ActionContext
        self.action_context = ActionContext()
        from core.audio_context import VolumeContext
        self.volume_context = VolumeContext()
        self.brain.context_fn = self.context
        files.configure(settings)
        registry.load_all()

    def start(self) -> None:
        from senses import eyes
        from hands import win
        win.remember_otto_window()
        self.apps.refresh_in_background()
        eyes.start()
        self.router.load(say=self.say)

    # ------------------------------------------------------------------------------------------
    def handle(self, text: str, heard_conf: float | None = None) -> Reply:
        t0 = time.perf_counter()
        self.turn_deadline = time.monotonic() + 45
        self.brain.deadline = self.turn_deadline
        self.trace = {"text": text}
        if isinstance(getattr(self.brain, "usage", None), list):
            self.brain.usage.clear()             # model calls of this turn only (shown in the details line)
        reply = self._handle(text, heard_conf)
        self._log_turn(reply, t0)
        return reply

    def _log_turn(self, reply: Reply, t0: float) -> None:
        self.trace["ms_total"] = round((time.perf_counter() - t0) * 1000)
        self.trace["reply"] = reply.text
        usage = getattr(self.brain, "usage", None)
        if isinstance(usage, list) and usage:
            self.trace["model_calls"] = [dict(u) for u in usage]
        log.write({"type": "request", **self.trace})
        if self.settings.get("show_details", True) and not reply.details:
            reply.details = self._details_line()
        if reply.text and not self.trace.get("fresh"):
            self.history.append({"you": self.trace.get("understood_as") or self.trace.get("text", ""),
                                 "otto": reply.text, "time": time.time(), "area": self.trace.get("area"),
                                 "tools": (self.trace.get("agent") or {}).get("summary", ""),
                                 "did": bool(self.trace.get("plan") or self.trace.get("answer_by") or self.trace.get("rule"))})

    def _handle(self, text: str, heard_conf: float | None) -> Reply:
        t = guards.clean(text)
        if not t:
            return Reply("")
        t, _ = guards.strip_wake(t)
        self.trace["text"] = t
        lead = re.match(r'(?:in|on)\s+([\w .]+?),?\s+(?:(?:can|could|would) you\s+(?:please\s+)?)?(.+?)[.!?]*$', t, re.I)
        if lead and self.apps is not None and self.apps.match_exact(' '.join(lead[1].lower().split())):
            t = f'{lead[2]} in {lead[1]}'
            self.trace['understood_as'] = t
        if guards.filler_only(t):
            self.trace['guard'] = 'filler_only'
            return Reply('')
        if re.fullmatch(r"how do you know (?:it is|it's|its) (?:tonight|night|morning|afternoon|evening)[?.!]*", t, re.I):
            return Reply("Your PC's local time is in my context, but that was just a greeting.")

        # "save that", "no" and "cancel" are fixed phrases that can't approve anything risky, so a quiet or
        # short recording of them is still accepted. A mumbled "yes" is NOT: it could approve closing an app.
        # Never for a question that approves something risky: there only a clearly heard plain yes counts.
        approving = bool(self.pending and self.pending.kind in self.APPROVALS)
        fixed_phrase = bool((guards.memory_command(t) and not approving) or guards.reply_kind(t) == 'no'
                            or guards.is_cancel(t) or self._names_an_option(t))
        if (self.pending and heard_conf is not None and not fixed_phrase
                and heard_conf < float(self.settings.get('whisper', {}).get('misheard_below', -0.9))):
            if self.pending.kind == "heard":           # "did you say ...?" and still unclear: let it go (20 Nov)
                self.pending = None
                return Reply("Sorry, I didn't catch that.")
            return Reply('I did not catch that clearly. Please repeat your answer.')
        if self.pending and time.time() < self.pending.expires:
            r = self._answer_pending(t)
            if r is not None:
                return r
        elif self.pending and self.pending.kind == "rephrase":
            self.rephrase_of = None
        if self.pending and self.pending.task:
            self.pending.task.cancel.set()
        self.pending = None
        # Only a bare yes/no with nothing waiting gets this; "Yeah, can you play that?" is a request (20 Nov voice).
        if guards.exact_yes(t) or guards._simple(t) in guards.NO:
            return Reply('There is no current question to answer. Please tell me what to do.')

        # A full corrected command stands alone; don't ask the model to invent its target.
        corrected = re.sub(r"^(?:no[, ]+|actually[, ]+|i meant[, ]+)", "", t, flags=re.I)
        explicit_correction = corrected != t and bool(re.match(
            r"(?:(?:(?:can|could|would) you|i (?:want|need) you to)\s+)?(?:play|open|set|find|pause|google|search)\b", corrected, re.I))
        if explicit_correction:
            self.rephrase_of = None
            t = corrected
            self.trace["understood_as"] = t
        from core.audio_context import is_followup
        if is_followup(details._t(t)):
            from hands import media
            resolved = self.volume_context.resolve(details._t(t), 'simulation' if self.dry_run else media.endpoint_id())
            if resolved:
                t = resolved
                self.trace['understood_as'] = t
        elif 'volume' not in t.casefold() and not re.search(r'\b(?:louder|quieter)\b', t, re.I):
            self.volume_context.clear()

        misheard = float(self.settings.get("whisper", {}).get("misheard_below", -0.9))
        if heard_conf is not None and heard_conf < misheard:
            self.trace["misheard"] = round(heard_conf, 2)
            self._set_pending("heard", text=t)
            return Reply(f"Sorry, did you say \"{t}\"?")
        return self._process(t)

    # ------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------
    def _set_pending(self, kind: str, **kw) -> None:
        timeout = float(self.settings.get("zones", {}).get("clarify_timeout_s", 30))
        if kind in ("agent_ask", "agent_confirm"):
            timeout = max(timeout, 120)        # reading the question and typing an answer takes longer than a yes/no
        if kw.get('plan'):
            kw['plan'] = deepcopy(kw['plan'])
            kw['scope'] = plan_scope(kw['plan'].steps)
        if kw.get('task'):
            kw['revision'] = kw['task'].revision
        self.pending = Pending(kind, expires=time.time() + timeout, **kw)

    def _answer_pending(self, t: str) -> Reply | None:
        if self._FRESH.match(t):
            self.pending = None                  # "new topic" is never an answer to the question
            return None
        p = self.pending
        kind = guards.reply_kind(t)
        self.trace["answering"] = p.kind
        if p.kind == 'audio_pick':
            self.pending = None
            match = re.fullmatch(r'(?:option |number )?(\d+)[.!]?', t, re.I)
            if match and 1 <= int(match[1]) <= len(p.files):
                endpoint, label = p.files[int(match[1])-1]
                plan = planner.Plan([{'do':'set_audio_output_id', 'with':{'device':endpoint}}], 'builtin')
                return self._run(plan, None, f'Select audio output {label}')
            return None
        if guards.is_cancel(t) and p.kind != "rephrase":
            if p.task:
                p.task.cancel.set()
            self.pending = None
            return Reply("Okay, cancelled.")

        if p.kind in self.APPROVALS and kind == "yes" and not guards.exact_yes(t):
            # "okay stop", "ok cancel", "yeah wait": not a clear yes, so nothing is approved; the question stays.
            p.expires = time.time() + 60
            return Reply('Please answer just "yes" or "no".')

        if p.kind == "agent_confirm":
            self.pending = None
            if kind not in ("yes", "no"):
                # Something else: a new request, and the waiting step is dropped. Mark it in the conversation,
                # or Qwen sees an unanswered "should I send?" and carries it out with the next request.
                if self.history and self.history[-1].get("otto", "").startswith("Just checking"):
                    self.history[-1]["cancelled"] = True
                return None
            return self._agent_resume(p, yes=(kind == "yes"))

        if p.kind == "agent_ask":
            self.pending = None
            if not self._answers_question(t, kind, p):
                # A new request, not an answer (11 Nov: "can you click the calm down video?" was taken as the
                # answer six times over). The question is dropped and marked unanswered.
                if self.history and self.history[-1].get("you") == p.text:
                    self.history[-1]["cancelled"] = True
                return None
            return self._agent_resume(p, answer=t)

        if p.kind == "heard":
            self.pending = None
            if kind == "yes":
                return self._process(p.text)
            if kind == "no":
                return Reply("Sorry, what did you say?")
            return None

        if p.kind == "confirm_area":
            if kind == "yes":
                self.pending = None
                self._learn(p.text, p.area, p.intent.action if p.intent else "", "confirmed")
                return self._do_area(p.text, p.area, intent=p.intent, via="confirmed")
            if kind == "no":
                self._set_pending("rephrase", text=p.text)
                self.rephrase_of = p.text
                return Reply("Okay. What did you want me to do?")
            self.rephrase_of = p.text      # they answered with a clearer request
            self.pending = None
            return None

        if p.kind == "confirm_plan":
            self.pending = None
            if kind == "yes":
                if (not p.task or p.task.cancel.is_set() or p.task.revision != p.revision or p.scope != plan_scope(p.plan.steps)):
                    return Reply('That plan changed or expired. Please ask again.')
                return self._run(p.plan, p.intent, p.text, confirmed=True, task=p.task)
            if p.task:
                p.task.cancel.set()
            if kind == "no":
                return Reply("Okay, I won't.")
            return None

        if p.kind == "confirm_forget":
            self.pending = None
            if kind == "yes":
                return self._forget_now()
            return Reply("Okay, I'll keep it.") if kind == "no" else None

        if p.kind == "pick":
            named = re.search(r"(?:it'?s|its|the one|it is|one)?\s*(?:called|named)\s+(?P<n>.+)$", t, re.I)
            if named:
                self.pending = None
                intent = Intent("files", "find", {"query": named.group("n").strip(" .\"'"), "first": False})
                self.trace["understood_as"] = f"find a file called {intent.params['query']}"
                return self._run(planner.make_plan(intent), intent, t)
            m = re.search(r"\b(\d+|first|second|third|fourth|fifth|last)\b", t.lower())
            if m and len(t.split()) <= 4:
                words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": len(p.files)}
                n = int(m.group(1)) if m.group(1).isdigit() else words[m.group(1)]
                if 1 <= n <= len(p.files):
                    self.pending = None
                    plan = planner.Plan([{"do": "open_path", "with": {"path": p.files[n - 1]}}], "builtin")
                    return self._run(plan, p.intent, p.text)
            self.pending = None
            return None

        if p.kind == "rephrase":
            self.rephrase_of = p.text
            self.pending = None
            return None
        return None

    # ------------------------------------------------------------------------------------------
    def _do_area(self, t: str, area: str, intent: Intent | None = None, via: str = "laya") -> Reply:
        self.trace["via"] = via
        intent = intent or details.by_rules(area, t, self.apps)
        if not intent:
            return self._agent(t)
        self.trace["intent"] = {"area": intent.area, "action": intent.action, "params": intent.params,
                                "by": intent.source}
        if intent.compose:
            try:
                r = self.brain.ask("answer", f"{intent.compose}. Plain text only, no title, no preamble.")
                intent.params["text"] = r.text
                self.trace["composed_by"] = r.model
            except NoBrainAvailable:
                return Reply("I can't reach a brain to write that right now.")
        plan = planner.make_plan(intent)
        if not plan.steps and not plan.error:
            return self._agent(t)              # no built-in steps: the agent works it out, with its safety checks
        self.trace["plan"] = {"source": plan.source, "steps": plan.steps}
        if plan.error:
            return self._finish(Reply(plan.error), area, False)
        return self._run(plan, intent, t)

    def _run(self, plan: planner.Plan, intent: Intent | None, t: str, confirmed: bool = False, task=None) -> Reply:
        from core.tasks import Task, Step, TaskStatus
        self.active_task = task or Task(t, [Step(s.get('id', f's{i}'), s['do'], deepcopy(s.get('with', {})))
                                           for i, s in enumerate(plan.steps)], mode='dry_run' if self.dry_run else 'live')
        if task is None and self.turn_deadline:
            self.active_task.active_seconds = max(0, 45 - (self.turn_deadline - time.monotonic()))
        self.active_task.deadline_at = min(self.turn_deadline or time.monotonic() + 45,
                                          time.monotonic() + max(0, 45 - self.active_task.active_seconds))
        try:
            res = safety.run_plan(plan.steps, confirmed=confirmed, dry_run=self.dry_run, why=t,
                                  task=self.active_task, progress=self.progress)
        except safety.NeedsConfirm as e:
            self.active_task.transition(TaskStatus.WAITING_INPUT)
            self._set_pending('confirm_plan', text=t, intent=intent, plan=plan, task=self.active_task)
            return Reply(f'Just checking: should I {e}?')
        finally:
            if self.active_task:
                self.action_context.record(self.active_task)
            self.active_task = None
            from hands import indicator
            indicator.hide()
        self.trace['outcome_status'] = res.data.get('outcome_status')
        if intent and intent.action in {'get_volume', 'set_volume', 'volume_up', 'volume_down'}:
            from hands import media
            if res.ok or (self.dry_run and res.data.get('outcome_status') == 'simulated'):
                self.volume_context.bind('simulation' if self.dry_run else media.endpoint_id())
        self.rephrase_of = None

        meant = res.data.get('did_you_mean')
        if meant and not res.ok:
            self._set_pending('confirm_area', text=meant['text'], area=meant['area'],
                              intent=Intent(meant['area'], meant['action'], dict(meant['params'])))
            return Reply(res.say)
        found = res.data.get("files")
        if res.data.get('audio_candidates'):
            self._set_pending('audio_pick', text=t, files=res.data['audio_candidates'])
            return Reply(res.say)
        if found is not None and plan.steps and plan.steps[0]["do"] == "find_files":
            if intent and intent.action == "open" and found and (intent.params.get("first") or len(found) == 1):
                return self._run(planner.Plan([{"do": "open_path", "with": {"path": found[0]}}], "builtin"),
                                 intent, t)
            if found:
                self._set_pending("pick", text=t, intent=intent, files=found)
                return self._finish(Reply(res.say, speak=f"I found {len(found)} files. They're on screen; "
                                                             "say a number to open one."), intent.area if intent else "files", True)

        if res.data.get("offer_liked"):
            self._set_pending("confirm_area", text="play my liked songs", area="media",
                              intent=Intent("media", "play_liked"))
            res.say = "Nothing is loaded in Spotify. Want me to play your Liked Songs?"
        text = res.say
        used = [step.get('with', {}).get('app') for step in plan.steps if step.get('with', {}).get('app')]
        if used and not self.dry_run:
            self.last_app = (res.data.get('app') or used[-1], time.time())
        self.last = {"text": t, "intent": intent, "plan": plan, "ok": res.ok, 'task_id': res.data.get('task_id')}
        return self._finish(Reply(text), intent.area if intent else "", res.ok)

    def _finish(self, reply: Reply, area: str, ok: bool) -> Reply:
        """After a request is handled: learn from a clarified rephrase."""
        if ok and self.rephrase_of and area and area not in ("unsure",):
            # Only learn "otto, valorant" = apps from "can you open valorant" if they share a real word,
            # so an unrelated new request doesn't teach Laya something wrong.
            if _shared_words(self.rephrase_of, self.trace.get("text", "")):
                self._learn(self.rephrase_of, area, "", "clarified")
            self.rephrase_of = None
        if self.last is None or self.last.get("text") != self.trace.get("text"):
            if area in ("chitchat", "question", "screen"):
                self.last = {"text": self.trace.get("text", ""), "intent": Intent(area, area), "plan": None, "ok": ok}
        return reply

    # ------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------
    def _learn(self, text: str, area: str, action: str, source: str) -> None:
        if learning.add_example(text, area, action, source):
            self.trace.setdefault("learned", []).append({"text": text, "area": area})
            self.router.note_new_example(say=self.say)

    def _memory(self, cmd: str) -> Reply:
        self.trace["memory"] = cmd
        if not self.last:
            return Reply("There's nothing to save yet. Ask me to do something first.")
        last = self.last
        i: Intent = last["intent"]
        if last.get("agent") is not None:
            return self._memory_agent(cmd, last)
        if cmd == "save":
            if not last["ok"]:
                return Reply("The last thing didn't work, so I won't save it. Want to try again?")
            if i is None:
                # Multi-step, screen-control (visual) and audio-output tasks have no single area/action, and we
                # must never invent a label for Laya to learn. Learning these is planned with any-app control (R7).
                self.trace["memory"] = "save_unsupported"
                return Reply("I can't save that kind of task yet; I can only save single requests for now.")
            self._learn(last["text"], i.area, i.action, "saved")
            return Reply("Got it, I'll remember that's what you meant.")
        # forget
        self._set_pending("confirm_forget")
        return Reply(f"Forget what I learned from \"{last['text']}\"?")

    def _forget_now(self) -> Reply:
        last = self.last or {}
        learning.remove_example(last.get("text", ""))
        if last.get("agent") is not None:
            from core import examples
            examples.forget(last.get("text", ""))
        self.last = None
        return Reply("Forgotten.")

    # ------------------------------------------------------------------------------------------
    # The new core (setting core.agent): a whole-sentence fast path, otherwise the agent loop

    def _agent_deadline(self) -> None:
        """The agent has its own time limit (90 s), not the 45 s of an ordinary turn."""
        from core import agent
        self.turn_deadline = time.monotonic() + agent.MAX_SECONDS + 5
        self.brain.deadline = self.turn_deadline

    def _process(self, t: str) -> Reply:
        if self._FRESH.match(t):
            self.history.clear()
            self.pending = None
            self.trace["fresh"] = True
            return Reply("Okay, fresh start.")
        mem = guards.memory_command(t)
        if mem:
            return self._memory(mem)
        if guards.is_gibberish(t, self.apps.known_words()):
            self.trace["guard"] = "gibberish"
            return Reply("Sorry, I didn't catch that.")
        closer = CLOSERS.get(guards._simple(t))
        if closer:
            self.trace["answer_by"] = "local"
            return Reply(closer)
        quick = answers.whole_local_answer(t)        # time, date, maths: no model needed
        if quick:
            self.trace["answer_by"] = "local"
            return self._finish(Reply(quick), "question", True)
        # Background words ("in the background") are left out only for the media rules; Google, files and the agent
        # get the whole sentence ("google how to run a script in the background").
        bare, background = details.background(t)
        if background:
            self.trace["background"] = True
        intent = details.background_video(bare) if background else None   # a YouTube video, no screen needed
        intent = intent or details.whole_command(t)       # door 1: unmistakable commands ("pause", "volume 30")
        if intent is None:
            # door 2: Laya is sure of the area AND that area's rule covers the whole sentence
            p = self.router.predict(t)
            zone = self.router.zone(p["prob"])
            self.trace.update(area=p["area"], prob=round(p["prob"], 3), zone=zone, laya_ms=round(p["ms"]),
                              top=[(a, round(x, 2)) for a, x in p["top"]])
            if zone == "high":
                intent = details.whole(p["area"], bare if p["area"] == "media" else t, self.apps)
        if intent is not None:
            self.trace["rule"] = "whole_sentence"
            return self._do_area(t, intent.area, intent=intent, via="fast")
        return self._agent(t)

    APPROVALS = ("agent_confirm", "confirm_plan", "confirm_forget")    # a yes here lets something risky happen

    def _names_an_option(self, t: str) -> bool:
        """One of the choices Otto just offered ("AirPods" for "Speakers or AirPods?"). Short answers are often heard
        with low confidence (19 Nov: "AirPods" at -1.04 was refused), but picking an offered option is safe: it is
        not a yes to anything risky, and a wrong pick still has to match an option."""
        p = self.pending
        if not p or p.kind != "agent_ask":
            return False
        said = " ".join(re.findall(r"[a-z0-9]+", t.lower()))
        options = [" ".join(re.findall(r"[a-z0-9]+", str(o).lower())) for o in (p.agent or {}).get("options", [])]
        # Exactly one option: "speakers" with "USB speakers" and "monitor speakers" offered is not an answer.
        return bool(said) and sum(1 for o in options if o and (said == o or re.search(rf"\b{re.escape(said)}\b", o))) == 1

    _NEW_REQUEST = re.compile(r"^(?:you\b|please\b|open|close|play|search|google|type|click|press|send|reply|"
                              r"what|who|where|when|why|how)\b|\b(?:can|could|would|will) you\b", re.I)

    def _answers_question(self, t: str, kind: str, p) -> bool:
        """Is this the answer to Otto's question, or a new request? Yes/no, one of the offered options, or a short
        reply that doesn't read like a new request counts as the answer."""
        if kind in ("yes", "no"):
            return True
        low = t.lower().strip(" .!?")
        options = [o.lower() for o in (p.agent or {}).get("options", []) if o]
        if any(o in low or low in o for o in options if len(o) > 1):
            return True
        return len(low.split()) <= 6 and not self._NEW_REQUEST.search(low)

    CONVERSATION_GAP = 180         # seconds of quiet after which a new request starts a new conversation
    _FRESH = re.compile(r"^(?:new topic|start over|start again|fresh start|new conversation|"
                        r"forget (?:this|the|our) conversation)[.!]*$", re.I)
    _CORRECTION = re.compile(r"^(?:no+\b|nope|wrong|wait\b|you (?:did ?n[o']?t|didn't|forgot|missed)|"
                             r"that'?s (?:wrong|not)|not (?:that|this|what)|try again|again\b)", re.I)
    _POINTS_BACK = re.compile(r"\b(?:open|type|send|put|paste|play|close|save|move|copy|show|click|press|reply|"
                              r"share|write|search|find|do)\s+(?:it|that|this|them|those)\b", re.I)
    _PLACE_WORD = re.compile(r"\b(?:open|launch|start|close|switch to|go to|in|on|into|from)\s+(?:my |the )?", re.I)

    def _conversation(self, t: str = "") -> list[dict]:
        """What the new request continues, as one note for the agent; [] when it starts a new conversation.
        A new conversation starts after 3 minutes of quiet, or when the request names its own app or site
        ("what is on my discord", "open youtube and ...") and doesn't refer back ("it", "that", "no, ...")."""
        chain, later = [], time.time()
        for h in reversed(list(self.history)[-6:]):
            if later - h.get("time", 0) > self.CONVERSATION_GAP:
                break
            chain.insert(0, h)
            later = h.get("time", 0)
        if not chain or (t and self._new_topic(t)):
            return []
        lines = []
        for h in chain:
            otto = h.get("otto", "")
            if h.get("cancelled"):
                otto += " (the user moved on without answering: it was NOT done)"
            lines.append(f"- User: {h.get('you', '')}\n  Otto: {otto}")
        return [{"role": "user", "content": EARLIER + "\n".join(lines)}]

    def _new_topic(self, t: str) -> bool:
        if self._FOLLOW.match(t) or self._CORRECTION.match(t) or self._POINTS_BACK.search(t):
            return False
        return self._names_place(t)

    def _names_place(self, t: str) -> bool:
        """Does the request name an app or website to work in ("on my discord", "open youtube")?"""
        from hands import web
        names = getattr(self, "_place_names", None)
        if names is None:
            names = {n.lower() for n in getattr(self.apps, "names", lambda: [])()}
            names |= set(getattr(self.apps, "aliases", {}) or {}) | set(web.sites())
            names = self._place_names = sorted((n for n in names if len(n) >= 3), key=len, reverse=True)
        low = t.lower()
        for m in self._PLACE_WORD.finditer(low):
            rest = low[m.end():]
            if any(rest.startswith(n) and (len(rest) == len(n) or not rest[len(n)].isalnum()) for n in names):
                return True
        return False

    def _agent(self, t: str) -> Reply:
        from core import agent, tools
        self._agent_deadline()
        self._hide_indicator()
        ctx = tools.ToolContext(dry_run=self.dry_run, brain=self.brain)
        self.active_task = agent.Stopper("dry" if self.dry_run else "live")   # what Otto's cancel key stops
        try:
            result = agent.run(t, self._conversation(t), self.brain, ctx, stop_after=self.agent_stop_after,
                               stop=self.active_task)
        finally:
            self.active_task = None
        return self._agent_reply(t, result)

    def _agent_resume(self, p: Pending, answer: str | None = None, yes: bool | None = None) -> Reply:
        from core import agent
        self._agent_deadline()
        self.active_task = p.agent.get("stop")
        try:
            result = agent.resume(p.agent, self.brain, answer=answer, yes=yes)
        finally:
            self.active_task = None
        return self._agent_reply(p.text, result)

    def _hide_indicator(self) -> None:
        if self.dry_run:
            return
        try:
            from hands import indicator
            indicator.hide()
        except Exception:
            pass

    def _agent_reply(self, t: str, result) -> Reply:
        from core import agent
        calls = result.calls
        # A step that waited for your yes is listed twice (asked, then run): count it once.
        acting = [c for c in calls if c["tool"] in agent.ACTING and not c.get("asked")]
        first = next((c for c in calls if c["tool"] not in ("done", "ask_user")), None)
        self.trace["agent"] = {
            "route": "loop", "status": result.status, "ok": result.ok, "asked": result.status == "confirm",
            "first": {"tool": first["tool"], "args": first.get("args", {})} if first else None,
            "acting": len(acting), "unsafe": False, "named": agent.named_apps(t),
            "calls": [{"tool": c["tool"], "args": c.get("args", {}), "ok": c.get("ok"), "asked": bool(c.get("asked")),
                       "say": str(c.get("say", ""))[:160]}
                      for c in calls],
            "summary": ", ".join(f"{c['tool']} {' '.join(str(v) for v in c.get('args', {}).values())}".strip()
                                 for c in acting[-4:])[:200]}
        if not any(c["tool"] == "point" and c.get("ok") for c in calls):
            self._hide_indicator()                 # the glow goes; a pointer you asked for stays until next time
        if result.status == "ask":
            self._set_pending("agent_ask", text=t, agent=result.pending)
            missing = [o for o in result.options if o.casefold() not in result.say.casefold()]
            if not missing:
                return Reply(result.say)
            # Spoken and shown plainly: no brackets (user, 20 Nov).
            opts = result.options
            said = ", ".join(opts[:-1]) + f" or {opts[-1]}" if len(opts) > 1 else opts[0]
            return Reply(f"{result.say} You can say {said}.")
        if result.status == "confirm":
            self._set_pending("agent_confirm", text=t, agent=result.pending)
            return Reply(f"Just checking: should I {result.say}?")
        # Saveable only if it really ran (not a dry run), finished, and every step that acted worked.
        saveable = (not self.dry_run and result.status == "done" and result.ok and bool(acting)
                    and all(c.get("ok") for c in acting) and not agent.unverified_save(calls))
        self.last = {"text": t, "intent": None, "plan": None, "ok": saveable,
                     "agent": [c for c in calls if c.get("ok") and not c.get("asked")]}
        return Reply(result.say or ("Done." if result.ok else ""))

    def _memory_agent(self, cmd: str, last: dict) -> Reply:
        if cmd == "forget":
            self._set_pending("confirm_forget")
            return Reply(f"Forget how I did \"{last['text']}\"?")
        if not last["ok"]:
            return Reply("I couldn't confirm the last thing fully worked, so I won't save it.")
        from core import examples
        if examples.save(last["text"], last["agent"]):
            self.trace["memory"] = "save_example"
            return Reply("Saved. Next time I'll do it the same way.")
        return Reply("There was nothing to save from that.")

    # ------------------------------------------------------------------------------------------
    # Conversation: follow-ups, multi-step requests, and the context every brain call gets
    _FOLLOW = re.compile(r"^(?:it|its|it's|that|this|those|them|the (?:one|other|first|second|third|last)|"
                         r"no,? (?:the|it|i meant|not)|not that|actually|also|instead|same|another|more|less|"
                         r"what about|how about|and (?:what|how|the|also|then)|called|named|i meant|i mean)\b", re.I)


    def context(self) -> dict:
        """What every brain call is told about right now (fills the {placeholders} in the Otto brief)."""
        from senses import eyes
        w = eyes.last_other_window() or {}
        recent = "\n".join(f"- User: {h['you']} / Otto: {h['otto'][:120]}" for h in list(self.history)[-3:]) or "- (none)"
        return {"now": datetime.now().strftime("%A %d %B %Y, %I:%M %p"),
                "window": f"{w.get('title', '')[:80]} ({w.get('exe', '')})" if w else "unknown",
                "recent": recent,
                "apps": ", ".join(sorted(self.apps.names())[:60])}

    # ------------------------------------------------------------------------------------------
    def _details_line(self) -> str:
        tr = self.trace
        bits = [self._speed_line()] if tr.get("ms_total") is not None else []
        if tr.get("guard"):
            bits.append(f"guard: {tr['guard']}")
        if tr.get("answering"):
            bits.append(f"reply to: {tr['answering']}")
        if tr.get("understood_as"):
            bits.append(f"understood as: \"{tr['understood_as']}\"")
        if tr.get("steps") and not tr.get("step"):
            bits.append(f"split into {len(tr['steps'])} steps ({tr.get('split_by')})")
        if tr.get("misheard") is not None:
            bits.append(f"whisper unsure ({tr['misheard']})")
        if tr.get("area"):
            bits.append(f"laya: {tr['area']} {tr['prob']:.0%} -> {tr['zone']} ({tr['laya_ms']} ms)")
        if tr.get("brain_area"):
            bits.append(f"brain guess: {tr['brain_area']} ({tr['brain']})")
        if tr.get("intent"):
            it = tr["intent"]
            bits.append(f"{it['action']} {it['params']} [{it['by']}]")
        if tr.get("plan"):
            bits.append(f"plan: {tr['plan']['source']}")
        for k in ("answer_by", "chat_by", "screen_by", "composed_by"):
            if tr.get(k):
                bits.append(f"{k.split('_')[0]}: {tr[k]}")
        if tr.get("learned"):
            bits.append("learned: " + ", ".join(f"\"{x['text']}\" = {x['area']}" for x in tr["learned"]))
        return " | ".join(bits)

    def _speed_line(self) -> str:
        """How long the turn took and where the time went, e.g. "4.2 s, model: 2 calls (3.9 s), prompt ~3,900
        tokens (read 600)". "read" much smaller than the prompt means Ollama reused the unchanged start."""
        tr = self.trace
        line = f"{tr['ms_total'] / 1000:.1f} s"
        calls = tr.get("model_calls") or []
        if tr.get("rule") or tr.get("answer_by") == "local":
            line += ", quick path"
        if calls:
            failed = [c for c in calls if c.get("failed")]
            calls_ok = [c for c in calls if not c.get("failed")]
            size = max([c.get("prompt_size") or 0 for c in calls_ok] or [0])
            read = [c["prompt_read"] for c in calls_ok if c.get("prompt_read") is not None]
            line += (f", model: {len(calls)} call{'s' if len(calls) > 1 else ''} "
                     f"({sum(c.get('seconds') or 0 for c in calls):.1f} s), prompt ~{size:,} tokens")
            if read:
                reused = any(c.get("reuse_reported") for c in calls_ok)
                line += f" (read {max(read):,}" + ("" if reused else ", reuse not reported") + ")"
            if failed:
                line += f", {len(failed)} failed ({', '.join(sorted({c['failed'] for c in failed}))})"
            line += _rates(calls)
            if any(c.get("thinking") for c in calls):
                line += ", thinking ON"
        return line
