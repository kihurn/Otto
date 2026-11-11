r"""Settings, folders and secrets.

Otto's own data lives in otto-data/ (created from defaults/ the first time).

Keys come from a .env file, read at start-up, in this order (later ones win):
  1. Windows environment variables (as set up in Phase 0)
  2. C:\Users\<you>\.otto\.env      <- recommended: outside OneDrive, so keys stay on this PC
  3. <Otto folder>\.env                 <- works too, but OneDrive will sync it to the cloud
Otto never writes keys anywhere or prints them.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_ENV = Path.home() / ".otto" / ".env"
PROJECT_ENV = ROOT / ".env"
DEFAULTS = ROOT / "defaults"
DATA = ROOT / "otto-data"
LOGS = DATA / "logs"
NOTES = DATA / "notes"
LAYA_DIR = DATA / "laya"

SETTINGS_FILE = DATA / "settings.json"
EXAMPLES_FILE = DATA / "examples.csv"
TEST_FILE = DATA / "test_set.csv"
RECIPES_FILE = DATA / "recipes.json"
SITES_FILE = DATA / "sites.json"
ALIASES_FILE = DATA / "app_aliases.json"
APPS_CACHE = DATA / "apps_cache.json"

# Files copied from defaults/ into otto-data/ only if they don't exist yet,
# so pasting a newer version of Otto never overwrites your data.
SEED_FILES = ["examples.csv", "test_set.csv", "recipes.json",
              "sites.json", "app_aliases.json", "brief.md", "eval.csv"]
BRIEF_FILE = DATA / "brief.md"


def ensure_data() -> None:
    for d in (DATA, LOGS, NOTES, LAYA_DIR):
        d.mkdir(parents=True, exist_ok=True)
    for name in SEED_FILES:
        target = DATA / name
        if not target.exists() and (DEFAULTS / name).exists():
            shutil.copy(DEFAULTS / name, target)
    if not SETTINGS_FILE.exists():
        # Only your own changes are stored here; everything else comes from defaults/settings.json,
        # so improvements to the defaults reach you automatically.
        save_json(SETTINGS_FILE, {"_version": SETTINGS_VERSION})


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


SETTINGS_VERSION = 3


def _migrate(mine: dict) -> dict:
    """Small one-off updates to your settings file when Otto changes a default you never touched."""
    if mine.get("_version", 1) < 2:
        vo = mine.get("voice_out", {})
        if vo.get("speed") == 1.0:          # 1.1: slightly faster speech by default
            vo["speed"] = 1.15
        mine["_version"] = 2
        save_json(SETTINGS_FILE, mine)
    if mine.get("_version", 1) < 3:
        # Gemma 4 cloud is no longer free: take it out of your model lists. A list that ends up empty is
        # removed, so the default (local Qwen) applies.
        brains = mine.get("brains")
        if isinstance(brains, dict):
            for job, chain in list(brains.items()):
                if isinstance(chain, list):
                    kept = [m for m in chain if not str(m).startswith("gemma4:")]
                    if kept:
                        brains[job] = kept
                    else:
                        del brains[job]
            if not brains:
                del mine["brains"]
        mine["_version"] = 3
        save_json(SETTINGS_FILE, mine)
    return mine


def load_settings() -> dict:
    """Your settings on top of the defaults, so new options appear automatically."""
    base = json.loads((DEFAULTS / "settings.json").read_text(encoding="utf-8"))
    if SETTINGS_FILE.exists():
        try:
            mine = _migrate(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            return _merge(base, mine)
        except json.JSONDecodeError as e:
            print(f"  ! otto-data/settings.json has a mistake ({e}); using the defaults for now.")
    return base


def get_setting(settings: dict, path: str):
    node = settings
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_setting(path: str, value, settings: dict | None = None) -> None:
    """Change one setting (e.g. 'voice_out.speed') in otto-data/settings.json, and in the live settings."""
    mine = load_json(SETTINGS_FILE, {})
    for target in (mine, settings) if settings is not None else (mine,):
        node = target
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    mine.setdefault("_version", SETTINGS_VERSION)
    save_json(SETTINGS_FILE, mine)


def parse_value(text: str):
    """'1.2' -> 1.2, 'true' -> True, 'null' -> None, '[...]' -> list, anything else -> string."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def c0re_key() -> str | None:
    return (os.environ.get("OTTO_C0RE_KEY") or "").strip() or None


def ollama_key() -> str | None:
    return (os.environ.get("OLLAMA_API_KEY") or "").strip() or None


def _read_env_file(path: Path) -> dict[str, str]:
    """KEY=value lines. Blank lines and # comments are ignored; quotes around values are optional."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (FileNotFoundError, OSError):
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key:
            values[key] = value
    return values


def load_env() -> list[str]:
    """Load the .env files into this process's environment. Returns which files were used."""
    used = []
    for path in (HOME_ENV, PROJECT_ENV):
        values = _read_env_file(path)
        for k, v in values.items():
            if v:
                os.environ[k] = v
        if values:
            used.append(str(path))
    return used


ENV_FILES_USED = load_env()


def spotify_client_id() -> str | None:
    return (os.environ.get("OTTO_SPOTIFY_CLIENT_ID") or "").strip() or None
