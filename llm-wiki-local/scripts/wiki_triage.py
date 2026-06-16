#!/usr/bin/env python3
"""
Triage RadarWiki (or any LLM Wiki project) review queue + lint state.

Usage:
    python3 wiki_triage.py [<project-path>]

Default project: ~/Documents/知识库/RadarWiki

Output (stdout):
  - review.json: total / unprocessed / by-type counts
  - lint.json: total / warning / info / by-type-by-severity
  - ingest-progress/: orphan in-flight digest (if any)
  - quick health verdict

Status-reporting discipline: this script reports STATE, not "completion".
A "0 unprocessed" verdict is a real "wiki is clean" signal; a "0 broken-link
warning" is a separate signal. Report both.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path


def triage(proj: Path) -> dict:
    llm = proj / ".llm-wiki"
    out: dict = {"project": str(proj), "files_found": {}, "health": {}}

    # --- review.json ---
    review_path = llm / "review.json"
    if review_path.exists():
        rev = json.loads(review_path.read_text())
        out["files_found"]["review.json"] = True
        out["review"] = {
            "total": len(rev),
            "unprocessed": sum(1 for i in rev if i.get("status") in (None, "none")),
            "by_type": dict(Counter(i.get("type", "?") for i in rev)),
            "by_status": dict(Counter(i.get("status", "none") for i in rev)),
        }
    else:
        out["files_found"]["review.json"] = False
        out["review"] = None

    # --- lint.json ---
    lint_path = llm / "lint.json"
    if lint_path.exists():
        lint = json.loads(lint_path.read_text())
        out["files_found"]["lint.json"] = True
        type_sev = Counter((x.get("type"), x.get("severity")) for x in lint)
        out["lint"] = {
            "total": len(lint),
            "by_type_severity": {f"{t}|{s}": n for (t, s), n in type_sev.items()},
            "warning_count": sum(n for (t, s), n in type_sev.items() if s == "warning"),
            "info_count": sum(n for (t, s), n in type_sev.items() if s == "info"),
        }
    else:
        out["files_found"]["lint.json"] = False
        out["lint"] = None

    # --- ingest-progress/: orphan in-flight digest ---
    prog_dir = llm / "ingest-progress"
    out["in_flight"] = []
    if prog_dir.exists():
        for f in prog_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                age_s = int(time.time() - f.stat().st_mtime)
                out["in_flight"].append(
                    {
                        "file": f.name,
                        "source": d.get("sourceIdentity"),
                        "progress": f"{d.get('completedThrough', 0)}/{d.get('chunkTotal', 0)}",
                        "age_s": age_s,
                        "stale_min": age_s // 60,
                    }
                )
            except Exception as e:
                out["in_flight"].append({"file": f.name, "error": str(e)})

    # --- queue ---
    q_path = llm / "ingest-queue.json"
    if q_path.exists():
        q = json.loads(q_path.read_text())
        out["queue"] = {
            "total": len(q),
            "by_status": dict(Counter(i.get("status") for i in q)),
        }
    else:
        out["queue"] = None

    # --- health verdict ---
    warnings = out.get("lint", {}).get("warning_count", 0) if out.get("lint") else 0
    unprocessed = out.get("review", {}).get("unprocessed", 0) if out.get("review") else 0
    stale_digests = [x for x in out["in_flight"] if x.get("stale_min", 0) >= 30]
    queue_total = out.get("queue", {}).get("total", 0) if out.get("queue") else 0

    out["health"] = {
        "broken_link_warnings": warnings,
        "unprocessed_review_items": unprocessed,
        "stale_in_flight_digests": len(stale_digests),
        "queue_size": queue_total,
        "verdict": (
            "CLEAN"
            if (warnings == 0 and unprocessed == 0 and len(stale_digests) == 0 and queue_total == 0)
            else "ACTION_NEEDED"
        ),
    }
    return out


def print_report(out: dict) -> None:
    proj = out["project"]
    print(f"=== LLM Wiki triage: {proj} ===\n")

    if out.get("review"):
        r = out["review"]
        print(f"[review.json]  {r['total']} items, {r['unprocessed']} unprocessed")
        print(f"  by type:   {r['by_type']}")
        print(f"  by status: {r['by_status']}")
    else:
        print("[review.json]  NOT FOUND")
    print()

    if out.get("lint"):
        l = out["lint"]
        print(f"[lint.json]    {l['total']} items")
        print(f"  warning: {l['warning_count']}  (actionable)")
        print(f"  info:    {l['info_count']}    (usually no action)")
        print(f"  by type/severity: {l['by_type_severity']}")
    else:
        print("[lint.json]    NOT FOUND")
    print()

    if out.get("queue"):
        print(f"[queue]        {out['queue']['total']} items, by status: {out['queue']['by_status']}")
    if out["in_flight"]:
        print(f"[in-flight]    {len(out['in_flight'])} digest progress files:")
        for x in out["in_flight"]:
            if "error" in x:
                print(f"  {x['file']}: ERROR {x['error']}")
            else:
                stale = " STALE" if x.get("stale_min", 0) >= 30 else ""
                print(
                    f"  {x['source'][:50]}: {x['progress']} "
                    f"(age {x['stale_min']}m){stale}"
                )
    print()

    h = out["health"]
    print("=== Health ===")
    print(f"  broken-link warnings:      {h['broken_link_warnings']}")
    print(f"  unprocessed review items:  {h['unprocessed_review_items']}")
    print(f"  stale in-flight digests:   {h['stale_in_flight_digests']}")
    print(f"  queue size:                {h['queue_size']}")
    print(f"  verdict: {h['verdict']}")


def main() -> None:
    if len(sys.argv) > 1:
        proj = Path(sys.argv[1]).expanduser()
    else:
        proj = Path("~/Documents/知识库/RadarWiki").expanduser()
    if not (proj / ".llm-wiki").exists():
        print(f"ERROR: {proj}/.llm-wiki not found", file=sys.stderr)
        sys.exit(1)
    out = triage(proj)
    print_report(out)
    # also dump JSON for programmatic use
    # print("\n--- JSON ---")
    # print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
