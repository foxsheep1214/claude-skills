#!/usr/bin/env python3
"""_lint_domains.py — load the valid-domain set for wiki-lint.

De-hardcodes the domain list that was previously baked into wiki-lint.sh
(a HardwareWiki-specific set leaking into the generic skill — RadarWiki /
自然科学知识库 legitimately use other domains and would get spurious
``invalid-domain`` findings).

Resolution priority:
  1. ``<project>/wiki/domains.md``  — project-level override (per-project
     knowledge base defines its own domain table)
  2. ``<skill>/references/domains.md`` — skill default
  3. ``set()`` — neither parsed → caller treats ``invalid-domain`` as
     lenient (skips that check) rather than guessing.

The markdown table is parsed by taking the first backticked cell of each
``| ... |`` row (the table in domains.md is ``| `slug` | 中文名 | ... |``).
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["load_valid_domains", "parse_domains_md"]

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_DOMAIN_CELL_RE = re.compile(r"`\s*([a-z0-9][a-z0-9_-]*)\s*`", re.IGNORECASE)


def parse_domains_md(text: str) -> set[str]:
    """Parse the first backticked cell of each markdown table row as a slug.

    The domains.md table format is ``| `slug` | 中文名 | ... |``. We take
    only the first backticked cell per row so the description column (which
    may also contain backticked tokens) does not pollute the slug set.
    """
    slugs: set[str] = set()
    for line in text.splitlines():
        if not _TABLE_ROW_RE.match(line):
            continue
        m = _DOMAIN_CELL_RE.search(line)
        if m:
            slugs.add(m.group(1).strip().lower())
    return slugs


def load_valid_domains(project_root: Path, skill_root: Path) -> set[str]:
    """Return the set of valid domain slugs for this project.

    Tries project-level ``wiki/domains.md`` first, then the skill's
    ``references/domains.md``. Returns an empty set if neither yields any
    slug (caller should then skip ``invalid-domain`` checks rather than
    flag every domain as invalid).
    """
    candidates = [
        project_root / "wiki" / "domains.md",
        skill_root / "references" / "domains.md",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        slugs = parse_domains_md(text)
        if slugs:
            return slugs
    return set()
