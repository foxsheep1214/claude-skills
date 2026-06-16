---
name: improved-wiki
description: "Class-level umbrella for the Karpathy/NashSU LLM-Wiki ingestion pipeline (autoIngestImpl + 17 mandatory Stages). Use when ingesting a PDF/PPTX/DOCX into a wiki project (HardwareWiki, RadarWiki, 全知全能, or any project using NashSU LLM Wiki app ≥ v0.4.22), validating an existing ingest against the 15-stage checklist, debugging stuck/failed/re-queued ingest tasks, or auditing a project's wiki structure for completeness. Covers mandatory stages, image extraction + captioning, global digest + chunk analysis, multi-round generation, review suggestions, cache hash discipline, and the scan-PDF OCR pipeline. **Stage 0 OCR (pilot + full-book) uses local minerU (free, auto-extracts images).**"
tags: [ingest, mandatory, nashsu, pipeline, scan-pdf, mineru, local-ocr, retry]
related_skills: [karpathy-llm-wiki, mineru-document-parsing, llm-wiki-local]
---

# improved-wiki — LLM-Wiki 17-Stage Ingest Pipeline (umbrella)

This skill governs the Karpathy LLM-Wiki ingest pattern + NashSU LLM Wiki app (v0.4.23) pipeline. Anything that touches a wiki project's ingest stages (validation, debugging, recovery, multi-source batch ingest) belongs here.

## Entry point

**Always start with `references/ingest-stages-mandatory.md`** — that's the 15-stage authoritative checklist with go/no-go gates. Then load other references as needed.

## Reference map

- `references/ingest-stages-mandatory.md` — **AUTHORITATIVE** 17-stage checklist (Stage 0 path A vs path B, ⭐-marked easy-to-skip stages, project methodology boundary). **Stage 0 OCR (pilot + full-book) uses local minerU** (free, auto-extracts images, no API key needed). Stage 2.1 (source/concept/entity) → 2.2 (query) → 2.3 (comparison) pipeline added 2026-06-16.
- `references/query-generation.md` — **Stage 2.2** prompt template for auto-generating `wiki/queries/` pages (open questions from single-source analysis). Skip condition: datasheet/standard.
- `references/comparison-generation.md` — **Stage 2.3** prompt template for auto-generating `wiki/comparisons/` pages. 2.3A (disambiguation), 2.3B (in-source concept contrast), 2.3C (cross-source contrast — suggestion only).
- `references/multimodal-vlm-pitfalls.md` — VLM model pitfalls (MinerU 2.5-Pro 1.2B caption collapse, mmx caption quality vs OCR brittleness).
- `references/image-caption-strategy.md` — captioning 3-way decision tree (single-batch API / Message Batches / mmx fallback).
- `references/raw-layout-compat.md` — Karpathy raw/ layout + NashSU wiki/ compatibility rules.
- `references/naming-conventions.md` — **AUTHORITATIVE** file naming, frontmatter, wikilink, and directory conventions (NashSU-aligned). Now includes `domain` field for disambiguation.
- `references/domains.md` — **AUTHORITATIVE** domain classification list for disambiguation and cross-domain linking.
- `templates/disambiguation.md` — template for creating disambiguation pages when one term has different meanings across domains.
- `templates/overview.md` — LLM-maintained comprehensive overview of ALL wiki topics; rewritten on every ingest with strong/weak claims and open questions.
- `templates/schema.md` — page type to directory mapping table (source, concept, entity, query, comparison, synthesis, finding, thesis, methodology).
- `templates/log.md` — append-only log template; the ingest pipeline writes INGEST / LINT / QUERY entries here.
- `templates/index.md` — LLM-updated index of all wiki pages organized by type (sources, concepts, entities, queries, comparisons, findings, synthesis, media, methodology).
- `references/nashsu-lint-source-analysis.md` — reading NashSU app's lint.json to find issues.
- `references/scripting-pitfalls.md` — broader Python + agent tool pitfalls.
- `references/kb-retrieval.md` — **AUTHORITATIVE** 4-step knowledge retrieval workflow (search → read → cite → declare). Keyword strategies, citation format, anti-patterns.
- `references/known-issues.md` — current known bugs and their workarounds.
- `references/initial-setup.md` — first-time project bootstrap.
- `references/cron-installation.md` — automated ingest via cron.
- `references/batch-digest-loop.md` — **批量消化**：用 Python 循环调用 `ingest.py` 逐本处理待消化书籍，支持断点续传，无需 GUI。

## Templates

8 templates by file type — book / paper / datasheet / applicationnote / designexample / presentation / standard / news. Copy and modify per project.

## Key Features (2026-06-16)

- **Batch mode with parallel Stage 0-2** — `ingest.py file1.pdf file2.pdf ...` processes multiple books concurrently during read-only LLM phases (Stage 0-2), then serializes shared-state writes (Stage 3+). Use `--parallel N` to control concurrency (default: 4).
- **Queue-based watch mode** — `ingest.py --watch` runs as a daemon consuming `ingest-queue.json`. New entries added mid-run are picked up between waves. `--drain` exits when the queue is empty. `--poll-interval N` controls re-scan frequency (default 30s). `--max-retries N` caps per-entry retries (default 3).
- **Configurable Stage 1.5 chunk parallelism** — `LLM_CHUNK_CONCURRENCY` env var controls max concurrent chunk analysis workers (default 8). `LLM_CHUNK_RETRIES` sets extra attempts per failed chunk (default 2). Rate-limit awareness: if any worker hits 429/503, all workers pause 3s before retrying.
- **Per-chunk generation** — Multi-chunk books use per-chunk parallel generation instead of one big synthesis. Each chunk's Stage 1.5 analysis independently generates concept/entity pages for its section. Coverage improves from ~10% to ~60-100% for large books.
- **Coverage gates** — Chunk analysis classifies concepts as core/supporting/mentioned. Legacy synthesis enforces core ≥80%, supporting ≥50%. Per-chunk mode achieves natural coverage by design.
- **Auto-validation** — `validate_ingest.py` runs automatically at the end of every ingest. 17/17 stages verified with fresh evidence before claiming completion, including Stage 0 pilot check for minerU-processed sources.
- **Stage verification gates** — Each stage has `_verify_stage_N()` checks that abort on hard failures (e.g., 0 FILE blocks, empty text extraction). Global digest now verifies all 6 required keys (book_meta, outline, key_entities, key_concepts, key_claims, chunk_plan).
- **Pipeline mode** — The first book whose Stage 2.1 completes starts writing immediately; no need to wait for all books. Stage execution order: `2.1 → 2.2 → 2.3 → 3 → 3.5 → 2.5 → 2.6` (review runs against written files for human inspection).

## Scripts

### Core Pipeline
- `scripts/ingest.py` — **full 15-stage runner**. Supports single-file, batch (`--parallel N`), queue watch (`--watch`, `--drain`, `--poll-interval N`, `--max-retries N`), and conversation mode. Env vars: `LLM_CHUNK_CONCURRENCY` (default 8), `LLM_CHUNK_RETRIES` (default 2).
- `scripts/_paths.py` — shared runtime directory detection (`.llm-wiki/` default, auto-migrates from `.iwiki-runtime/`)
- `scripts/_language.py` — language detection for frontmatter validation

### Media & Images
- `scripts/caption_batch.py` — Stage 0.6 standalone batch caption utility (MiniMax M3 multi-image API)

### Lint & Validation
- `scripts/wiki-lint.sh` — structural lint: broken-link, orphan, no-outlinks, missing-frontmatter, missing-domain, invalid-domain
- `scripts/wiki-lint-semantic.py` — LLM-driven semantic lint (contradiction/stale/missing-page/suggestion)
- `scripts/validate_ingest.py` — 15-stage validator, auto-runs at end of every ingest
- `scripts/validate-frontmatter.sh` — quick frontmatter compliance check

### Queue & Monitoring
- `scripts/wiki-monitor.sh` — scan raw/ for new/changed files, populate ingest queue (optional; prefer manual queue management for most workflows)
- `scripts/run-queue.sh` — thin wrapper around `ingest.py --watch --drain`. Supports `--parallel N`, `--file <path>` (single-shot), `--priority <path>` (prepend), `--watch` (continuous)

### Embeddings & Search
- `scripts/build_embeddings.py` — Stage 6 (also auto-triggered after ingest if `EMBEDDING_BASE_URL` is set)
- `scripts/search_wiki.py` — LanceDB semantic search

### Repair (standalone utilities)
- `scripts/repair_stage_05.py` — re-extract images for already-ingested sources
- `scripts/repair_stage_06.py` — re-generate missing image captions
- `scripts/repair_stage_35.py` — re-inject images into source pages
- `scripts/repair_stage_37.py` — generate stub source pages from existing media
- `scripts/reingest_batch.py` — batch re-ingest helper

## NashSU Parity (2026-06-14 audit)

ingest.py has been audited against NashSU `ingest.ts` v0.4.23 (2993 lines) and `lint.ts` (299 lines). Key parity features:

| Feature | Description |
|---------|-------------|
| Page merge | Existing pages are LLM-merged (array union + body merge), not overwritten |
| Path safety | `is_safe_ingest_path()` — 8 checks: NUL bytes, absolute paths, `..`, Windows reserved names, illegal chars |
| Fence-aware parsing | Tracks ``` ```/`~~~` fences; `---END FILE---` inside code blocks is not a closer |
| CRLF normalization | `\r\n` → `\n` before parsing FILE blocks |
| Error classification | Hard errors (disk full, permission) prevent cache save; soft errors (parse warnings) do not |
| Page history backup | Pre-overwrite snapshots to `.llm-wiki/page-history/<ts>_<name>` |
| Content sanitization | Fix stray code fences and `frontmatter:` prefix from LLM output |
| Dynamic token budget | `compute_max_tokens()` scales by model context (128K→8K, 256K→16K, 512K→32K) |
| Inline embeddings | Stage 6 auto-runs after ingest when `EMBEDDING_BASE_URL` is set |
| Lint slug priority | Last-write-wins (NashSU `Map.set`), not first-write-wins |
| Lint orphan detection | No frontmatter/char filters — matches NashSU unconditional detection |
| Stage 2.5 trigger | 3 NashSU conditions: ≥4 FILE blocks, ≥10K chars, or incomplete REVIEW block |
| **Stage 2 FILE path enforcement** | Source page: `wiki/sources/<pdf-stem>.md`. Concept: `wiki/concepts/<slug>.md`. Agent prompts MUST include exact filenames. 2026-06-15: 5 books had pages written to wrong dirs. |

## Stage 2 FILE Block Path Enforcement

**Every Stage 2 agent prompt MUST include:**

```yaml
SOURCE_FILENAME: wiki/sources/<raw-rel-path>.md
CONCEPT_FILENAME: wiki/concepts/<slug>.md
```

`<raw-rel-path>` mirrors the `raw/` directory structure. For example:
- `raw/book/High Speed Digital Design.pdf` → `wiki/sources/book/High Speed Digital Design.md`
- `raw/datasheet/ADI/ADL8113.pdf` → `wiki/sources/datasheet/ADI/ADL8113.md`

**DO NOT**: write to bare `wiki/<slug>`, invent source filenames, or create subdirectories that don't match `raw/`.
**DO NOT**: write concept pages to `wiki/sources/` — only the source page goes there. Every concept must use `wiki/concepts/<slug>.md`.
**The write script MUST validate** every path. `_auto_correct_wiki_path()` now handles both `wiki/Concept` (2-part) and `wiki/sources/Concept` (3-part wrong-dir) cases (2026-06-15: 68 concept pages ended up in sources/ from RF Microwave ingest).

The same rule applies to **`wiki/media/`** — media directories mirror the `raw/` structure. `raw/book/Foo.pdf` → `wiki/media/book/Foo/`. The path is `<type-subdir>/<pdf-stem>` where `<type-subdir>` is the raw file's parent directory relative to `raw/`.

## Trigger this skill

**Ingest (写入)**:
- User mentions wiki ingest / PDF OCR / Stage 0 / "minimax batch"
- User says "validate-ingest failed", "ingest-cache missing", "wiki has no source page", "image not captioned"
- A wiki project (HardwareWiki, RadarWiki, 自然科学知识库, etc) starts a new source ingest
- **Stage 0 (MANDATORY)**: Before selecting any file under `raw/` for digestion, the agent MUST check whether `wiki/sources/<raw-rel-path>.md` exists (mirroring the `raw/` directory structure). This source page is the **immutable record** of a completed ingest (written once at Stage 3, never deleted by the pipeline). Source page exists = skip. **Do NOT check `ingest-cache.json` for deduplication** — it is a volatile runtime file that can be missing, stale, or corrupted. Never rely on memory or conversation history to determine what has been ingested.
- User mentions "本地 OCR" / "local minerU" / "pilot OCR"

**Retrieval (读取)**:
- User asks to search/query the knowledge base: "搜索 wiki" / "查知识库" / "find X in wiki" / "wiki 里有没有"
- Technical questions that should check wiki first: "buck 电路 ringing 怎么解决" / "这个参数在 datasheet 里有没有"
- User says "引用知识库" / "cite wiki"
- Cross-project questions: "硬件知识库里有没有关于 X 的内容"

## OCR Architecture (Stage 0)

Two OCR paths, chosen by `detect_pdf_type()` (three-signal detection):

| PDF Type | Detection | Pilot | Full-Book OCR | Cost |
|----------|-----------|-------|---------------|------|
| Text-layer | avg >500 chars/page AND full-page image ratio <60% | None needed | PyMuPDF `get_text()` | Free |
| Scanned | avg <50 chars/page, OR >60% pages have full-page images, OR **image-heavy book** | **Local minerU** 5 pages | Local minerU VLM | Free |
| Mixed (50-500) | Between thresholds, no image dominance | Try PyMuPDF first; if sparse → local minerU pilot | Same as scanned if sparse | Free/Varies |

**Three detection signals** (2026-06-14 updated after Johnson《High-Speed Signal Propagation》failure):
1. `get_text()` average chars/page
2. Full-page image ratio: render low-res pixmap, check non-white pixel coverage (>80% = scan). This catches OCR-layered PDFs where background scan images aren't enumerable by `get_images()` (form XObject / masked image / inline image).
3. `get_images()` embedded image count — if only 1 image covering >50% page area, it's a scan page.

**⚠️ OCR-treated scanned PDFs** can have high char counts from embedded OCR text layers. The 3-signal detection corrects this misclassification. **For image-heavy technical books** (signal integrity, eye diagrams, waveforms, schematics), prefer minerU even if text char counts look OK — losing diagrams is far worse than the extra OCR time.

**Pilot (local minerU)**: Extracts 5 pages into a temp PDF, runs `~/.venv/bin/mineru -b vlm-auto-engine`. No API key needed. Output includes text + auto-extracted images. Quality check: >100 chars/page.

**Full-book OCR (local minerU)**: Same `mineru` CLI, run on the full PDF. No cloud API needed. Outputs per-page text + auto-extracted images to `extract-tmp/`. **Concurrency limit**: max 2 minerU instances system-wide (`MINERU_MAX_CONCURRENT = 2`). Each VLM model instance consumes several GB of unified memory; exceeding 2 concurrent instances on 16GB Mac causes SIGABRT crash.

**Venue**: `~/.venv` (Python 3.11, minerU v3.3.1, PyMuPDF). Created via `uv venv ~/.venv` and `uv pip install mineru pymupdf torch mlx mlx-vlm transformers`.

## Raw Layout Convention

improved-wiki 的 `raw/` 布局**不是** NashSU 原生的 `raw/sources/<type>/<file>`。设计目标是让人类能按领域直观浏览源文件，而非被工具路径约束。

### 基础 type 文件夹

每个知识库至少包含以下 3 个基础 type：

```
raw/
├── book/          # 书籍 → digest-book.md
├── paper/         # 论文 → digest-paper.md
└── presentation/  # 演示文稿 → digest-presentation.md
```

### 扩展 type 文件夹（按知识库领域添加）

HardwareWiki 等工程类知识库可添加：

```
raw/
├── datasheet/         # 数据手册 → digest-datasheet.md
├── ApplicationNote/   # 应用笔记 → digest-applicationnote.md
├── DesignExample/     # 设计示例 → digest-designexample.md
├── standard/          # 标准文档 → digest-standard.md
└── news/              # 行业新闻 → digest-news.md
```

### 嵌套子文件夹（自由组织）

每个 type 文件夹下可以按任意层级嵌套子文件夹，方便人类分类浏览。`detect_template_type()`（`ingest.py:162-194`）会自动向上查找到 type 文件夹：

```
raw/
├── book/
│   ├── control/
│   │   └── Automatic_Control_Systems_-_2007_-_Kuo.pdf
│   └── power/
│       └── Switching_Power_Supply_Design_-_Pressman.pdf
├── datasheet/
│   ├── ADI/
│   │   └── ADL8113.pdf
│   └── TI/
│       └── INA1H94-SEP.pdf
└── paper/
    └── MIMO/
        └── Phased_MIMO_Radar_Hassanien_2009.pdf
```

### Type → 模板映射

| type 文件夹 | 模板 | 说明 |
|------------|------|------|
| `book` | `digest-book.md` | 完整书籍，章节结构 |
| `paper` | `digest-paper.md` | 学术论文 |
| `presentation` | `digest-presentation.md` | 演示文稿/课件 |
| `datasheet` | `digest-datasheet.md` | 器件数据手册 |
| `ApplicationNote` | `digest-applicationnote.md` | 应用笔记 |
| `DesignExample` | `digest-designexample.md` | 参考设计 |
| `standard` | `digest-standard.md` | 行业标准 |
| `news` | `digest-news.md` | 新闻/博文 |

### Wrapper 文件夹（自动跳过）

如果项目从 NashSU 迁移而来，可能有 `sources/` 或 `assets/` 包装目录。`detect_template_type()` 会自动跳过它们（`WRAPPER_FOLDERS = {"sources", "assets"}`）。

### 新项目初始化

```bash
mkdir -p raw/{book,paper,presentation}
# 按需添加扩展 type
mkdir -p raw/{datasheet,ApplicationNote,DesignExample}
```

## Knowledge Retrieval (消费侧)

When answering technical questions, **search the wiki BEFORE answering from general knowledge**. The authoritative retrieval workflow is `references/kb-retrieval.md`.

**Quick start**:
```bash
# Build index (once per project)
python3 scripts/build_embeddings.py --project ~/Documents/知识库/HardwareWiki embed

# Semantic search via LanceDB + local Ollama bge-m3
python3 scripts/search_wiki.py "query" --project ~/Documents/知识库/HardwareWiki
```

**Projects**:
| Project | Path | Contents |
|---------|------|----------|
| HardwareWiki | `~/Documents/知识库/HardwareWiki` | Hardware design, circuits, components |
| 硬件设计知识库 | `~/Documents/知识库/硬件设计知识库` | Chinese hardware design KB |
| RadarWiki | `~/Documents/知识库/RadarWiki` | Radar systems |
| 雷达系统知识库 | `~/Documents/知识库/雷达系统知识库` | Chinese radar KB |
| 自然科学知识库 | `~/Documents/知识库/自然科学知识库` | Math, physics, science fundamentals |

**Rules** (from `references/kb-retrieval.md`):
1. Search with ≥2 synonyms (Chinese + English) before answering
2. When wiki has content → cite with project name + file path + section
3. When wiki has no content → explicitly mark `✗ 知识库无相关内容`
4. Never fabricate wiki references