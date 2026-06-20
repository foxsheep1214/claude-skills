#!/usr/bin/env python3
"""lint.py — Global wiki consistency checks (Phase 2 of NashSU refactor)

Separate from ingest for independent, offline wiki-wide validation.
Checks for orphan pages, broken references, structural issues.

Usage:
    python3 lint.py
    python3 lint.py --wiki-root ~/Documents/知识库/HardwareWiki
"""

import argparse
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))

from _core import Config, detect_runtime_dir


def check_orphan_pages(wiki_root: Path) -> list[str]:
    """Find pages with no incoming links"""
    orphans = []
    concepts_dir = wiki_root / "concepts"
    entities_dir = wiki_root / "entities"

    if not concepts_dir.exists() and not entities_dir.exists():
        return orphans

    all_pages = list(concepts_dir.glob("*.md")) + list(entities_dir.glob("*.md"))

    for page in all_pages:
        # Check if any other page links to this one
        found_link = False
        for other_page in all_pages:
            if other_page == page:
                continue
            try:
                content = other_page.read_text(encoding='utf-8')
                if f"[[{page.stem}]]" in content or f"[{page.stem}]" in content:
                    found_link = True
                    break
            except Exception:
                pass

        if not found_link:
            orphans.append(page.name)

    return orphans


def check_broken_references(wiki_root: Path) -> list[tuple[str, str]]:
    """Find broken wiki references (links to non-existent pages)"""
    broken = []
    concepts_dir = wiki_root / "concepts"
    entities_dir = wiki_root / "entities"

    all_pages = set()
    if concepts_dir.exists():
        all_pages.update(p.stem for p in concepts_dir.glob("*.md"))
    if entities_dir.exists():
        all_pages.update(p.stem for p in entities_dir.glob("*.md"))

    all_files = list(concepts_dir.glob("*.md")) + list(entities_dir.glob("*.md")) if concepts_dir.exists() or entities_dir.exists() else []

    for page_file in all_files:
        try:
            content = page_file.read_text(encoding='utf-8')
            import re
            links = re.findall(r'\[\[([^\]]+)\]\]', content)
            for link in links:
                if link not in all_pages:
                    broken.append((page_file.name, link))
        except Exception:
            pass

    return broken


def lint_wiki(wiki_root: Path) -> dict:
    """Run all lint checks and return results"""
    results = {
        "orphan_pages": check_orphan_pages(wiki_root),
        "broken_references": check_broken_references(wiki_root),
        "passed": True
    }

    return results


def main():
    """Main lint command"""
    parser = argparse.ArgumentParser(description="Wiki-wide consistency checks")
    parser.add_argument("--wiki-root", type=Path, help="Wiki root directory")
    args = parser.parse_args()

    wiki_root = args.wiki_root or Path.cwd()

    if not wiki_root.exists():
        print(f"❌ Wiki root not found: {wiki_root}")
        return 1

    print(f"🔍 Lint: Global Wiki Consistency Check")
    print(f"  Wiki: {wiki_root}")
    print()

    results = lint_wiki(wiki_root)

    # Report orphan pages
    if results["orphan_pages"]:
        print(f"⚠️  Found {len(results['orphan_pages'])} orphan pages (no incoming links):")
        for page in results["orphan_pages"]:
            print(f"    - {page}")
        print()

    # Report broken references
    if results["broken_references"]:
        print(f"⚠️  Found {len(results['broken_references'])} broken references:")
        for page, link in results["broken_references"]:
            print(f"    - {page}: links to missing [[{link}]]")
        print()

    if not results["orphan_pages"] and not results["broken_references"]:
        print("✅ All checks passed!")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
