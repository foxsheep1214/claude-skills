---
title: Broken-link repair workflow
date: 2026-06-10
updated: 2026-06-10
trigger: User says "fix the broken links in my wiki" / "处理 review 里的 confirm" / "wikilink 全部修一遍" — or any "B 类" triage question.
purpose: Step-by-step playbook for triaging + repairing `review.json` `confirm` items (broken wikilinks). Codifies the 5-bucket triage, the frontmatter+body double-fix pitfall, the stub template, and the status-reporting discipline.
---

# Broken-link repair workflow

When `review.json` has `confirm` items (or the user reports broken wikilinks), follow this exact sequence. Each step is mandatory — skipping triage leads to either over-edits (creating 50 useless acronym stubs) or under-edits (missing the C-class "page exists with a different name" wins that account for 20%+ of fixes).

## 0. Run the comprehensive wikilink audit FIRST

Before touching `review.json`, run `scripts/wikilink-audit.py` against the wiki tree. This is the **ground truth** — `review.json` only carries ~10-20% of broken links (LLM-prioritized); `lint.json` is re-derivable and may be stale. The audit walks every `wiki/**/*.md`, resolves every `[[wikilink]]` against the actual page tree, and reports:

- Total unresolved refs + unique targets
- Value buckets (D/A/A'/B/F)
- High-frequency targets cited ≥3 times (the D-bucket — top priority)
- Source-file rollup (which files contribute the most unresolved refs)

```bash
python3 ~/.agents/skills/llm-wiki-local/scripts/wikilink-audit.py ~/Documents/知识库/RadarWiki
```

Use this to discover the **D-bucket** (e.g. `janus天线配置` cited 6 times — `review.json` may not even list it as a confirm item if the LLM didn't flag it). The audit is what catches the items the LLM review missed.

The audit and `wiki_triage.py` are complementary:
- `wiki_triage.py` reads ONLY `.llm-wiki/*.json` state files (review, lint, queue, progress)
- `wikilink-audit.py` reads the `wiki/**/*.md` tree directly

Run both. The triage tells you "what does the app think needs fixing"; the audit tells you "what's actually broken on disk".

## 1. Triage: 5 buckets

Pull every `confirm` item's `description`, regex-extract `\[\[([^\]]+)\]\]` to get the broken target. Then classify each target into one of five buckets:

| Bucket | Definition | Frequency (RadarWiki 2026-06-10 sample) | Action |
|---|---|---|---|
| **D — high-freq, no page, top priority** | Target is cited ≥3 times across the wiki but has no existing page (e.g. `janus天线配置` cited 6 times across 6 different pages) | ~1% of items, but the absolute highest-value win | Stub immediately, no judgment call needed |
| **C — page exists, name mismatch** | Target's words appear in some `wiki/**/*.md` filename but with a different suffix (e.g. target `相控阵雷达资源管理技术` vs file `相控阵雷达资源管理技术 - 2016 - 毕增军.md`) | ~20% of confirm items, biggest single win | Edit the `[[wikilink]]` to include the suffix, do NOT create a new page |
| **A — real concept worth stubbing** | Target is a real radar/signal-processing term (e.g. `功率谱密度`, `海浪谱`, `超低副瓣`) that genuinely should have a page | ~40% of items | Create a stub page (template below) and link from at least one related page |
| **B — acronym / model name / proper noun** | Target is a multi-letter acronym (EIK, UWB, MPM, X-45C, Warloc) or a person (Merrill-Skolnik, Prentice-Hall) — these are SKOLNIK handbook source-text references that don't carry wiki meaning on their own | ~30% of items | Dismiss with reason "source-text reference, not a wiki concept" |
| **A' — niche terminology, judge case-by-case** | Target is a real concept but only cited once and in a low-value context (发射机分类与选型, 速调管MTBF) | ~10% of items | Default to dismiss unless the user flags it as important |

**Heuristic for A vs A'**: target appears in ≤1 source → A' (dismiss). Target appears across multiple sources or in a "core" RadarWiki concept area (spectral analysis, signal processing, antennas, propagation) → A (stub). **D-bucket override**: if a target is cited ≥3 times regardless of single-source context, promote it to D (the user wants this fixed — high citation count = high value).

**F-bucket** (URL/regulation numbers like `DoDI-5000.88`, `IEEE-15288.2`) is auto-detected by the audit script and is always dismiss.

## 2. Extract targets with frequency (mandatory first step)

```python
import json, re
from pathlib import Path
from collections import Counter

llm = Path("~/Documents/知识库/<project>/.llm-wiki").expanduser()
rev = json.loads((llm/"review.json").read_text())
broken = [i for i in rev if i.get("type") == "confirm"]

# Extract every [[target]] from every confirm item's description
target_items = {}
for i in broken:
    for t in re.findall(r"\[\[([^\]]+)\]\]", i.get("description", "")):
        target_items.setdefault(t, []).append(i)

# Frequency-sorted → bucket assignment is now mechanical
for t in sorted(target_items.keys(), key=lambda x: -len(target_items[x])):
    n = len(target_items[t])
    print(f"  x{n:2d}  {t}")
```

A target with `n >= 2` is almost always **bucket C** (page exists with a slightly different name; many places refer to it). `n == 1` is either A, A', or B — read the source page's context to decide.

**Don't trust `n` from `review.json` alone.** The audit script's `target_count` is the ground truth (counts every `[[target]]` across all `wiki/**/*.md`, not just the ones in `review.json`). Some high-frequency targets (D-bucket) may have ZERO entries in `review.json` if the LLM review didn't flag them.

## 3. C-bucket: rename-link, do NOT create page

For each C-bucket target, find the actual existing page(s) by name fuzzy match:

```python
proj = Path("~/Documents/知识库/<project>")
wiki = proj / "wiki"
all_files = list(wiki.rglob("*.md"))

target = "相控阵雷达资源管理技术"
candidates = []
keys = ["相控阵", "资源管理"]  # split target by hand
for f in all_files:
    if all(k in f.stem for k in keys):
        candidates.append(str(f.relative_to(proj)))
print(candidates)
# → ['wiki/sources/相控阵雷达资源管理技术 - 2016 - 毕增军.md',
#    'wiki/concepts/相控阵雷达资源管理.md']
```

Pick the most specific page (usually the source page when the target is a book title), then **edit every wikilink** that pointed at the bare target to point at the full filename (without `.md`). Edit **frontmatter `related:` AND body `[[...]]`** — see pitfall §5.

## 4. A-bucket and D-bucket: create stub with this template

The wiki uses frontmatter-style `---` blocks. A stub page should be **2-3 paragraphs, no fluff**:

```markdown
---
type: concept
title: <target>
tags: [<field>, <subfield>, <technique>]
related: [<closely-related-concepts>]
sources: ["<source-book-or-paper.pdf>"]
created: 2026-06-10
updated: 2026-06-10
---

# <target>

**<target>** (<English name>, <acronym>) is a <one-sentence definition>.

## <Core principle / formula>

<2-5 lines of math or technical content. If you have a formula, typeset in $\LaTeX$ (LLM Wiki renders math). If you have no source content (the source PDF is image-only / OCR-failed), say so explicitly and stop — don't fabricate technical depth you don't have.>

## <Application or limitation>

<1-2 lines on where it's used in the radar/signal-processing domain, OR a known limitation.>
```

**Stub content-depth heuristic (from RadarWiki 2026-06-10 session)**:
- **D/A-bucket with extractable source PDF** (e.g. `Stoica Spectral Analysis` — has clean `.cache/*.txt` with full TOC): write 2-3 paragraphs of real technical content. The source is there, use it.
- **D/A-bucket with image-only source PDF** (e.g. `Skolnik Radar Handbook`, `Barton Radar System Analysis` — `.cache/*.txt` is just page numbers): write 1-2 paragraphs of definition-level content. Don't fabricate equations or claims you can't back.
- **A' with single-source citation**: probably should be dismissed (§6), not stubbed.

**Stub anti-patterns (don't do these)**:
- ❌ Long frontmatter with 10 tags you made up
- ❌ Verbatim copy of the Wikipedia opening sentence (the wiki is for the user's own knowledge, not a Wikipedia mirror)
- ❌ Multi-section essays for a concept you've only seen cited once (that's A', not A — should have been dismissed)
- ❌ Stub that links back to the source page that already contained the link (circular noise)

**Length target**: 30-60 lines total including frontmatter. Less than that = too thin to be useful. More than that = you probably don't have source material to justify it.

## 5. The frontmatter + body pitfall (this WILL bite you)

**Wikilinks exist in TWO places** in any wiki page:

1. **Frontmatter `related:` field** — e.g. `related: [雷达数据处理及应用, ...]`
2. **Body `[[wikilink]]` references** — e.g. `与[[雷达数据处理及应用]]条目对应`

**`lint.json` and `review.json` BOTH scan both**. If you only fix one, half the broken links stay.

**Verification command (run after every C-bucket edit batch)**:

```bash
rg '\[\[<target>\]\]' wiki/ -l    # body references
rg '<target>' wiki/ -l             # frontmatter + body, but expect false positives
rg '\[\[<bare-target>\]\]' wiki/ -l  # SPECIFICALLY the broken bare target
```

Run this for every C-bucket target. If the third command still returns files, you missed a body reference.

**Lesson from 2026-06-10 session**: when editing `entities/X.md` and `sources/Y.md` for a C-bucket, the related-page in `index.md` is **also a source file** that may reference the bare target — don't forget index.md, overview.md, log.md, and queries/*.md. Run a final `rg '\[\[<target>\]\]' wiki/` after the batch to confirm zero residue.

## 6. Dismiss B, A', and F buckets in review.json

When dismissing, set three fields (don't just remove the item — that breaks audit trail):

```python
import json, time
ts_ms = int(time.time() * 1000)
for i in rev:
    if i.get("type") == "confirm" and <this target matches>:
        i["status"] = "dismissed"
        i["dismissedAt"] = ts_ms
        i["dismissedReason"] = "<why>"  # e.g. "source-text acronym, not a wiki concept"
```

Common reasons to log:
- `"source-text acronym (Skolnik handbook), not a wiki concept"`
- `"niche term with single citation, not worth a stub"`
- `"proper noun / person name, no wiki page needed"`
- `"page already exists with different name; fixed at source"` (C-bucket — also for audit clarity)
- `"URL / regulation number, no wiki page needed"` (F-bucket)

## 7. lint.json: don't bother editing (it's re-derivable)

The app rescans `wiki/**/*.md` periodically and **rewrites `lint.json` from scratch**. If you manually delete broken-link entries, they'll reappear on the next scan (if the underlying wikilink is still broken) or vanish (if you actually fixed the wikilink). The only state-changing action that persists is the wiki-file edit itself.

**Status-reporting discipline**: when you tell the user "I removed N broken links from lint.json", you MUST also report:
- (a) Engineering: N entries filtered out of `lint.json` array
- (b) Goal: zero of those targets still appear in any `[[...]]` across the wiki; verify with `rg '\[\[<target>\]\]' wiki/`

If (b) is false, the report is misleading. The lint.json deletion is cosmetic.

## 8. Backup before bulk edits (mandatory)

```bash
mkdir -p ~/.hermes/backups/radarwiki-broken-links/$(date +%s)
cp <project>/.llm-wiki/{review,lint}.json ~/.hermes/backups/radarwiki-broken-links/$(date +%s)/
```

Two timestamps recommended — one before triage (in case you need to inspect what was there), one before the dismissals (in case you over-dismissed and need to recover the items).

## 9. The "ask for the B-bucket threshold" decision

When the user says "fix all confirm items" but the items include 25+ acronyms (B bucket), ask once before mass-dismissing. Suggested phrasing:

> "B 类有 25 条缩写（EIK, UWB, X-45C, Warloc ...）— 只补有 wiki 价值的少数，还是全部建 stub，还是全部 dismiss？"

The user usually picks "只补少数, 其他 dismiss" or "全部 dismiss" — both are defensible. Don't pick for them.

**If the user does not respond (clarify times out)**, default to "只补高价值的少数，其他 dismiss" — apply the D-bucket override (cite-count ≥3 wins) and stub the top ~10 highest-frequency concepts. Never go silent and never mass-stub 50 acronyms.

## 10. End-of-task status report (REQUIRED)

After all edits + status updates, report using 双栏 format:

| | 工程执行 | 目标达成 |
|---|---|---|
| C-bucket | N wikilinks edited across M files | M files re-grep'd, zero bare-target references remain |
| D/A-bucket | K stub pages created in `wiki/concepts/` | K new frontmatter entries verified |
| B/A'/F dismiss | N review items set to `status="dismissed"` with reason | next lint scan will reflect N fewer broken-link warnings (not verifiable until app re-scans) |
| lint.json | 389 broken-link entries removed from array | will be regenerated on next app scan — count will drop to actual count of remaining broken links |
| wikilink-audit.py | (rerun) unresolved-refs count: 460 → 449 | unresolved-unique-targets: 450 → 445 |

If any cell in "目标达成" is unchecked, say so explicitly. Don't claim the wiki is "clean" based on having edited JSON files.

## 11. Known false-pitfalls

- ❌ **Editing `lint.json` and `review.json` as primary state** — they're regenerable. Fix the actual `wiki/**/*.md` files.
- ❌ **Creating a page when the user said "dismiss"** — they may have a reason (e.g. they don't want wiki clutter from acronyms).
- ❌ **Forgetting to update `related:` frontmatter** — half the broken links stay.
- ❌ **Trusting the bare `description` field in review.json** — it sometimes contains paraphrases, not exact wikilink tokens. Always regex-parse `[[...]]` from the raw field.
- ❌ **Skipping the existence check before creating a stub** — there may already be a `wiki/concepts/<target>.md` with slightly different frontmatter. Always `ls` first.
- ❌ **Trusting `review.json` count as the universe of broken links** — it carries only the LLM-prioritized subset. Run `wikilink-audit.py` to see ground truth.

## 12. Quick "do I have work to do" check

```python
import json
from pathlib import Path
llm = Path("~/Documents/知识库/<project>/.llm-wiki").expanduser()
rev = json.loads((llm/"review.json").read_text()) if (llm/"review.json").exists() else []
unprocessed = [i for i in rev if i.get("status") in (None, "none")]
print(f"{len(unprocessed)} unprocessed review items, {len(rev)} total")
# By type
from collections import Counter
print(Counter(i.get("type") for i in unprocessed))
```

If `unprocessed == 0` AND `lint.json` has zero `severity: warning` items → wiki is "clean" by these two signals. Re-scan still useful for the next digest.

**Pair this with `wikilink-audit.py`** for a complete picture:

```bash
python3 ~/.agents/skills/llm-wiki-local/scripts/wiki_triage.py <project>
python3 ~/.agents/skills/llm-wiki-local/scripts/wikilink-audit.py <project>
```

The triage tells you "what the app flagged", the audit tells you "what's actually broken on disk". They can disagree — and they often do (audit typically shows ~5-10x more broken links than triage).
