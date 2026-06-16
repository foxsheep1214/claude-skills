#!/usr/bin/env python3
"""Stage 1 / 1.5 YAML list-prefix repair for minimax M3 output.

Problem: LLM outputs nested list items missing the `- ` prefix under
`key_details:` / `claims:` / `connections_to_existing_wiki:` etc.
`yaml.safe_load()` then fails with
  expected <block end>, but found '<scalar>'

Repair heuristic: walk the YAML line-by-line. When a line is a quoted
scalar indented ≥4 spaces, the previous (already-repaired) line ends
with `:` or begins with `- `, AND the current line does not already
start with `- ` — prepend `- `.

CRITICAL: compare against `fixed_lines[-1]` (the previous repaired line),
NOT `lines[i-1]`. Otherwise context does not propagate: the first
malformed line stays fixed, but its repaired form never influences the
next malformed sibling, and the repair chain breaks.

Usage:
    python3 yaml_list_prefix_fix.py <yaml_file>
    # or import repair_yaml_text() / repair_yaml_file() from a script

Origin: ADL8113 ingest (2026-06-13), Stage 1.5 first attempt produced
14-entity / 16-concept / 10-claim chunk analysis where every list item
under `key_details:` lost its `- ` prefix. The ingest.py retry would
have re-burned API quota; this script repaired the raw response in
place in <1s.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List


def _should_add_dash(stripped: str, prev_repaired: str, indent: int) -> bool:
    """True iff this line is a quoted scalar inside a list and is missing `- `."""
    if indent < 4:
        return False
    if stripped.startswith("- "):
        return False
    # Quoted scalar (single or double quote, both ends)
    is_quoted = (stripped.startswith('"') and stripped.endswith('"') or
                 stripped.startswith("'") and stripped.endswith("'"))
    if not is_quoted:
        return False
    prev_stripped = prev_repaired.lstrip()
    prev_is_list_item = prev_stripped.startswith("- ")
    prev_is_block_key = prev_repaired.rstrip().endswith(":")
    # Either we just saw `key:` (block key) or `- prev_item:` (list item)
    return prev_is_block_key or prev_is_list_item


def repair_yaml_text(yaml_text: str) -> str:
    """Return a repaired copy of yaml_text with missing `- ` prefixes fixed."""
    lines = yaml_text.split("\n")
    fixed: List[str] = []
    for line in lines:
        if fixed:
            prev = fixed[-1]
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if _should_add_dash(stripped, prev, indent):
                line = " " * indent + "- " + stripped
        fixed.append(line)
    return "\n".join(fixed)


def repair_yaml_file(path: Path) -> str:
    """Repair a YAML file in-place and return the repaired text."""
    raw = path.read_text(encoding="utf-8")
    fixed = repair_yaml_text(raw)
    if fixed != raw:
        path.write_text(fixed, encoding="utf-8")
    return fixed


def extract_yaml_block(text: str) -> str:
    """Pull the first ```yaml ... ``` block out of an LLM response."""
    m = re.search(r"```yaml\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Usage: yaml_list_prefix_fix.py <yaml_file>", file=sys.stderr)
        return 2
    p = Path(argv[1])
    if not p.exists():
        print(f"File not found: {p}", file=sys.stderr)
        return 1
    before = p.read_text(encoding="utf-8")
    after = repair_yaml_text(before)
    if before == after:
        print(f"OK: no repairs needed for {p}")
        return 0
    # Count repairs
    before_dash_lines = sum(1 for ln in before.split("\n")
                             if _should_add_dash(ln.lstrip(), "", len(ln) - len(ln.lstrip())))
    after_dash_lines = sum(1 for ln in after.split("\n")
                            if ln.lstrip().startswith("- "))
    p.write_text(after, encoding="utf-8")
    print(f"Repaired {p}: {after.count(chr(10))} lines, "
          f"~{after_dash_lines} dash-prefixed items after")
    # Try to verify parse
    try:
        import yaml  # type: ignore
        yaml.safe_load(after)
        print(f"OK: {p} now parses as valid YAML")
        return 0
    except yaml.YAMLError as e:
        print(f"⚠ {p} still fails yaml.safe_load: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))