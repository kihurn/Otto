"""Shared test setup. Tests run on any OS (no Windows needed): Laya, the brain and the Hands are faked,
and everything runs in dry-run. otto-data is redirected to a temporary folder."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAKE_APPS = ["Spotify", "Discord", "Google Chrome", "VALORANT", "Steam", "Visual Studio Code", "OBS Studio",
             "Calculator", "Settings", "Notepad", "File Explorer", "Microsoft Edge", "Riot Client", "WhatsApp", "Word"]


@pytest.fixture(autouse=True)
def temp_data(tmp_path, monkeypatch):
    from core import config
    data = tmp_path / "otto-data"
    for name, value in {"DATA": data, "LOGS": data / "logs", "NOTES": data / "notes", "LAYA_DIR": data / "laya",
                        "SETTINGS_FILE": data / "settings.json", "EXAMPLES_FILE": data / "examples.csv",
                        "TEST_FILE": data / "test_set.csv", "RECIPES_FILE": data / "recipes.json",
                        "SITES_FILE": data / "sites.json", "ALIASES_FILE": data / "app_aliases.json",
                        "APPS_CACHE": data / "apps_cache.json", "BRIEF_FILE": data / "brief.md"}.items():
        monkeypatch.setattr(config, name, value)
    for mod in ("core.learning", "core.recipes", "core.log", "core.router", "hands.notes", "hands.web", "hands.apps"):
        m = __import__(mod, fromlist=["x"])
        for name in ("EXAMPLES_FILE", "TEST_FILE", "RECIPES_FILE", "LOGS", "LAYA_DIR", "NOTES", "SITES_FILE",
                     "ALIASES_FILE", "APPS_CACHE"):
            if hasattr(m, name):
                monkeypatch.setattr(m, name, getattr(config, name))
    from core import router
    monkeypatch.setattr(router, "CURRENT", config.LAYA_DIR / "current")
    config.ensure_data()
    from hands import apps
    monkeypatch.setattr(apps.INDEX, "apps", [{"name": n, "id": n} for n in FAKE_APPS])
    yield data
