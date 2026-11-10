"""Make the pip-installed NVIDIA libraries (cuBLAS 12, cuDNN 9) findable on Windows for faster-whisper."""

from __future__ import annotations

import os
import site
from pathlib import Path

_done = [False]


def add_nvidia_dll_dirs() -> list[str]:
    if _done[0] or os.name != "nt":
        return []
    added: list[str] = []
    for p in site.getsitepackages() + [site.getusersitepackages()]:
        root = Path(p) / "nvidia"
        if root.is_dir():
            for dll in root.rglob("*.dll"):
                if str(dll.parent) not in added:
                    added.append(str(dll.parent))
    for folder in added:
        try:
            os.add_dll_directory(folder)
        except (OSError, AttributeError):
            pass
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
    _done[0] = True
    return added
