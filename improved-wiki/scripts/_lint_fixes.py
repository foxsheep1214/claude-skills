#!/usr/bin/env python3
"""_lint_fixes.py — auto-fixes for structural lint findings.

Faithful port of NashSU ``src/lib/lint-fixes.ts`` (v0.5.1). Three fixes that
``_lint_suggest.run_structural_lint`` surfaces suggestions for but the old
improved-wiki never applied:

  - append_wikilink          — add ``- [[target]]`` under ``## Related``
                               (for orphan / no-outlinks suggestions).
  - rewrite_wikilink_target  — rewrite a broken ``[[broken]]`` link to its
                               suggested target, preserving any ``|alias``.
  - ensure_broken_link_stub  — create a ``type: query`` stub page for a broken
                               link target that has no suggestion, so the link
                               resolves instead of dangling.

Pure string/path logic — no LLM, no I/O except ``ensure_broken_link_stub``
which writes the stub file. ``make_query_slug`` is a port of NashSU
``wiki-filename.ts:makeQuerySlug`` (NFKC + Unicode-aware, keeps CJK).
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

__all__ = [
    "make_query_slug",
    "lint_link_target",
    "has_wikilink_to_target",
    "append_wikilink",
    "rewrite_wikilink_target",
    "stub_relative_path_from_broken_target",
    "stub_title_from_broken_target",
    "ensure_broken_link_stub",
]


# ── slug (port of wiki-filename.ts:makeQuerySlug) ────────────────────────────

_NON_SLUG_RE = re.compile(r"[^\w-]", re.UNICODE)


def make_query_slug(title: str) -> str:
    """Unicode-aware kebab slug. Keeps letters/digits across all scripts
    (Latin, CJK, Cyrillic …) plus ASCII hyphen. NFKC-normalized, lowercased,
    whitespace→hyphen, runs collapsed, trimmed, truncated to 50 chars (by
    codepoint). Falls back to ``"query"`` when nothing usable remains.
    """
    slug = unicodedata.normalize("NFKC", title).strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = _NON_SLUG_RE.sub("", slug)
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    truncated = slug[:50]
    return truncated if truncated else "query"


# ── link target normalization ────────────────────────────────────────────────

def lint_link_target(target: str) -> str:
    """Normalize a wikilink target to a wiki-relative slug form (port of
    lint-fixes.ts:lintLinkTarget). Strips a leading ``wiki/`` and a trailing
    ``.md``, trims whitespace. Also strips surrounding quotes that leak from
    YAML-formatted related fields (e.g. [[concepts/foo"]] or [["concepts/foo"]])."""
    t = target.replace("\\", "/")
    t = re.sub(r"^wiki/", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\.md$", "", t, flags=re.IGNORECASE)
    return t.strip().strip('"').strip("'")


def _normalized_link_target(target: str) -> str:
    return lint_link_target(target).lower()


_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
_WIKILINK_WITH_ALIAS_RE = re.compile(r"\[\[([^\]|]+?)(\|[^\]]+?)?\]\]")


def has_wikilink_to_target(content: str, target: str) -> bool:
    """True if ``content`` already contains a ``[[target]]`` (or
    ``[[target|alias]]``) link to ``target`` (case-insensitive)."""
    normalized = _normalized_link_target(target)
    return any(
        _normalized_link_target(m.group(1)) == normalized
        for m in _WIKILINK_RE.finditer(content)
    )


# ── fix 1: append a wikilink under ## Related ────────────────────────────────

_RELATED_HEADING_RE = re.compile(r"^##\s+Related\s*$", re.IGNORECASE | re.MULTILINE)


def append_wikilink(content: str, target: str) -> str:
    """Append ``- [[target]]`` under a ``## Related`` heading. Creates the
    heading if absent. No-op (returns content unchanged) if a link to target
    already exists."""
    link_target = lint_link_target(target)
    if has_wikilink_to_target(content, link_target):
        return content
    link_line = f"- [[{link_target}]]"
    m = _RELATED_HEADING_RE.search(content)
    if m:
        insert_at = m.end()
        return f"{content[:insert_at]}\n{link_line}{content[insert_at:]}"
    return f"{content.rstrip()}\n\n## Related\n{link_line}\n"


# ── fix 2: rewrite a broken link target ──────────────────────────────────────

def rewrite_wikilink_target(
    content: str,
    broken_target: str,
    suggested_target: str,
) -> str:
    """Rewrite every ``[[broken]]`` (or ``[[broken|alias]]``) link to
    ``[[suggested]]`` (preserving alias). Other links are untouched."""
    broken = _normalized_link_target(broken_target)
    replacement = lint_link_target(suggested_target)

    def _sub(m: re.Match) -> str:
        raw_target = m.group(1)
        alias = m.group(2)
        if _normalized_link_target(raw_target) != broken:
            return m.group(0)
        return f"[[{replacement}{alias}]]" if alias is not None else f"[[{replacement}]]"

    return _WIKILINK_WITH_ALIAS_RE.sub(_sub, content)


# ── fix 3: stub page for an unresolvable broken link ─────────────────────────

def stub_relative_path_from_broken_target(broken_target: str) -> str:
    """Wiki-relative path (``queries/<slug>.md`` or nested) for a stub page
    that would satisfy ``[[broken_target]]``."""
    normalized = lint_link_target(broken_target)
    parts = [make_query_slug(p) for p in normalized.split("/") if p]
    if len(parts) > 1:
        rel = "/".join(parts)
    else:
        rel = f"queries/{parts[0] if parts else 'missing-page'}"
    return f"{rel}.md"


def stub_title_from_broken_target(broken_target: str) -> str:
    name = os.path.basename(lint_link_target(broken_target))
    return re.sub(r"[-_]+", " ", name).strip() or "Missing Page"


def ensure_broken_link_stub(
    project_path: str | Path,
    broken_target: str,
) -> tuple[Path, str, bool]:
    """Create a ``type: query`` stub page for ``broken_target`` if it doesn't
    exist. Returns ``(full_path, relative_path, created)``."""
    relative_path = stub_relative_path_from_broken_target(broken_target)
    full_path = Path(project_path) / "wiki" / relative_path
    if full_path.exists():
        return full_path, relative_path, False
    full_path.parent.mkdir(parents=True, exist_ok=True)
    title = stub_title_from_broken_target(broken_target)
    from time import strftime
    date = strftime("%Y-%m-%d")
    safe_title = title.replace('"', '\\"')
    content = (
        "---\n"
        "type: query\n"
        f'title: "{safe_title}"\n'
        f"created: {date}\n"
        f"updated: {date}\n"
        "tags: [stub, lint]\n"
        "related: []\n"
        "sources: []\n"
        "---\n\n"
        f"# {title}\n\n"
        "Created by Wiki Lint as a placeholder for a missing wikilink target.\n"
    )
    full_path.write_text(content, encoding="utf-8")
    return full_path, relative_path, True
