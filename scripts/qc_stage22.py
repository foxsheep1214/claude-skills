#!/usr/bin/env python3
"""QC gate for Stage 2.2 chunk-analysis responses — detects placeholder/thin analysis.

Generalized from the ad-hoc script that caught the Skolnik incident (2026-07-07):
a driving sub-agent chained past the L4 cap (delegate-mode.md, max 2 handoffs per
agent) without ever exiting, context accumulated past its practical ceiling, and
Stage 2.2 responses degraded into placeholder concepts (e.g. "Radar Handbook
Content" instead of real topic names). Run this after every Stage 2.2 response —
ideally before deciding whether to chain the next handoff or hand back to the
parent — to catch degradation at the cheapest point, before it propagates into
Stage 2.4's generated pages.

Usage:
    python3 scripts/qc_stage22.py                       # scans IMPROVED_WIKI_ROOT (or cwd)
    IMPROVED_WIKI_ROOT=/path/to/project python3 scripts/qc_stage22.py
"""
import os
import re
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from _paths import detect_runtime_dir

MIN_CONCEPTS = 5
MIN_BYTES = 3000
PLACEHOLDER = re.compile(
    r"(?i)chunk \d|handbook content|reference material|technical content|"
    r"book content|comprehensive.*content"
)


def check(txt_file: Path) -> tuple[bool, str]:
    text = txt_file.read_text(encoding="utf-8", errors="replace")
    size = len(text)
    concepts = re.findall(r"^\s*-\s*name:\s*[\"']?(.+?)[\"']?\s*$", text, re.MULTILINE)
    placeholders = [c for c in concepts if PLACEHOLDER.search(c)]
    if size < MIN_BYTES:
        return False, f"size {size} < {MIN_BYTES}"
    if len(concepts) < MIN_CONCEPTS:
        return False, f"only {len(concepts)} concepts (< {MIN_CONCEPTS})"
    if placeholders:
        return False, f"placeholder names: {placeholders[:3]}"
    return True, f"OK ({len(concepts)} concepts, {size} bytes)"


def main() -> int:
    project_root = Path(os.environ.get("IMPROVED_WIKI_ROOT", os.getcwd()))
    runtime = detect_runtime_dir(project_root)
    conv_root = runtime / "conversation"
    if not conv_root.is_dir():
        print(f"No conversation dir at {conv_root}")
        return 0

    bad = []
    total = 0
    for conv_dir in sorted(conv_root.iterdir()):
        targets = sorted(
            conv_dir.glob("Stage-2-2-Chunk-*.txt"),
            key=lambda p: int(re.search(r"Chunk-(\d+)", p.name).group(1)),
        )
        if not targets:
            continue
        print(f"=== {conv_dir.name} ===")
        for f in targets:
            total += 1
            n = re.search(r"Chunk-(\d+)", f.name).group(1)
            ok, msg = check(f)
            status = "✓" if ok else "✗"
            print(f"  chunk {n}: {status} {msg}")
            if not ok:
                bad.append((conv_dir.name, f, msg))

    print(f"\n{total} responses, {len(bad)} bad")
    if bad:
        print("Bad chunks (delete to force redo):")
        for conv_name, f, msg in bad:
            print(f"  rm {f}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
