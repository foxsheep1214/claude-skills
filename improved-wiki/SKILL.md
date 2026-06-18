---
name: improved-wiki
description: "Class-level umbrella for the Karpathy/NashSU LLM-Wiki ingestion pipeline (13-stage ingest + lint + graph). Use when ingesting a PDF/PPTX/DOCX into a wiki project (HardwareWiki, RadarWiki, etc), validating an ingest, debugging failed tasks, or auditing wiki completeness. Phase 0 OCR uses local minerU (free, auto-extracts images). Lint includes knowledge graph + Louvain community detection."
tags: [ingest, mandatory, nashsu, pipeline, scan-pdf, mineru, local-ocr, knowledge-graph, louvain]
related_skills: [karpathy-llm-wiki, llm-wiki-local]
---

# improved-wiki

Karpathy LLM-Wiki pattern + NashSU v0.4.25 pipeline. 13 ingest Stages (5 Phases) + lint + graph (auto-triggered).

```
Ingest: 0→0.5→0.6→1→1.5→2.0→2.x→2.3→2.5→2.6→3.5→[4]

Phase 0: Pre-processing (text extraction, image extract, caption, pilot OCR)
Phase 1: Analysis        (global digest, sequential chunk analysis)
Phase 2: Generation      (source page, per-chunk concept/entity, queries, comparisons, review)
Phase 3: Write & Enrich  (file write, image injection, aggregate repair)
Phase 4: Embeddings      (auto-triggered if EMBEDDING_BASE_URL set)

Sequential (NashSU parity): 1.5 chunk analysis + 2.x per-chunk generation
Parallel (I/O only):        0.6∥1 caption∥digest + 0.6 caption batch dispatch

Lint:  [Build Graph] → [Louvain] → [Insights]
       (post-ingest auto-triggered via AUTO_BUILD_GRAPH=1, 30min staleness guard)
```

## Entry point

**`references/ingest-stages-mandatory.md`** — authoritative ingest-stage checklist with go/no-go gates.

## Reference map

**Pipeline core**:
- `references/ingest-stages-mandatory.md` — ingest stage checklist (Phase 0-4 + Lint, ⭐ easy-to-skip stages marked; knowledge graph section)
- `references/query-generation.md` — Stage 2.3: auto-generate `wiki/queries/`
- `references/comparison-generation.md` — Stage 2.5: auto-generate `wiki/comparisons/` (2.5A disambiguation, 2.5B in-source, 2.5C cross-source)
- `references/knowledge-gap-lint.md` — lint system: synthesis/finding/thesis/methodology formation triggers
- `references/scanned-pdf-ocr-pipeline.md` — minerU scanned PDF OCR pipeline (Path B)
- `references/raw-naming-conventions.md` — raw 文件命名规范检查机制（项目级 `raw/NAMING.md` + auto-check）
- `references/conversation-mode.md` — direct LLM execution mode for ingest
- `references/delegate-mode.md` — agent orchestration for batch ingest

**Conventions**:
- `references/naming-conventions.md` — file naming, frontmatter, wikilink, directory conventions (NashSU-aligned)
- `references/domains.md` — domain classification for disambiguation
- `references/raw-layout-compat.md` — raw/ layout convention (type subdirs, nested, template mapping)

**Operations**:
- `references/kb-retrieval.md` — 4-step knowledge retrieval (search → read → cite → declare)
- `references/image-caption-strategy.md` — unified Path A+B caption pipeline, parallel dispatch, preprocessing (2026-06-17)
- `references/multimodal-vlm-pitfalls.md` — VLM pitfalls (caption collapse, OCR brittleness)
- `references/known-issues.md` — current bugs and workarounds
- `references/initial-setup.md` — first-time project bootstrap
- `references/batch-digest-loop.md` — batch ingest with resume
- `references/cron-installation.md` — cron-based automation
- `references/nashsu-lint-source-analysis.md` — NashSU lint.json internals
- `references/scripting-pitfalls.md` — Python + agent tool pitfalls

**Templates** (8 by file type):
`templates/digest-{book,paper,datasheet,applicationnote,designexample,presentation,standard,news}.md`

**Aggregate templates**:
`templates/{overview,schema,index,log,disambiguation}.md`

## Key features

- **Auto-ingest**: `python3 scripts/ingest.py file.pdf [file2.pdf ...]` — NashSU two-step: Stage 2.0 dedicated source page + Stage 2.x concept/entity generation
- **Batch ingest**: `python3 scripts/ingest.py f1.pdf f2.pdf ...` — parallel Stage 0-2 per book, serial Stage 3+ write
- **Knowledge graph**: `AUTO_BUILD_GRAPH=1` auto-rebuilds graph after ingest; manual: `python3 scripts/build_knowledge_graph.py`
- **Sequential Stage 1.5 + 2.x** (NashSU parity): chunk analysis (Stage 1.5) and per-chunk generation (Stage 2.x) run sequentially with accumulating context — each chunk builds on all previous chunks' discoveries. Per-chunk checkpoint for crash recovery.
- **Parallel I/O**: caption ∥ digest (Stage 0.6∥1), caption batch dispatch (×6 workers). Pure I/O-bound parallelism only — no quality impact.
- **Heading path tracking** (NashSU parity): each chunk analysis prompt includes full heading hierarchy (`Chapter 3 > Section 3.2 > Subsec 3.2.1`)
- **Overlap context** (NashSU parity): paragraph/sentence-aware overlap text passed between chunks for continuity
- **Page merge** (NashSU v0.4.25): three-layer merge on re-ingest — frontmatter array union + LLM body merge + locked fields. Sources field uses union-merge (preserves multi-source provenance).
- **CJK slug rewriting** (NashSU parity): auto-detects Chinese/Japanese/Korean titles and generates readable CJK slugs
- **PPTX/DOCX support** (NashSU parity): text extraction + image extraction from Office formats via stdlib zipfile
- **Schema routing validation** (NashSU parity): validates frontmatter `type:` against file path directory, auto-corrects mismatches
- **Aggregate repair safety** (NashSU parity): proportional size caps for index + overview, FILE block output filtering
- **Wikilink enrichment**: auto-adds `[[wikilinks]]` after page write (NashSU enrich-wikilinks parity)
- **Source lifecycle**: `--delete` removes source page + cache + orphan concepts/entities + media
- **Lint auto-fix**: `wiki-lint.sh --fix` repairs missing-domain and missing-frontmatter
- **Queue watch**: `--watch --drain` daemon mode consuming `ingest-queue.json`
- **Auto-validation**: `validate_ingest.py` runs at end of every ingest; per-stage gate functions (`_verify_stage_0_text`, `_verify_stage_1_5_chunks`, etc.)
- **NashSU parity**: aligned with `ingest.ts` v0.4.25 (sequential chunk gen, heading path, overlap suffix, CJK slug, PPTX/DOCX, sources union merge, schema routing, aggregate repair caps, page merge, wikilink enrichment, source lifecycle)
- **Local OCR**: minerU VLM via `~/.venv/bin/mineru -b vlm-auto-engine` (free, serial, `MINERU_MAX_CONCURRENT=1`)

## Scripts

| Category | Scripts |
|----------|---------|
| Core | `ingest.py`, `_paths.py`, `_language.py`, `_frontmatter.py` |
| Merge/Enrich | `_enrich_wikilinks.py`, `_source_lifecycle.py` |
| Lint | `wiki-lint.sh`, `wiki-lint-semantic.py`, `build_knowledge_graph.py`, `validate_ingest.py`, `validate-frontmatter.sh` |
| Queue | `wiki-monitor.sh`, `run-queue.sh` |
| Embeddings | `build_embeddings.py`, `search_wiki.py` |
| Repair | `repair_wiki.py`, `repair_stage_38.py`, `reingest_batch.py` |

## Trigger this skill

**Ingest**: User mentions wiki ingest / PDF OCR / minimax batch / validate-ingest / image caption / local minerU / pilot OCR. **Dedup rule**: before selecting any file, check `wiki/sources/<path>.md` exists. Never rely on `ingest-cache.json` for dedup.

**Retrieval**: User asks to search wiki / cite knowledge base / query technical content. See `references/kb-retrieval.md`.

## Projects

| Project | Path |
|---------|------|
| HardwareWiki | `~/Documents/知识库/HardwareWiki` |
| RadarWiki | `~/Documents/知识库/RadarWiki` |
| 自然科学知识库 | `~/Documents/知识库/自然科学知识库` |
