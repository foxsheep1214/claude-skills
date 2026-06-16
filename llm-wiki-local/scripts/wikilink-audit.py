#!/usr/bin/env python3
"""
Comprehensive wikilink audit for an LLM Wiki project.

Walks every wiki/**/*.md, extracts every [[wikilink]] (with optional
#anchor / |display), resolves the target against the wiki tree using
LLM Wiki's resolution rules, and reports unresolved targets with
frequency + source pages.

This is the audit that runs AFTER the broken-link-repair-workflow has
finished its C/A bucket work — it answers "did I miss any?" and gives a
value-bucketed view of what remains.

Usage:
    python3 wikilink-audit.py [<project-path>]

Default project: ~/Documents/知识库/RadarWiki

Output (stdout):
  - Total wiki pages / total wikilink refs / unique targets
  - Unresolved target count + frequency table
  - Value buckets (multi-source high-value, acronyms, proper nouns, etc.)
  - Source-file rollup (which files contribute the most unresolved targets)
  - A residual-by-bucket summary so the user can decide whether to keep going

Status-reporting discipline: this script reports state, not completion.
"Unresolved = 0" is a real cleanliness signal; "unresolved dropped from
460 to 449" is also a real signal of partial progress.

Why a separate script (not part of wiki_triage.py):
  - wiki_triage.py reads ONLY LLM Wiki's own .llm-wiki state files
    (review.json, lint.json, ingest-queue.json, ingest-progress/).
  - This script reads the wiki/ markdown tree directly — the ground
    truth. lint.json is re-derivable, so we audit the source.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")


def parse_wikilink(content: str):
    """Return list of (target, anchor, display) tuples."""
    results = []
    for m in WIKILINK_RE.finditer(content):
        inner = m.group(1)
        if "#" in inner:
            target_part, anchor = inner.split("#", 1)
        else:
            target_part, anchor = inner, None
        if "|" in target_part:
            target, display = target_part.split("|", 1)
        else:
            target, display = target_part, None
        results.append((target.strip(), anchor, display))
    return results


def build_page_index(wiki_root: Path):
    """Build stem -> [relative paths] index for resolution."""
    all_files = list(wiki_root.rglob("*.md"))
    stem_paths = defaultdict(list)
    for f in all_files:
        stem_paths[f.stem].append(str(f.relative_to(wiki_root)))
    return all_files, stem_paths


def resolve_target(target: str, source_file: Path, wiki_root: Path, stem_paths: dict):
    """
    Mirror LLM Wiki's resolution rules:
      1. If target has no '/', check source_file.parent first (same-dir stem match)
      2. If target looks like a relative path, try wiki_root / target + .md
      3. If target has '/', try direct path
      4. Fall back to unique stem match across the whole wiki
      5. Fall back to ambiguous stem match (returns first, flags ambiguity)
    Returns (resolved_relative_path, reason) or (None, reason).
    """
    # 1. Same-dir stem
    if "/" not in target:
        same_dir = source_file.parent / (target + ".md")
        if same_dir.exists():
            return (str(same_dir.relative_to(wiki_root)), "stem in same dir")
    # 2/3. Path-style
    for candidate in (target + ".md", target):
        p = wiki_root / candidate
        if p.exists():
            return (str(p.relative_to(wiki_root)), "path")
    # 4/5. Cross-dir stem
    matches = stem_paths.get(target, [])
    if len(matches) == 1:
        return (matches[0], "unique stem")
    if len(matches) > 1:
        return (matches[0], f"ambiguous stem ({len(matches)} matches)")
    return (None, "NOT FOUND")


def bucket_target(target: str, frequency: int) -> str:
    """
    Classify an unresolved target into a value bucket:
      D: high-frequency, multi-source, no existing page  (top priority)
      C: page exists with slightly different name  (separate recheck needed)
      B: acronym / model / proper noun  (dismiss unless user overrides)
      F: URL or regulation number  (dismiss)
      A: real concept cited once or twice  (judge: stub or dismiss)
      A': single-source niche terminology  (dismiss by default)
    """
    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in target)
    has_english_alpha = any(ch.isascii() and ch.isalpha() for ch in target)
    has_dot = "." in target
    has_dash = "-" in target
    all_caps_acronym = bool(re.match(r"^[A-Z0-9\-_/]+$", target)) and not has_chinese

    # URL/regulation pattern: contains . but no Chinese, OR looks like DoDI-XXXX.YY
    if (has_dot and not has_chinese) or re.match(r"^[A-Z][A-Za-z]+-\d", target):
        return "F"
    if all_caps_acronym and frequency == 1:
        return "B"
    # Person-name patterns: First-Last, X-Y-Z, etc.
    if re.match(r"^[A-Z][a-zA-Z]+-[A-Z][a-zA-Z]+(-[A-Z][a-zA-Z]+)*$", target) and not has_chinese:
        return "B"
    if re.match(r"^[A-Z]-[A-Z]-[A-Z][a-zA-Z\-]+$", target):
        return "B"
    if frequency >= 3 and has_chinese:
        return "D"
    if frequency >= 2 and has_chinese:
        return "A"
    if has_chinese:
        return "A'"
    if has_english_alpha and not has_chinese:
        return "B"
    return "A'"


def audit(wiki_root: Path):
    all_files, stem_paths = build_page_index(wiki_root)
    existing_stems = {f.stem for f in all_files}

    all_links = []
    for f in all_files:
        for target, anchor, display in parse_wikilink(f.read_text()):
            all_links.append((str(f.relative_to(wiki_root)), target))

    target_count = Counter(t for _, t in all_links)
    target_sources = defaultdict(set)
    for src, t in all_links:
        target_sources[t].add(src)

    unresolved_targets = [t for t in target_count if t not in existing_stems]
    unresolved_refs = sum(1 for _, t in all_links if t not in existing_stems)

    # Resolve to find ambiguous-but-resolved (warn but don't count as unresolved)
    resolved_full = []
    for src, t in all_links:
        f = next((x for x in all_files if str(x.relative_to(wiki_root)) == src), None)
        if f is None:
            continue
        r, reason = resolve_target(t, f, wiki_root, stem_paths)
        if r:
            resolved_full.append((src, t, r, reason))

    # Bucket unresolved
    bucketed = defaultdict(list)
    for t in unresolved_targets:
        b = bucket_target(t, target_count[t])
        bucketed[b].append(t)

    # Source-file rollup
    per_file = defaultdict(int)
    for src, t in all_links:
        if t in unresolved_targets:
            per_file[src] += 1

    return {
        "wiki_root": str(wiki_root),
        "total_pages": len(all_files),
        "total_refs": len(all_links),
        "unique_targets": len(target_count),
        "unresolved_refs": unresolved_refs,
        "unresolved_unique": len(unresolved_targets),
        "buckets": {b: len(ts) for b, ts in bucketed.items()},
        "bucket_targets": {b: sorted(ts, key=lambda x: -target_count[x]) for b, ts in bucketed.items()},
        "target_count": dict(target_count),
        "target_sources": {t: sorted(srcs) for t, srcs in target_sources.items()},
        "per_file_unresolved": dict(sorted(per_file.items(), key=lambda x: -x[1])),
    }


def print_report(result: dict):
    print(f"=== Wikilink audit: {result['wiki_root']} ===\n")
    print(f"Pages:          {result['total_pages']}")
    print(f"Total wikilink refs: {result['total_refs']}")
    print(f"Unique targets: {result['unique_targets']}")
    print(f"Unresolved refs:    {result['unresolved_refs']}")
    print(f"Unresolved unique:  {result['unresolved_unique']}")
    print()
    print("=== Value buckets (D = top priority, A' = default dismiss) ===")
    bucket_labels = {
        "D": "D — high-freq (>=3), no page, likely core concept",
        "A": "A — Chinese term cited 1-2x, judge stub or dismiss",
        "A'": "A' — single-source Chinese niche, default dismiss",
        "B": "B — acronym / model / person name, default dismiss",
        "F": "F — URL / regulation number, dismiss",
    }
    for b in ("D", "A", "A'", "B", "F"):
        if b not in result["buckets"]:
            continue
        n = result["buckets"][b]
        print(f"  {bucket_labels[b]}: {n}")
    print()

    # Top unresolved by frequency
    unresolved_with_freq = sorted(
        result["bucket_targets"].get("D", []) + result["bucket_targets"].get("A", []),
        key=lambda t: -result["target_count"][t],
    )
    if unresolved_with_freq:
        print("=== High/medium-value unresolved targets (sorted by frequency) ===")
        for t in unresolved_with_freq[:20]:
            c = result["target_count"][t]
            sources = result["target_sources"].get(t, [])[:3]
            print(f"  x{c:2d}  {t}")
            for s in sources:
                print(f"         <- {s}")
        if len(unresolved_with_freq) > 20:
            print(f"  ... and {len(unresolved_with_freq) - 20} more")
    print()

    # Source-file rollup (top 10)
    print("=== Source files contributing most unresolved refs ===")
    for src, n in list(result["per_file_unresolved"].items())[:10]:
        print(f"  {n:3d}  {src}")
    if len(result["per_file_unresolved"]) > 10:
        print(f"  ... and {len(result['per_file_unresolved']) - 10} more files with unresolved refs")
    print()

    # Verdict
    d_count = result["buckets"].get("D", 0)
    a_count = result["buckets"].get("A", 0)
    if d_count == 0 and a_count == 0:
        verdict = "CLEAN (no high/medium-value targets left)"
    elif d_count == 0:
        verdict = f"LOW VALUE (only {a_count} A-bucket items, judgment call)"
    else:
        verdict = f"ACTION NEEDED ({d_count} D-bucket + {a_count} A-bucket items)"
    print(f"=== Verdict: {verdict} ===")


def main():
    if len(sys.argv) > 1:
        proj = Path(sys.argv[1]).expanduser()
    else:
        proj = Path("~/Documents/知识库/RadarWiki").expanduser()
    wiki = proj / "wiki"
    if not wiki.exists():
        print(f"ERROR: {wiki} not found", file=sys.stderr)
        sys.exit(1)
    result = audit(wiki)
    print_report(result)


if __name__ == "__main__":
    main()
