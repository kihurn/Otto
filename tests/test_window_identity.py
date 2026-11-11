"""Word must resolve to its process, regardless of titles in other apps."""
import pytest
from hands import win, apps


@pytest.mark.parametrize('spoken', ['Word', 'Microsoft Word', 'microsoft   word', 'WINWORD'])
def test_word_ignores_workspace_and_document_titles(monkeypatch, spoken):
    wrong = {'hwnd': 1, 'exe': 'Antigravity.exe', 'title': 'Word'}
    document = {'hwnd': 2, 'exe': 'notepad.exe', 'title': 'notes - Microsoft Word'}
    right = {'hwnd': 3, 'exe': 'WINWORD.EXE', 'title': 'Untitled document'}
    monkeypatch.setattr(win, 'windows', lambda: [wrong, document, right])
    assert win.find_window(spoken) is right


@pytest.mark.parametrize('exe', ['Antigravity.exe', 'notepad.exe', 'chrome.exe', ''])
def test_missing_word_does_not_fall_back_to_a_title(monkeypatch, exe):
    monkeypatch.setattr(win, 'windows', lambda: [{'hwnd': 1, 'exe': exe, 'title': 'Microsoft Word'}])
    assert win.find_window('Word') is None


def test_open_word_launches_word_instead_of_focusing_antigravity(monkeypatch):
    wrong = {'hwnd': 1, 'exe': 'Antigravity.exe', 'title': 'Word'}
    right = {'hwnd': 2, 'exe': 'WINWORD.EXE', 'title': 'Document1 - Word'}
    observed, launched, focused = [wrong], [], []
    monkeypatch.setattr(win, 'IS_WINDOWS', True)
    monkeypatch.setattr(win, 'windows', lambda: observed)
    monkeypatch.setattr(win, 'focus', lambda hwnd: focused.append(hwnd) or True)
    monkeypatch.setattr(apps.time, 'sleep', lambda seconds: None)
    def launch(app):
        launched.append(app['name'])
        observed.append(right)
    monkeypatch.setattr(apps, '_launch', launch)
    assert apps.open_app('Microsoft Word').ok
    assert launched == ['Word'] and focused == [2]
