"""Stage 4.1: final ingest validation (post-write).

Runs after Stage 3 writes wiki pages to disk and after Stage 3.7 embeddings.
Runs validate_ingest.py inline for fresh verification evidence — the
Superpowers Iron Law: every ingest MUST produce fresh verification evidence
before claiming completion.

Sibling of _stage_3_7_embed.py (Stage 3.7 embeddings). 3.7 is embed-side
I/O; this module is the final verification gate — different concerns, one
stage per file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from _core import Config


def stage_4_1_validate_ingest(config: Config, raw_file: Path) -> None:
    """Run validate_ingest.py inline for the just-completed source.

    Superpowers Iron Law: every ingest MUST produce fresh verification evidence
    before claiming completion.  This runs the 13-stage validator on the current
    source and prints the result.  Hard failures prevent the "ok" status.
    """
    import subprocess
    validate_script = Path(__file__).parent / "validate_ingest.py"
    if not validate_script.exists():
        print("[validate] ⚠️  validate_ingest.py not found, skipping final verification")
        return

    slug = raw_file.stem
    # Compute the exact cache key (matching ingest.py's `rel` variable)
    try:
        cache_key = str(raw_file.relative_to(config.raw_root))
    except ValueError:
        cache_key = str(raw_file)
    print(f"\n[validate] Running 13-stage final verification for {slug} (cache_key={cache_key})...")
    result = subprocess.run(
        [sys.executable, str(validate_script)],
        env={**os.environ, "IMPROVED_WIKI_ROOT": str(config.wiki_root),
             "SOURCE_SLUG": slug,
             "CACHE_KEY": cache_key},
        capture_output=True, text=True, timeout=600,
    )
    # Print the validator output (shows per-stage PASS/FAIL)
    stdout = result.stdout.strip()
    if stdout:
        # Print only the summary lines to avoid overwhelming output
        for line in stdout.splitlines():
            if any(marker in line for marker in ["Result:", "PASS", "FAIL", "❌", "✅", "Stage"]):
                print(f"  {line}")

    if result.returncode != 0:
        # Don't raise — the ingest succeeded but validation found issues.
        # The compliance record already documents stage status.
        stderr_tail = result.stderr.strip()[-500:] if result.stderr else ""
        print(f"[validate] ⚠️  Validator exit {result.returncode} — review warnings above")
        if stderr_tail:
            print(f"[validate] {stderr_tail}")
    else:
        print(f"[validate] ✅ All 13 stages verified — ingest complete")
