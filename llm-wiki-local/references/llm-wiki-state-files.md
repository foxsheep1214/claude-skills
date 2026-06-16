---
title: LLM Wiki state files — four sources of truth
date: 2026-06-09
purpose: Quick reference for the agent when diagnosing "why is the queue full of files I already digested" / "did the digest really run" / "why did the embedding change"
---

# `.llm-wiki/` state files — full schema map

LLM Wiki v0.4.x (Electron desktop app) keeps state in **four files** under the project root (`<project>/.llm-wiki/`) plus one global config file under `~/Library/Application Support/com.llmwiki.app/`. They are not always consistent — that's the point of having all of them.

## File map

```
<project>/
├── .llm-wiki/
│   ├── ingest-cache.json       ← authoritative digest history
│   ├── ingest-queue.json       ← pending work (the "queue" the UI shows)
│   ├── file-snapshot.json      ← current file inventory (paths only)
│   ├── lancedb/
│   │   └── wiki_chunks_v{N}.lance   ← vector index; N bumps on embedding change
│   ├── ingest-progress/        ← per-book live progress JSONs (only for books currently being digested)
│   │   └── _backup/            ← completed-digest progress, archived here on success. Move-not-delete:
│   │                              the file's content (`globalDigest`, `analyses[]`, `chunkTotal`)
│   │                              IS the digest result, alongside the .md files in `wiki/`.
│   ├── image-caption-cache.json    ← image hash → caption map (liveness signal)
│   ├── conversations.json      ← chat session IDs
│   ├── chats/                  ← chat session contents
│   ├── project.json            ← project metadata
│   ├── file-change-queue.json  ← internal watcher queue
│   ├── dedup-queue.json        ← internal dedup state
│   ├── lint.json               ← wiki lint state (mechanical scan: broken-link / orphan / no-outlinks)
│   └── review.json             ← LLM-curated review items (confirm / suggestion / missing-page / contradiction / duplicate)
└── raw/sources/                ← source documents being digested

~/Library/Application Support/com.llmwiki.app/
├── app-state.json              ← global config (token, model, projects, embeddings)
├── app-state.json.bak.pre-X.<ts>   ← config rollback points (one per recent change)
└── (Caches/, Preferences/, WebKit/ are app-internal, not relevant to diagnosis)
```

## Schemas

### `ingest-cache.json`

```json
{
  "entries": {
    "Convex Optimization Exercises - 2012 - Boyd.pdf": {
      "hash": "a2e0f87677d407476249e0441aa76e3a0cf56e97d3105f5ef994445146f765ab",
      "timestamp": 1780849298328,
      "filesWritten": [
        "wiki/sources/Convex Optimization Exercises - 2012 - Boyd.md",
        "wiki/entities/stephen-boyd.md",
        "...",
        "wiki/index.md",
        "wiki/log.md",
        "wiki/overview.md"
      ]
    }
  }
}
```

**Key facts**:
- Key is the **relative path from `raw/sources/`** (e.g. `book/Array Signal Processing - 1989 - Pillai.pdf` for files under that subdirectory).
- `hash` is SHA-256 of the source file bytes at digest time.
- `filesWritten` is the ground truth for "this digest produced N entities + M concepts + 1 source.md".
- Entries are **append-only** — once added, the entry stays even if the source file is later modified or deleted.
- A source path being in `entries` does **not** mean the current source file matches the cached hash.

### `ingest-queue.json`

```json
[
  {
    "id": "ingest-1780927238701-qgsqcf",
    "projectId": "47dfa87b-3389-4174-873b-cae09c6809ac",
    "sourcePath": "raw/sources/book/Discret Time Signal Processing 3rd - 2014 - Oppenheim.pdf",
    "folderContext": "book",
    "status": "pending",     // or "processing", "failed"
    "addedAt": 1780927238701,
    "error": "Chunk analysis stream failed",
    "retryCount": 2
  }
]
```

**Key facts**:
- `status: processing` with a `retryCount > 0` and an `error` looks stuck, but check `ingest-progress/` for the actual progress file before intervening — see the parent skill's "Ingest diagnostics" section.
- Items with `status: pending` and `error: null` are normal new work; do not touch.
- The `folderContext` is derived from the path's first segment relative to `raw/sources/`.
- Items DO get added/removed as the watcher diffs. There is no permanent record in the queue (the cache is permanent; the queue is transient).

### `file-snapshot.json`

```json
{
  "version": 1,
  "updatedAt": 1780964303037,
  "files": [
    "purpose.md",
    "raw/sources/Convex Optimization Exercises - 2012 - Boyd.pdf",
    "raw/sources/book/Advanced Metric Wave Radar - 2020 - Wu.pdf",
    "..."   // 295 entries, list of relative paths
  ]
}
```

**Key facts**:
- Just a path inventory. No hashes, no sizes, no mtimes. The watcher uses this to diff against `ls` of the watched directory.
- New files in newly-scanned subdirectories show up here as new path entries.
- The `updatedAt` field is the timestamp of the last watcher scan.

### `lancedb/wiki_chunks_v{N}.lance`

A Lance database directory. The version suffix `v{N}` increments when `embeddingConfig` (model, outputDimensionality, or chunk size) changes in `app-state.json`. Old `v{N-1}.lance` may or may not be deleted — empirically the v0.4.23 desktop app keeps v1 around but switches reads to v2 after a config change.

**Key facts**:
- The presence of `v{N}.lance` does not mean it is being read. Check `lancedb/wiki_chunks_v{N}.lance/_transactions/` for recent `.txn` files to confirm active writes.
- The `data/<hash>.lance` files are individual chunk data files, named by content hash. Each digest produces ~10–100 of these.
- A `data/<hash>.lance` mtime in the past hour means that chunk was embedded or re-embedded recently.

### `app-state.json.bak.pre-X.<ts>`

A backup of `app-state.json` taken **right before** a setting change. The naming pattern is:

```
app-state.json.bak.pre-<setting-name>.<unix-timestamp-ms>
```

Common observed prefixes:
- `pre-embedding` — embedding model/dim change
- `pre-bge` — switching to bge-m3 specifically
- `pre-deepseek` — switching LLM provider
- `pre-M3` — switching chat model

**To reconstruct what changed**: diff the `.bak.pre-X.<ts>` against the current `app-state.json`. The diff reveals exactly which config field was modified and when.

**Pitfall**: these backup files accumulate over time and are never deleted by the app. If you see 20 `.bak.pre-*` files, the user has changed settings 20 times. This is normal — but if the user reports "digest results disappeared", check the `timestamp` of the most recent backup against the digest `timestamp` in `ingest-cache.json` to see which came first.

## Cross-reference patterns

### Pattern 1: "Is this file really digested?"

```python
import json
from pathlib import Path

proj = Path("~/Documents/知识库/<project>").expanduser()
cache = json.loads((proj/".llm-wiki/ingest-cache.json").read_text())

target = "Convex Optimization Exercises - 2012 - Boyd.pdf"
for k, v in cache["entries"].items():
    if k == target or k.endswith("/" + target):
        print(f"DIGESTED: {k}")
        print(f"  timestamp: {v['timestamp']}")
        print(f"  files written: {len(v['filesWritten'])}")
        break
else:
    print(f"NOT IN CACHE: {target}")
```

### Pattern 2: "Why is this file in the queue?"

```python
queue = json.loads((proj/".llm-wiki/ingest-queue.json").read_text())
for q in queue:
    if "Pillai" in q["sourcePath"]:
        print(f"{q['status']:10} retry={q['retryCount']} path={q['sourcePath']}")
        # If retryCount == 0 and status == pending, it's new work, not a re-run.
```

### Pattern 3: "Did the embedding config change recently?"

```bash
ls -lat ~/Library/Application\ Support/com.llmwiki.app/app-state.json* 2>&1 | head -10
# Compare mtime of app-state.json against the .bak.pre-* files.
# If a .bak.pre-embedding is newer than the last cache entry, the embedding change
# is what triggered the lancedb bump — not a digest re-run.
```

### Pattern 4: "Has a new subdirectory appeared?"

```python
from collections import Counter
from pathlib import Path
queue = json.loads((proj/".llm-wiki/ingest-queue.json").read_text())
parents = Counter(Path(q["sourcePath"]).parent.name for q in queue)
print(parents)
# If `Counter({'book': 160, 'paper': 0})` and book/ didn't exist yesterday, that's
# 160 newly-scanned files, not 160 re-runs of old work.
```

## When state files disagree

The four files can disagree. The most common disagreement is `ingest-cache.json` vs `ingest-queue.json`: a file can be in both (cache says "I already did this", queue says "I'm about to do it again"). When this happens:

1. The queue entry is **newer** than the cache entry (the user re-scanned, the hash changed, the watcher added a new queue item).
2. The cache entry is **authoritative** for "what files were written" — the .md files in `wiki/` are still there from the original digest.
3. The new queue run will re-write the same `wiki/sources/<name>.md` file (overwriting the previous version) but the entities/concepts may merge or duplicate depending on the LLM's response.

**To stop re-runs without losing cached work**:
- Set `sourceWatchConfig.<projectId>.autoIngest: false` in `app-state.json`.
- Manually clear the queue (`ingest-queue.json` → `[]`) after backing it up.
- Future `sources/rescan` calls will only re-queue files with **changed** hashes, not stable ones.

### `ingest-progress/` and `ingest-progress/_backup/`

Per-book digest state. **Schema** (full version in parent skill → "Ingest diagnostics"):

```json
{
  "version": 1,
  "sourceIdentity": "Systems Engineer Guidebook - 2022 - DoD.pdf",
  "sourceHash": "22955c494391a7ad",
  "sourceLength": 608472,
  "sourceBudget": 300000,
  "targetChars": 60000,
  "overlapChars": 3000,
  "chunkTotal": 11,
  "completedThrough": 11,
  "globalDigest": "**Summary**\\n...",
  "analyses": ["## Chunk 1/11 — Page 1\\n..."],
  "updatedAt": 1781054960294
}
```

**Lifecycle**:
- **Live phase**: progress JSON sits at `ingest-progress/<book-slug>-<hash>.json`. `chunkTotal` and `completedThrough` tell you how far through. `updatedAt` is the liveness signal — recent ms timestamp = still working.
- **Completion**: on success, the live JSON is **moved** to `ingest-progress/_backup/` (not deleted). The `_backup/` file is the only on-disk record of the completed digest's full metadata. `ingest-cache.json` only stores hash + `filesWritten` — not the digest text itself. The `_backup/` `globalDigest` and `analyses[]` are the canonical record.
- **Failure path**: live JSON stays in `ingest-progress/` (or is moved to `_backup/` depending on app version), `error` is appended to the queue entry, `retryCount` increments.

**`_backup/` interpretation**: if a JSON exists at `ingest-progress/_backup/<slug>-<hash>.json` with `completedThrough == chunkTotal` and `globalDigest` non-empty, the digest **finished successfully** — regardless of whether `ingest-cache.json` has a matching entry. The cache is the UI-facing record; the backup is the data record.

### Pattern 5: "Orphan completed digest" (state desync)

A digest completed and its progress moved to `_backup/`, but the `ingest-cache.json` entry never got written AND the same book got re-added to `ingest-queue.json` with `status: pending`. Symptom: queue shows N pending items, `ingest-progress/` (live) is empty, app CPU is idle, no `processing` entries. Empirically the worker stops draining the queue after a successful completion that didn't fully register.

```python
import json
from pathlib import Path

proj  = Path("~/Documents/知识库/<project>").expanduser()
llm   = proj / ".llm-wiki"
cache = json.loads((llm/"ingest-cache.json").read_text())
queue = json.loads((llm/"ingest-queue.json").read_text())
backup_dir = llm/"ingest-progress/_backup"

cached_hashes = {e["hash"][:16] for e in cache.get("entries", {}).values()}
queue_names   = {Path(q["sourcePath"]).name for q in queue}

orphans = []
for f in backup_dir.glob("*.json"):
    p = json.loads(f.read_text())
    if p.get("completedThrough", 0) < p.get("chunkTotal", 0):
        continue
    h = p.get("sourceHash", "")[:16]
    if h not in cached_hashes:
        orphans.append({"name": p.get("sourceIdentity"), "hash": h})

print(f"orphans in _backup not in cache: {len(orphans)}")
for o in orphans: print(f"  {o['hash']}  {o['name']}")
print(f"queue entries for same files:  {sum(1 for n in queue_names if any(n in o['name'] for o in orphans))}")
```

If any one is missing, you have a desync. Pattern 5 detects the most common flavor.

### `lint.json` (wiki health scan — mechanical)

Mechanical scan of all `wiki/**/*.md` wikilinks + cross-page references. Schema (v0.4.23):

```json
[
  {
    "type": "broken-link",   // or "orphan" or "no-outlinks"
    "severity": "warning",   // or "info"
    "page": "entities/何友.md",
    "detail": "Broken link: [[雷达数据处理及应用]] — target page not found.",
    "id": "lint-9883",
    "createdAt": 1781083836725
  }
]
```

**Type matrix** (empirically observed):
| type | severity | meaning | action |
|---|---|---|---|
| `broken-link` | warning | A `[[wikilink]]` points at a non-existent page | Fix or dismiss — see `references/broken-link-repair-workflow.md` |
| `orphan` | info | A page that no other page links to | Add inbound links, or ignore (newly-created pages are orphans by definition) |
| `no-outlinks` | info | A page with no outbound `[[wikilink]]` | Add cross-references, or ignore (single-source pages) |

**Key facts**:
- `lint.json` is **re-derivable on every app scan**. The app scans `wiki/**/*.md`, parses wikilinks, and rewrites the file. Manually editing it is a no-op unless the underlying file change persists.
- `severity` is the agent's actual priority — `info` items are non-actionable. Filter on `severity == "warning"` when triaging.
- `detail` includes the broken target inside `[[...]]` — parse with a regex `\[\[([^\]]+)\]\]` to extract for triage.
- `id` is stable across rescans for the same violation; `createdAt` is the first-detection timestamp.
- **Don't conflate `lint.json` and `review.json` counts**. The lint scan finds ALL broken links; the LLM review picks a subset. The two will disagree by an order of magnitude — that's by design (lint = mechanical; review = LLM-curated priority).

### `review.json` (LLM-curated review items)

Array of review items the LLM produced on digest completion. Schema (v0.4.23):

```json
[
  {
    "type": "confirm",            // or "suggestion" / "missing-page" / "contradiction" / "duplicate"
    "title": "修复 entities/何友.md 中的失效链接",
    "description": "Broken link: [[雷达数据处理及应用]] — target page not found.",
    "status": "none"              // or "dismissed" / "resolved" / etc. (none = unprocessed)
  }
]
```

**Type matrix**:
| type | meaning | agent action |
|---|---|---|
| `confirm` | "Should we make this change?" — usually broken-link fixes the LLM has high confidence in | Verify the suggested fix is real, then either apply or dismiss with reason |
| `suggestion` | "Consider doing X" — adds cross-reference, expands stub, etc. | Judgment call; show user, get decision |
| `missing-page` | A wikilink target that should have a page but doesn't | Decide: create stub / link to existing equivalent / dismiss |
| `contradiction` | Two pages disagree on a fact | Read both, present the contradiction, let user adjudicate |
| `duplicate` | Two pages overlap significantly | Propose merge target |

**Status field lifecycle** (v0.4.23):
- `status: "none"` (or missing) — unprocessed
- `status: "dismissed"` — agent decided to skip; record `dismissedAt` + `dismissedReason` (this skill's workflow)
- The app may also accept `"resolved"` after a real fix

**Key facts**:
- `status: "none"` on every item is the **default state for an uncurated wiki**. The presence of items is normal — they accumulate over time.
- `review.json` items DO reappear across digests if the underlying issue isn't actually fixed (e.g. broken link still broken). Dismiss is a valid permanent resolution.
- **The `description` field often duplicates the broken-link's target** as a `[[...]]` token — same parse regex as `lint.json`.
- Reasoning-mode override (see "Reasoning mode scope matrix" above) applies to review-item generation: it's auto-forced off in v0.4.23+, so don't expect longer/thorougher review items just because you cranked up `reasoning.mode`.

### Pattern 6: "Are review.json and lint.json out of sync?"

Expected ratio: `review.json.size ≈ 0.10–0.20 × lint.broken-link-count` (LLM picks 10-20% of the mechanical findings as priority). If the ratio is way off:

- Ratio < 0.05: app hasn't run the LLM review pass recently (review is generated on digest completion + periodic scan)
- Ratio > 0.50: the LLM review is over-reporting — possibly because the wiki is in a "stale" state and many broken links cluster in one place

Use this ratio as a coarse health check, not a strict rule.

## File map summary

The `ingest-progress/` → `ingest-progress/_backup/` → `ingest-cache.json` chain is the app's digest lifecycle. A digest completes when all three are in agreement:
- `ingest-progress/_backup/<slug>-<hash>.json` exists with `completedThrough == chunkTotal`
- `ingest-cache.json` has an `entries[<name>].hash` matching the backup's `sourceHash` (or a prefix thereof)
- `ingest-queue.json` does **not** contain a `pending`/`processing` entry for the same `sourcePath`

If any one is missing, you have a desync. Pattern 5 detects the most common flavor.
