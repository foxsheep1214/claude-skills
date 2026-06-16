"""
_paths.py — Shared runtime directory detection for improved-wiki scripts.

Matches ingest.py Config.from_env() logic exactly:
  - Default:     <root>/.llm-wiki/          (NashSU-aligned)
  - Back compat: <root>/.iwiki-runtime/     (existing improved-wiki projects)
  - Legacy:      <root>/wiki/               (when old state files exist inside wiki/)

Usage:
    from _paths import detect_runtime_dir

    runtime = detect_runtime_dir(Path(project_root))
    extract  = runtime / "extract-tmp" / slug
    cache    = runtime / "ingest-cache.json"
    review   = runtime / "review.json"
"""

from pathlib import Path


def detect_runtime_dir(wiki_root: Path) -> Path:
    """Return the runtime directory for this wiki project.

    Priority:
      1. .iwiki-runtime/   auto-migrate to .llm-wiki/ if it still exists
      2. .llm-wiki/        if it exists and has valid content (ingest-cache.json,
                           ingest-progress/, or embed-cache.json) — preferred over
                           legacy wiki/ even if old state files exist there
      3. wiki/             if old state files exist there (legacy), and .llm-wiki/
                           is empty or doesn't exist
      4. .llm-wiki/        clean default (NashSU-aligned)
    """
    llm_wiki = wiki_root / ".llm-wiki"
    iwiki = wiki_root / ".iwiki-runtime"

    # Auto-migrate from .iwiki-runtime → .llm-wiki
    if iwiki.exists():
        _migrate_iwiki_runtime(iwiki, llm_wiki)
        # After migration, use .llm-wiki
        return llm_wiki

    # If .llm-wiki/ exists and has valid content, use it regardless of legacy wiki/
    llm_wiki_indicators = [
        llm_wiki / "ingest-cache.json",
        llm_wiki / "ingest-progress",
        llm_wiki / "embed-cache.json",
    ]
    if any(p.exists() for p in llm_wiki_indicators):
        return llm_wiki

    # Legacy: old projects that put state inside wiki/
    old_indicators = [
        wiki_root / "wiki" / ".ingest-cache.json",
        wiki_root / "wiki" / "ingest-cache.json",
        wiki_root / "wiki" / ".ingest-progress",
        wiki_root / "wiki" / "ingest-progress",
        wiki_root / "wiki" / ".extract-tmp",
        wiki_root / "wiki" / "extract-tmp",
    ]
    if any(p.exists() for p in old_indicators):
        return wiki_root / "wiki"

    # Auto-migrate: lint-cache.json / lint-lock in wiki/
    _migrate_lint_cache_out_of_wiki(wiki_root)

    # Default: NashSU-aligned
    return llm_wiki


def _migrate_iwiki_runtime(iwiki: Path, llm_wiki: Path) -> None:
    """Migrate .iwiki-runtime/ contents → .llm-wiki/, then remove old dir."""
    import shutil, sys
    llm_wiki.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(iwiki.iterdir()):
        dst = llm_wiki / src.name
        try:
            if src.is_dir():
                if dst.exists():
                    # Merge: move individual files
                    for f in src.iterdir():
                        f.rename(dst / f.name)
                        count += 1
                    src.rmdir()
                else:
                    src.rename(dst)
            else:
                if dst.exists():
                    src.unlink()  # already migrated elsewhere
                else:
                    src.rename(dst)
            count += 1
        except OSError:
            pass
    # Remove old dir if empty (or force remove after migration attempt)
    try:
        iwiki.rmdir()
    except OSError:
        pass
    if count:
        print(f"[_paths] Migrated {count} items from .iwiki-runtime/ → .llm-wiki/", file=sys.stderr)


def _migrate_lint_cache_out_of_wiki(wiki_root: Path) -> None:
    """If lint-cache.json or lint-lock exists under wiki/, move to .llm-wiki/."""
    wiki = wiki_root / "wiki"
    runtime = wiki_root / ".llm-wiki"
    migrated = 0
    for name in ("lint-cache.json", "lint-lock"):
        wiki_path = wiki / name
        if wiki_path.exists():
            runtime.mkdir(parents=True, exist_ok=True)
            dest = runtime / name
            wiki_path.rename(dest)
            migrated += 1
    # Also clean up stale numbered copies (concurrent-run artifacts)
    for stale in sorted(wiki.glob("lint-cache [0-9]*.json")):
        stale.unlink(missing_ok=True)
        migrated += 1
    for stale in sorted(wiki.glob("lint-lock [0-9]*")):
        stale.unlink(missing_ok=True)
        migrated += 1
    if migrated:
        import sys
        print(f"[_paths] Migrated {migrated} lint state file(s) from wiki/ → .llm-wiki/", file=sys.stderr)
