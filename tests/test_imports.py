"""Every import in Otto's own code points at something that exists, including imports inside functions (which
only run on Windows, so the rest of the suite never executes them). Guards the old-core deletion (20 Nov 2026)."""
import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OWN = ("core", "hands", "senses", "connectors", "tools")
FILES = [p for d in OWN for p in (ROOT / d).rglob("*.py")] + [ROOT / "otto.py"]


def _imports():
    for path in FILES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 \
                    and node.module.split(".")[0] in OWN:
                for alias in node.names:
                    yield path.relative_to(ROOT).as_posix(), node.lineno, node.module, alias.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in OWN:
                        yield path.relative_to(ROOT).as_posix(), node.lineno, alias.name, None


@pytest.mark.parametrize("where,line,module,name", sorted(set(_imports())))
def test_import_target_exists(where, line, module, name):
    mod = importlib.import_module(module)
    if name and name != "*":
        assert hasattr(mod, name) or importlib.util.find_spec(f"{module}.{name}"), \
            f"{where}:{line} imports {name} from {module}, which doesn't exist"


def test_all_actions_load_and_otto_imports():
    from hands import registry
    registry.load_all()
    importlib.import_module("otto")
