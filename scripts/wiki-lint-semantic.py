#!/usr/bin/env python3
"""
wiki-lint-semantic.py — LLM-driven semantic lint for a wiki/.

This is improved-wiki's port of NashSU's runSemanticLint() from
src/lib/lint.ts (v0.4.23 L161-299). It scans every page's first 500
chars + frontmatter, sends the concatenated summaries to an LLM, and
parses ---LINT:type|severity|title--- blocks back into findings.

Findings carry type="semantic" (matching NashSU's 4th structural-lint
type), with the raw type (contradiction / stale / missing-page /
suggestion) preserved in the detail string. affectedPages is parsed
from an optional "PAGES: a, b" line in the body.

Output schema (one item per finding):
  {
    "type": "semantic",
    "severity": "warning" | "info",
    "page": "<title from LINT header>",
    "detail": "[<rawType>] <body minus PAGES line>",
    "affectedPages": ["a.md", "b.md"] | undefined,
    "id": "lint-semantic-<n>",
    "createdAt": <epoch ms>
  }

Config (env vars, matching ingest.py):
  IMPROVED_WIKI_ROOT  project root (default: cwd)
  LLM_API_KEY         required
  LLM_BASE_URL        https://api.minimaxi.com (default; script appends
                      /anthropic/v1/messages — see pitfall below)
  LLM_MODEL           MiniMax-M3 (default)

Usage:
  ./wiki-lint-semantic.py              # scan and write lint-semantic.json
  ./wiki-lint-semantic.py --dry-run    # print prompt + summaries, no LLM call
  ./wiki-lint-semantic.py --limit 50   # cap pages sampled (for huge wikis)
  ./wiki-lint-semantic.py --max-tokens 2048  # cap LLM output (default 4096)

Pitfall — LLM_BASE_URL double-path: ingest.py appends /anthropic/v1/messages
internally, so set LLM_BASE_URL to the BARE origin (e.g. https://api.minimaxi.com
NOT https://api.minimaxi.com/anthropic). Same trap as ingest.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ── constants (verbatim from NashSU lint.ts L161-162) ────────────────────────
LINT_BLOCK_REGEX = re.compile(
    r"---LINT:\s*([^\n|]+?)\s*\|\s*([^\n|]+?)\s*\|\s*([^\n-]+?)\s*---\n"
    r"([\s\S]*?)---END LINT---"
)

# NashSU parity: only log.md excluded from semantic lint (lint.ts L188)
ANCHOR_FILES = {"log.md"}
STATE_FILES = {
    "lint-cache.json", "lint.json",
    "ingest-cache.json",
    "ingest-queue.json",
    "ingest-lock",
    "lint-lock", "lint.lock",
    "lint-semantic.json",  # don't lint our own output
}

# Per-page summary size (NashSU: 500 chars)
SUMMARY_CHARS = 500
# Concatenated sample for language detection (NashSU: 2000 chars)
LANG_SAMPLE_CHARS = 2000
# Default max_tokens (NashSU Stage 2 semantic: 4096)
DEFAULT_MAX_TOKENS = 4096


# ── LLM call (verbatim pattern from ingest.py call_llm) ──────────────────────
def call_llm(
    system_prompt: str,
    user_content: str,
    base_url: str,
    model: str,
    api_key: str,
    max_tokens: int,
) -> str:
    """Call the LLM via Anthropic messages protocol. Returns the text content."""
    url = f"{base_url.rstrip('/')}/anthropic/v1/messages"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {e.code}: {err_body[-500:]}")

    content = data.get("content", [])
    if not content:
        raise RuntimeError(f"LLM response has no content: {json.dumps(data)[:500]}")
    text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
    return "".join(text_parts)


# ── language directive (NashSU parity: _language.detect_language port) ───────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from _language import build_language_directive  # noqa: E402 (titles, descriptions, PAGES list) MUST be in English."


# ── core scan ────────────────────────────────────────────────────────────────
def collect_summaries(wiki_dir: Path, limit: Optional[int] = None) -> list[tuple[str, str]]:
    """Returns [(short_path, summary_text), ...]. Excludes anchors + state files.
    Sorts by relative path for determinism (NashSU parity)."""
    out: list[tuple[str, str]] = []
    for path in sorted(wiki_dir.rglob("*.md")):
        rel = path.relative_to(wiki_dir)
        if rel.name in STATE_FILES or rel.name in ANCHOR_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        preview = text[:SUMMARY_CHARS] + ("..." if len(text) > SUMMARY_CHARS else "")
        out.append((str(rel), preview))
        if limit and len(out) >= limit:
            break
    return out


def parse_lint_blocks(raw: str, now_ms: int) -> list[dict]:
    """Parse ---LINT:type|severity|title---\n<body>\n---END LINT--- blocks.
    Mirrors NashSU lint.ts L266-291."""
    results: list[dict] = []
    for n, m in enumerate(LINT_BLOCK_REGEX.finditer(raw)):
        raw_type = m.group(1).strip().lower()
        severity = m.group(2).strip().lower()
        title = m.group(3).strip()
        body = m.group(4).strip()

        # Affected pages (optional PAGES: line)
        pages_match = re.search(r"^PAGES:\s*(.+)$", body, re.MULTILINE)
        affected = (
            [p.strip() for p in pages_match.group(1).split(",")]
            if pages_match
            else None
        )
        detail = re.sub(r"^PAGES:.*$", "", body, flags=re.MULTILINE).strip()

        # Severity coercion (NashSU L286: only "warning" stays warning)
        sev = "warning" if severity == "warning" else "info"

        results.append({
            "type": "semantic",
            "severity": sev,
            "page": title,
            "detail": f"[{raw_type}] {detail}",
            "affectedPages": affected,
            "id": f"lint-semantic-{n}",
            "createdAt": now_ms,
        })
    return results


def build_prompt(summaries: list[tuple[str, str]]) -> tuple[str, str]:
    """Returns (system_prompt, user_content). The system prompt is the
    full task spec; the user content carries the wiki page summaries."""
    lang_directive = build_language_directive(
        "\n".join(p for _, p in summaries)[:LANG_SAMPLE_CHARS]
    )
    system_prompt = (
        "You are a wiki quality analyst. Review the following wiki page summaries and identify issues.\n"
        "\n"
        f"{lang_directive}\n"
        "\n"
        "For each issue, output exactly this format:\n"
        "\n"
        "---LINT: type | severity | Short title---\n"
        "Description of the issue.\n"
        "PAGES: page1.md, page2.md\n"
        "---END LINT---\n"
        "\n"
        "Types:\n"
        "- contradiction: two or more pages make conflicting claims\n"
        "- stale: information that appears outdated or superseded\n"
        "- missing-page: an important concept is heavily referenced but has no dedicated page\n"
        "- suggestion: a question or source worth adding to the wiki\n"
        "- cross-domain-ambiguity: same term (slug) used for different concepts in different domains but not disambiguated — e.g., 'switch' meaning both a mechanical switch (circuit-fundamentals) and a switching transistor (power-electronics) without domain-specific pages\n"
        "- wrong-domain: a page's frontmatter `domain` field does not match its actual content domain\n"
        "\n"
        "Severities:\n"
        "- warning: should be addressed\n"
        "- info: nice to have\n"
        "\n"
        "Only report genuine issues. Do not invent problems. Output ONLY the ---LINT--- blocks, no other text.\n"
        "\n"
        "## Wiki Pages\n"
    )
    user_content = "\n\n".join(
        f"### {path}\n{preview}" for path, preview in summaries
    )
    return system_prompt, user_content


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompt + summary stats, skip LLM call")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of pages sampled (for huge wikis)")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"LLM max_tokens (default {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path (default: <state_dir>/lint-semantic.json)")
    args = parser.parse_args()

    root = Path(os.environ.get("IMPROVED_WIKI_ROOT", os.getcwd()))
    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        print(f"ERROR: wiki/ not found under {root}", file=sys.stderr)
        return 2

    # State dir resolution (matches ingest.py + validate_ingest.py)
    # Uses _paths.detect_runtime_dir() — .llm-wiki/ default, auto-migrates from .iwiki-runtime/
    _script_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(_script_root))
    from _paths import detect_runtime_dir  # noqa: E402

    state_dir = detect_runtime_dir(root)  # handles all fallback logic
    out_path = Path(args.output) if args.output else state_dir / "lint-semantic.json"

    summaries = collect_summaries(wiki_dir, limit=args.limit)
    if not summaries:
        print(f"[semantic-lint] No wiki pages found in {wiki_dir}", file=sys.stderr)
        # Still write an empty findings file so callers don't error
        out_path.write_text("[]", encoding="utf-8")
        return 0

    print(f"[semantic-lint] Collected {len(summaries)} page summaries")

    system_prompt, user_content = build_prompt(summaries)

    if args.dry_run:
        print(f"[semantic-lint] DRY-RUN: would send {len(user_content):,} chars to LLM")
        print(f"  system_prompt: {len(system_prompt):,} chars")
        print(f"  first 500 chars of user_content:\n  {user_content[:500]!r}")
        return 0

    # LLM config: env vars override config.json
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "")

    if not (api_key and base_url and model):
        # Read from ~/.agents/config.json (same source as ingest.py)
        config_path = Path.home() / ".agents" / "config.json"
        try:
            if config_path.exists():
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                default = os.environ.get("LLM_PROVIDER") or cfg.get("default", "")
                provider = cfg.get("providers", {}).get(default, {})
                if provider:
                    api_key = api_key or provider.get("api_key", "")
                    base_url = base_url or provider.get("base_url", "")
                    model = model or provider.get("models", {}).get("text", provider.get("model", ""))
        except Exception:
            pass

    if not api_key:
        print("ERROR: LLM_API_KEY not set. Export it (e.g. source ~/.hermes/.env) "
              "or configure ~/.agents/config.json, or use --dry-run to skip the LLM call.",
              file=sys.stderr)
        return 2

    print(f"[semantic-lint] Calling LLM ({model} @ {base_url}) ...")
    try:
        raw = call_llm(
            system_prompt, user_content,
            base_url=base_url, model=model, api_key=api_key,
            max_tokens=args.max_tokens,
        )
    except Exception as e:
        print(f"[semantic-lint] LLM call failed: {e}", file=sys.stderr)
        return 1

    now_ms = int(time.time() * 1000)
    findings = parse_lint_blocks(raw, now_ms)
    print(f"[semantic-lint] Parsed {len(findings)} semantic finding(s) from LLM output "
          f"({len(raw):,} chars raw)")

    # Atomic write
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(findings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(out_path)
    print(f"[semantic-lint] Wrote {out_path}")

    # Summary
    if findings:
        from collections import Counter
        c = Counter(f["severity"] for f in findings)
        print(f"[semantic-lint] severity: warning={c.get('warning', 0)} info={c.get('info', 0)}")

    # ── Write lint pages to wiki/lint/ (human-browsable, same format as structural) ──
    lint_dir = wiki_dir / "lint"
    lint_dir.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y-%m-%d")
    severity_icon = {"warning": "⚠️", "info": "ℹ️"}

    written = 0
    fname_counts: dict[str, int] = {}
    for f in findings:
        detail = f.get("detail", "")
        raw_type = ""
        m = re.match(r"\[(\w+)\]\s*", detail)
        if m:
            raw_type = m.group(1)
        sev = f.get("severity", "info")
        icon = severity_icon.get(sev, "ℹ️")
        affected = f.get("affectedPages") or []
        page_ref = f.get("page", "semantic")

        # Safe filename
        safe_type = re.sub(r"[^\w-]", "", raw_type)[:20] if raw_type else "semantic"
        safe_title = re.sub(r"[^\w一-鿿\-]", "-", page_ref)[:50]
        base_name = f"semantic-{safe_type}-{safe_title}"
        base_name = re.sub(r"-{2,}", "-", base_name)
        n = fname_counts.get(base_name, 0) + 1
        fname_counts[base_name] = n
        filename = f"{base_name}-{n:02d}.md" if n > 1 else f"{base_name}.md"

        affected_links = "\n".join(f"- [[{p.replace('.md', '')}]]" for p in affected)

        md = f"""---
type: lint
lint_type: semantic
raw_type: {raw_type}
severity: {sev}
page: "{page_ref}"
affected_pages: [{', '.join(affected)}]
resolved: false
created: {date_str}
---

# {icon} [semantic/{raw_type}] {page_ref}

{detail}

{"## Affected Pages" if affected else ""}
{affected_links}
{"## Resolution" if affected else "## Resolution"}
_修复后，将 frontmatter 中 `resolved: false` 改为 `resolved: true`，下次 lint 时自动清理。_
"""
        page_path = lint_dir / filename
        tmp = page_path.with_suffix(page_path.suffix + ".tmp")
        tmp.write_text(md, encoding="utf-8")
        tmp.rename(page_path)
        written += 1

    if written > 0:
        print(f"[semantic-lint] {written} semantic lint pages → {lint_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
