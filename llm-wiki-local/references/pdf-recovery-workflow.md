---
title: PDF-recovery query workflow — what to do when the user says "处理这个 query"
date: 2026-06-10
trigger: User says "处理 query/<file>.md" (Category 1, PDF-recovery), or asks "处理这个 query 一下" / "把这个查询做了", or hands you a `wiki/queries/<book>-文本恢复.md` to advance.
purpose: End-to-end workflow for making substantive progress on a Category 1 PDF-recovery work order. The companion to `queries-directory.md` (which classifies them) — this reference prescribes what to *do* with one once it's in the queue. Codified from the 2026-06-10 RadarWiki session where 卡里拉斯《ESRS 设计手册》was diagnosed in depth.
---

# PDF-recovery query workflow

The user keeps these queries around as **standing work orders**. They sit in `wiki/queries/` until somebody (the user, you, or a background pipeline) actually acts. "处理" a query means *making real, verifiable progress* — not just rewriting the file or moving status from "未启动" to "进行中".

## Step 0: Verify the query is actually Category 1

Quick classification (don't trust filenames alone):

```python
import re
from pathlib import Path

q = Path("<project>/wiki/queries/<name>.md")
text = q.read_text()
fm = re.match(r'^---\n(.*?)\n---', text, re.DOTALL).group(1)

is_cat1 = (
    'origin:' not in fm                             # not a deep-research
    and not q.name.startswith('research-')          # not a research file
    and ('PDF' in text or 'OCR' in text or '文本恢复' in text or '文本提取' in text)
)
```

If `is_cat1` is False, see `queries-directory.md` for the other 4 categories.

## Step 1: Diagnose the PDF state — don't trust the query's claims

The query is the user's *work order*, not the truth. **Verify everything** before doing OCR/minerU work:

```python
import fitz  # PyMuPDF — already in /Users/skyfend/.hermes/hermes-agent/venv

PDF = "<project>/raw/sources/<book>.pdf"
doc = fitz.open(PDF)

# Core state probe
print("page_count:", doc.page_count)
print("toc:", doc.get_toc())              # bookmarks can be a TOC hint
print("metadata:", doc.metadata)          # producer, creator, creationDate

# Text layer check (do NOT skip — "all images" sometimes has hidden text)
total_chars = 0
empty_pages = 0
for i in range(doc.page_count):
    text = doc[i].get_text()
    total_chars += len(text.strip())
    if not text.strip():
        empty_pages += 1
print(f"text chars: {total_chars}; empty pages: {empty_pages}/{doc.page_count}")

# Image per page = scan confirmation
from collections import Counter
exts = Counter()
for i in range(doc.page_count):
    for img in doc[i].get_images(full=True):
        exts[doc.extract_image(img[0])["ext"]] += 1
print("image exts:", exts)
```

**Strong signals of a "scanned PDF" (text truly absent)**:
- All pages have ≥1 image
- All images are PNG (not JPEG — IRIS scanners often output PNG)
- `get_text()` returns empty for all pages
- `metadata["producer"]` contains "IRIS" or "Adobe Scan" or "VueScan" or "WIA-"

If text is actually present, the query is misclassified — go back to user, don't OCR a layer that exists.

## Step 2: Check whether ingest has already been attempted

```python
import json
from pathlib import Path

proj = Path("<project>")
llm = proj / ".llm-wiki"

# Has this book been digested?
cache = json.loads((llm / "ingest-cache.json").read_text())
key = "<book>.pdf"
if key in cache.get("entries", {}):
    print("ALREADY DIGESTED:", cache["entries"][key])
    print("filesWritten:", cache["entries"][key].get("filesWritten", []))

# Has it been split for OCR/minerU?
split_dir = llm / "_pdf_split" / "<book>"
if split_dir.exists():
    parts = sorted(split_dir.glob("*.pdf"))
    print(f"PDF split into {len(parts)} parts: {[p.name for p in parts]}")

# Has any part been processed by minerU vlm?
out_dir = llm / "_pdf_split_out"
if out_dir.exists():
    for d in out_dir.iterdir():
        if "<book>" in d.name or any("<book>" in str(s) for s in d.rglob("*")):
            print(f"minerU output for {d.name}: exists")
```

**Common surprise**: the user (or a prior session) has already split the PDF and even kicked off minerU on some parts. Don't redo the split.

## Step 3: OCR-validate key metadata — fix the wiki entries

This is the **most valuable single action** you can take on a PDF-recovery query, because it turns a 0-information entry into real wiki content.

**Tooling (already in `~/.hermes/hermes-agent/venv/`, no install needed)**:
- Python: `/Users/skyfend/.hermes/hermes-agent/venv/bin/python3`
- Has: PyMuPDF (`fitz`) 1.24.x, pytesseract 0.3.13
- Tesseract binary: `/opt/homebrew/bin/tesseract`
- Tesseract languages: `/opt/homebrew/share/tessdata/chi_sim.traineddata` (Chinese simplified, ~50 MB)

**Working OCR configuration** (validated 2026-06-10, 卡里拉斯 ESRS handbook):

```python
import fitz, pytesseract, io
from PIL import Image

PDF = "<project>/raw/sources/<book>.pdf"
doc = fitz.open(PDF)

# Cover (page 1), translator's preface (page 2), TOC (page 7-8), body (page 10+)
SAMPLE_PAGES = [0, 1, 5, 6, 7, 8, 9, 10]  # 0-indexed

for page_idx in SAMPLE_PAGES:
    if page_idx >= doc.page_count:
        continue
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=400)            # 400dpi is the sweet spot
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    # PSM=6 = "uniform block of text" — best for prose/tables in books
    text = pytesseract.image_to_string(img, lang="chi_sim+eng", config="--psm 6")
    print(f"=== Page {page_idx+1} ===\n{text}\n")
```

**What to look for in the OCR output** (and the corrections they trigger):

| What you'll see | What it corrects in the wiki |
|----------------|-----------------------------|
| Author name on cover / preface | `entities/<author>.md` frontmatter `name` field, and any source page that says just "Carlson" |
| English book title (often on title page in italic / cover) | `wiki/sources/<book>.md` English title field (commonly miswritten by the LLM that wrote the stub) |
| "一九七X年" date in preface | `wiki/sources/<book>.md` year field (Chinese-translated books often have year-of-translation ≠ year-of-original) |
| TOC entries (chapters + page numbers) | Replaces any "推测章节" or "Part I-VI" placeholder in `wiki/sources/<book>.md` and `wiki/queries/<book>-文本恢复.md` |
| Translator credits in preface | `wiki/sources/<book>.md` translator field; valuable for cross-referencing the original English edition |

**The CardBook trap**: don't OCR the whole 288-page book at 400dpi — it takes 5-10 minutes and uses lots of CPU. Sample the cover + preface + TOC + first body page is enough to (a) confirm OCR works for this book, (b) extract all the metadata the wiki needs to stop being a stub.

## Step 4: Update the wiki entries — find every place the wrong fact lives

After OCR verification, the same wrong fact often lives in 3-5 places. Use a search to find them all:

```bash
grep -rn "Electronically Scanned Array Radar Design Handbook" \
    /Users/<user>/Documents/知识库/<project>/wiki/
```

**Common locations to update**:

1. `wiki/queries/<book>-文本恢复.md` (the work order itself) — main body has a "## 当前状态" block
2. `wiki/entities/<author>.md` (if author page exists) — frontmatter `name` + body table
3. `wiki/concepts/<topic>.md` (if concept page exists) — "## 历史背景" or similar section
4. `wiki/sources/<book>.md` — 来源基本信息 block
5. `wiki/sources/research-<topic>-<ts>.md` (if a research file was mis-categorized here) — `status: 已替代` + `superseded_by`
6. `wiki/queries/research-<topic>-<ts>.md` (the duplicate) — same treatment
7. `wiki/log.md` — append the new ingest/verify entry

**Verify the cleanup is complete**:

```python
# Should print only the warning/banner lines, not the actual content
from pathlib import Path
wrong = "Electronically Scanned Array Radar Design Handbook"  # the bad title
right = "Electronic Scanning Radar Systems (ESRS) Design Handbook"  # the right title
for f in Path("<project>/wiki/").rglob("*.md"):
    if wrong in f.read_text() and right not in f.read_text():
        print(f"STILL CONTAINS ONLY WRONG TITLE: {f}")
```

## Step 5: Disposition the duplicate research file — use superseded_by, not delete

When `wiki/queries/<book>.md` and `wiki/queries/research-<book>-<ts>.md` both exist (Category 5 duplicate), the right move is **not** deletion. The research file is a snapshot of when the query was first answered; deleting it loses context.

**Standard pattern** (applied to both copies — they may both exist):

```markdown
---
type: query
title: "Research: <book> 文本恢复"
created: 2026-06-10
origin: deep-research
tags: [research, 已替代, 推测性内容]
related: [<book>-文本恢复]
supersedes: false
superseded_by: <book>-文本恢复
---

> ⚠️ **本文件已被取代（<date>）** — 本文件是早期 deep-research 的"未确定作者""推测章节框架"版本。
> 经直接 OCR PDF 扫描页验证：作者确认为 <author>、英文书名为 <title>、真实目录为 <chapters>。
> 完整诊断与更新已合并到主 query 文件 [[<book>-文本恢复]]，请以主文件为准。
> 本文件保留作为历史追溯记录，不应再被引用为权威信息。
```

Also do the same to the mirror copy in `wiki/sources/research-<book>-<ts>.md` (LLM Wiki sometimes writes research output to BOTH locations — the `sources/` copy is mis-classified as a source file but is actually a research process artifact).

## Step 6: Write a substantive query file — make it the new authoritative work order

The rewritten query file should be **the single place** a future agent reads to understand:
- What's been done (date + method)
- What's still pending (with concrete next actions, not vague plans)
- The cross-project picture (other PDFs in the same systemic batch)

**Structure that works** (from the 卡里拉斯 2026-06-10 rewrite):

1. **TL;DR status line** at top: `> 进行中 — <what's done in one line>, <what's next in one line>`
2. **Key metadata table** with `(OCR 已验证, <date>)` flag on each row — so the next agent knows which facts come from primary evidence vs. inference
3. **"需修正的既有错误" section** with a before/after table of mistakes found in existing wiki pages
4. **Real structure** (chapter list, not "Part I-VI" guesses)
5. **"已完成动作" dated list** — every action taken with date
6. **Cross-batch table** — if 5 PDFs have the same problem, list all 5 with their split/process state, so a batch minerU job can be scoped
7. **"待办（下阶段，需胡杨授权后启动）"** with two tiers: (a) no-resource-needed housekeeping, (b) long-pipeline-awaiting-authorization

## Step 7: Log the work

Append to `wiki/log.md`:

```
## 2026-06-10 OCR 验证 | <book> 文本恢复 — 关键元数据修正

- **方法**：<one line: tool + config>
- **PDF 状态确认**：<page count, text presence, image exts>
- **关键元数据修正**（已写入主 query [[...]]）：
  - <old> → <new>
- **真实目录**（OCR 直接抽取，PDF 内置目录页）：<real structure>
- **<N> 本系统性问题汇总**（均在 .llm-wiki/_pdf_split/ 拆好 Parts）：
  - <book 1>: <pages> → <parts> (<minerU status>)
  - ...
- **更新文件**：<list of files>
- **后续（待胡杨明确授权）**：<next batch action>
```

## Pitfalls

- **Don't trust the query's claims.** The 卡里拉斯 query said "1975" (wrong — actually 1976) and "*Electronically Scanned Array Radar Design Handbook*" (wrong — actually ESRS Design Handbook). Always OCR-verify before propagating.
- **Don't OCR the whole book in one shot.** 288 pages × 400dpi × PSM=6 takes 5-10 min of CPU. Sample 8-12 strategically-chosen pages.
- **Don't delete the duplicate research file.** The user's instinct to triage is right, but the research file has context. `superseded_by` is the right disposition.
- **Don't update only the query file.** Wrong metadata lives in entity / concept / source pages too. Search globally.
- **Don't trust `ingest-cache.json` "filesWritten" to mean "real content".** The cache says the LLM write happened, but if the LLM had no text to digest, all the .md files are stubs with "无法获取实质性内容" disclaimers. Verify with `get_text()` on the actual .md file.
- **Don't auto-start minerU.** The user has memory "长 background pipeline 逐步授权" (long pipeline stepwise authorization). Document what's ready to run, but wait for explicit go.
- **Don't conflate "frontmatter updated" with "body updated".** Tables in body often repeat the same frontmatter fact. Patch both.

## See also

- `references/queries-directory.md` — the 5 categories + triage classifier
- `references/broken-link-repair-workflow.md` — the OTHER backlog (review.json `confirm` items)
- `references/llm-wiki-state-files.md` — the 4 ingest state files
- `SKILL.md` § "Ingest queue internals" — for minerU pipeline internals
- `SKILL.md` § "Ingest diagnostics (stuck/failed queue)" — when minerU is the right next step
