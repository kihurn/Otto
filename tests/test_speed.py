"""Speed batch (19 Nov): prompt order, model usage numbers, the time line in the log, more quick-path phrasings."""
from core import config, details
from core.brain import Brain


def _brain(tmp_path, monkeypatch, text):
    brief = tmp_path / "brief.md"
    brief.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "BRIEF_FILE", brief)
    b = Brain({"brains": {"decide": ["m"]}, "brain": {"num_ctx": 16384}})
    b.context_fn = lambda: {"now": "Thu 19:55", "window": "Spotify", "recent": "you: hi", "apps": "Chrome"}
    return b


def test_brief_splits_fixed_from_live(tmp_path, monkeypatch):
    b = _brain(tmp_path, monkeypatch, "Rules here.\nApps: {apps}\n\nRight now: {now}. Last: {window}.\nRecent:\n{recent}\n")
    fixed, live = b.brief_parts()
    assert fixed == "Rules here.\nApps: Chrome" and live.startswith("Right now: Thu 19:55") and "you: hi" in live


def test_agent_prompt_puts_the_live_details_last(tmp_path, monkeypatch):
    from core import agent
    b = _brain(tmp_path, monkeypatch, "Rules here.\nRight now: {now}.")
    prompt = agent.system_prompt(b, "open chrome")
    assert prompt.startswith("Rules here.") and prompt.rstrip().endswith("Right now: Thu 19:55.")


def test_ask_also_ends_with_the_live_details(tmp_path, monkeypatch):
    b = _brain(tmp_path, monkeypatch, "Rules here.\nRight now: {now}.")
    sent = {}
    monkeypatch.setattr(b, "_post", lambda path, body, timeout: sent.update(body) or {
        "message": {"content": "hi", "thinking": "hmm"}, "prompt_eval_count": 12, "eval_count": 3})
    b.ask("chat", "hello", system="Job: chat.")
    system = sent["messages"][0]["content"]
    assert system.index("Rules here.") < system.index("Job: chat.") < system.index("Right now")
    assert "think" not in sent                            # only sent when brain.think is set
    u = b.usage[-1]
    assert u["prompt_read"] == 12 and u["reply_tokens"] == 3 and u["thinking"] == 3 and u["prompt_size"] > 0


def test_thinking_can_be_switched_off(tmp_path, monkeypatch):
    b = _brain(tmp_path, monkeypatch, "Rules.")
    b.settings["brain"]["think"] = False
    sent = {}
    monkeypatch.setattr(b, "_post", lambda path, body, timeout: sent.update(body) or {"message": {"content": "x"}})
    b.ask("chat", "hello")
    assert sent["think"] is False


def test_speed_line():
    from core.pipeline import Otto
    o = Otto.__new__(Otto)
    o.trace = {"ms_total": 4210, "model_calls": [
        {"seconds": 2.0, "prompt_size": 3900, "prompt_read": 3900, "thinking": 0},
        {"seconds": 1.5, "prompt_size": 4100, "prompt_read": 250, "thinking": 0}]}
    assert o._speed_line() == "4.2 s, model: 2 calls (3.5 s), prompt ~4,100 tokens (read 3,900, reuse not reported)"
    o.trace["model_calls"][1]["reuse_reported"] = True
    o.trace["model_calls"].append({"seconds": 12.0, "failed": "timeout"})
    assert o._speed_line() == ("4.2 s, model: 3 calls (15.5 s), prompt ~4,100 tokens (read 3,900), "
                               "1 failed (timeout)")
    o.trace = {"ms_total": 90, "rule": "whole_sentence"}
    assert o._speed_line() == "0.1 s, quick path"


def test_spoken_volume_phrasings_take_the_quick_path():
    for said, level in [("Now can you increase the volume to 80?", 80), ("turn the volume up to 80", 80),
                        ("lower the volume to 20", 20), ("hey, set volume to 30", 30),
                        ("okay so turn up the volume to 75 percent", 75)]:
        intent = details.whole_command(said)
        assert intent and intent.action == "set_volume" and intent.params["level"] == level, said
    assert details.whole_command("turn the volume up to 80 and play lofi") is None
    assert details._t("now playing") == "now playing"


def test_think_setting_is_dropped_for_a_model_without_thinking(tmp_path, monkeypatch):
    from core.brain import BrainError
    b = _brain(tmp_path, monkeypatch, "Rules.")
    b.settings["brain"]["think"] = False
    sent = []

    def post(path, body, timeout):
        sent.append(dict(body))
        if "think" in body:
            raise BrainError("http_400", '"qwen3-vl:8b-instruct" does not support thinking')
        return {"message": {"content": "ok"}}
    monkeypatch.setattr(b, "_post", post)
    assert b.ask("chat", "hello").text == "ok" and "think" in sent[0] and "think" not in sent[1]


def test_reused_prompt_start_is_not_counted_as_read():
    from core.brain import _new_tokens
    assert _new_tokens({"prompt_eval_count": 79, "prompt_eval_cached_count": 74}) == 5
    assert _new_tokens({"prompt_eval_count": 79, "context_cache_size": 4096}) == 79      # not a prompt count
    assert _new_tokens({"prompt_eval_count": 79}) == 79
    assert _new_tokens({}) is None


def test_eval_counts_save_as_keys_only_for_a_save_request():
    from core.evaluate import Decision, EvalCase, judge
    assert judge(EvalCase("save my notes", first_tool="keys"), Decision("loop", "save", {}, False))[0]
    assert not judge(EvalCase("open a new tab", first_tool="keys"), Decision("loop", "save", {}, False))[0]
