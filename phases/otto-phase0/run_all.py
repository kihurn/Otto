"""Runs every Phase 0 check in order, then writes results/summary.txt for you to send to Claude.

Run:  python run_all.py
      python run_all.py --skip laya,whisper     (skip checks you've already passed)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from otto_check.common import BOLD, RESET, RESULTS_DIR, ROOT, gpu_memory

CHECKS = [
    ("c0re", ["check_c0re.py"]),
    ("laya", ["check_laya.py", "--train"]),
    ("whisper", ["check_whisper.py"]),
    ("websearch", ["check_websearch.py"]),
    ("memory", ["check_memory.py"]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="", help="comma-separated checks to skip")
    args = ap.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    for name, cmd in CHECKS:
        if name in skip:
            continue
        print(f"\n{BOLD}################ {name} ################{RESET}")
        t0 = time.time()
        code = subprocess.call([sys.executable, *cmd], cwd=ROOT)
        if code != 0:
            print(f"\n(the {name} check stopped with an error after {time.time() - t0:.0f}s; "
                  f"the red text above explains it)")

    write_summary()


def write_summary() -> None:
    lines = ["OTTO PHASE 0 SUMMARY", f"Python {sys.version.split()[0]}"]
    mem = gpu_memory()
    if mem:
        lines.append(f"GPU {mem['name']}, driver {mem['driver']}, {mem['total_mb']} MB")
    raw = {}
    for name, _ in CHECKS:
        path = RESULTS_DIR / f"{name}.json"
        if not path.exists():
            lines.append(f"\n[{name}] not run")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        raw[name] = data["numbers"]
        lines.append(f"\n[{name}] ({data['seconds']}s)")
        for c in data["checks"]:
            lines.append(f"  {c['result']:4}  {c['check']}" + (f": {c['detail']}" if c["detail"] else ""))
    lines.append("\n---- numbers ----")
    lines.append(json.dumps(raw, indent=1))
    out = RESULTS_DIR / "summary.txt"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{BOLD}All done. Send Claude the contents of {out.relative_to(ROOT)} "
          f"(it contains no keys).{RESET}")


if __name__ == "__main__":
    main()
