from types import SimpleNamespace

from core import reading
from core.pipeline import Otto


def test_overlap_preserves_repeated_messages_and_rejects_a_gap():
    first = ["Ann: intro", "Lee: OK", "Maya: OK"]
    second = ["Lee: OK", "Maya: OK", "Lee: deadline"]
    assert reading.prepend_overlap(first, second) == ["Ann: intro", *second]
    assert reading.prepend_overlap(["earlier", "different"], second) is None
    assert reading.prepend_overlap(["a", "b"], ["a", "b", "a", "b"]) is None


def test_long_summary_keeps_first_middle_and_last_sections():
    prompts = []

    def ask(job, prompt, **kwargs):
        prompts.append(prompt)
        facts = [word for word in ("first_fact", "middle_fact", "last_fact") if word in prompt]
        return SimpleNamespace(data={"summary": " ".join(facts)})

    content = ("first_fact " + "x" * 5500 + "middle_fact " + "x" * 5500 + "last_fact")
    assert reading.summarize(content, "summarise this article", SimpleNamespace(ask=ask)) == (
        "first_fact middle_fact last_fact")
    assert len(prompts) == 4


def test_pdf_coverage_names_unreadable_pages(monkeypatch, tmp_path):
    import sys
    path = tmp_path / "attachment.pdf"
    path.touch()
    pages = [SimpleNamespace(extract_text=lambda text=text: text) for text in ("first", "", "last")]
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda stream: SimpleNamespace(pages=pages)))
    text, coverage = reading.pdf_pages(path)
    assert text == "Page 1\nfirst\n\nPage 3\nlast"
    assert "read 2 of 3 pages" in coverage and coverage.endswith("2")


def test_summary_refuses_to_substitute_chat_for_pdf(monkeypatch):
    from core import agent_safety
    from hands import win
    monkeypatch.setattr(agent_safety, "back_to_user_window", lambda ctx: None)
    monkeypatch.setattr(win, "foreground", lambda: 1)
    monkeypatch.setattr(win, "window_info", lambda hwnd: {"title": "Group"})
    monkeypatch.setattr(reading.web, "chrome_addresses", lambda **kw: [])
    otto = SimpleNamespace(dry_run=False)
    assert "couldn't verify a local PDF" in Otto._summarize_source(otto, "summarise this PDF", "pdf").text
