# LLM Wiki v0.4.23 Ingest Pipeline — Actual Stage Map

Sourced from the upstream `nashsu/llm_wiki` v0.4.23 source code, primarily
`src/lib/ingest.ts` (the `autoIngestImpl()` function, lines 471–1158).
Use this when the user asks **how the pipeline works internally** or when
debugging a stage-specific failure (e.g. "Step 1 keeps timing out" or
"why is the aggregate-repair stage rewriting index.md").

The skill `llm-wiki-local` covers operations against the running app
(state files, API, recovery recipes). This reference covers **what each
stage actually does** in the source — they're complementary, not duplicate.

---

## 1. Reverse-identifying the app to its open-source repo

If you're handed an unfamiliar packaged LLM Wiki binary (or any Tauri/Electron
desktop app), you can recover its source repo in three steps before reading
arbitrary strings:

1. **Bundle ID + display name** — read
   `/Applications/<App>.app/Contents/Info.plist`:
   ```
   CFBundleIdentifier = com.llmwiki.app
   CFBundleDisplayName = LLM Wiki
   CFBundleShortVersionString = 0.4.23
   ```
2. **State file** — `~/Library/Application Support/<bundle-id>/app-state.json`
   exposes `version`, `lastProject.path`, `providerConfigs`, and the active
   `llmConfig` (model, endpoint, reasoning mode). Cross-checks the version.
3. **Strings in the Mach-O binary** — look for asset path patterns:
   ```
   $ strings <App>.app/Contents/MacOS/<exec> | grep -E "/assets/[a-z-]+-[A-Za-z0-9_-]+\.(js|ts)$"
   /assets/ingest-BZ_SUjTv.js
   /assets/ingest-queue-BWda7j6s.js
   /assets/chunk-...
   /assets/tauri-fetch-Dhx26arl.js
   ```
   Tauri/Vite-style asset paths + a JS bundle naming pattern are diagnostic
   for a webview-based desktop app. Then check the
   `Tauri-Response` / `Tauri-Invoke-KeyCodePageNotFound` / `tauri://`
   protocol strings — those are unique to Tauri 2.x.

For LLM Wiki specifically: the source is
`github.com/nashsu/llm_wiki`, v0.4.23 tag, GPL v3.0.
Clone with `git clone --depth 1 --branch v0.4.23 https://github.com/nashsu/llm_wiki.git`.

**Pitfall:** Don't try to lldb-attach to dump process memory. macOS SIP blocks
attach to processes you didn't launch from your debugger, even as root.
The asset strings inside the Mach-O are enough to fingerprint the source
repo. If you need the actual JS source, clone upstream.

---

## 2. The actual stage taxonomy (v0.4.23)

The author uses explicit `// ── Step N: ──` comments in `ingest.ts`. From
top to bottom of `autoIngestImpl()`:

| # | Stage | Line | What it does | Side artifacts |
|---|---|---|---|---|
| 0 | MinerU preprocessing (optional) | 506 | PDF only. If `mineruConfig.enabled && token`, submit to OpenXLab MinerU. Fallback to PDFium on failure. | `<source-dir>/.cache/<file>.txt` |
| — | Cache check (SHA-256) | 548 | `checkIngestCache(pp, sourceIdentity, sourceContent)`. Hit → re-run only image pipeline, return cached `writtenPaths`. | `.llm-wiki/ingest-cache.json` |
| 0.5 | Image extraction | 640 | `extractAndSaveSourceImages` (Rust-side PDF/PPTX/DOCX) + `extractAndSaveMarkdownImages` for `.md` sources. | `wiki/media/<source-slug>/...` |
| 0.6 | Image captioning | 674 | `captionMarkdownImages`. Only runs when `multimodalConfig.enabled`. SHA-256-cached at `.llm-wiki/image-caption-cache.json`. When disabled, strips `![](url)` from sourceContent entirely (intentional, prevents caption-less image refs from leaking into wiki pages). | `.llm-wiki/image-caption-cache.json` |
| — | Long-source check | 773 | `if (enrichedSourceContent.length > sourceBudget)` → call `analyzeLongSourceInChunks()`. Budget default 300K chars. | see §3 below |
| 1 | Analysis | 795 | One `streamChat` call. system = `buildAnalysisPrompt(purpose, index, sourceContent)`. max_tokens=4096, reasoning=`{mode: "off"}` (auto-forced on structured paths). | — |
| 2 | Generation | 833 | One `streamChat` call. system = `buildGenerationPrompt(schema, purpose, index, sourceIdentity, overview, sourceContext, sourceSummaryPath)`. User message carries the Stage 1 analysis as **context only** (must not be echoed). Output is `---FILE:<path>--- body ---END FILE---` blocks. max_tokens scales with `maxContextSize` (8K/16K/24K/32K). | — |
| 2.5 | Review suggestions (optional) | 888 | Triggers when `shouldRunDedicatedReviewStage(generation)` — i.e. generation has ≥10K chars OR ≥4 FILE blocks. Separate `streamChat` call. | — |
| 2.6 | Aggregate repair (conditional) | 962 | Only when generation touched `wiki/index.md`, `wiki/overview.md`, or `wiki/log.md` AND the existing file is small enough to safely regenerate (`isAggregateRepairSafe`). If skipped, warns "aggregate file too large". | — |
| 3 | Write files | 935 | `writeFileBlocks` parses FILE blocks via `FILE_BLOCK_REGEX = /---FILE:\s*([^\n]+?)\s*---\n([\s\S]*?)---END FILE---/g`, sanitizes each, writes to `wiki/{sources,concepts,entities,queries,comparisons,findings,synthesis}/`. Returns `{writtenPaths, warnings, hardFailures}`. | wiki pages |
| 3.5 | Image safety-net injection | 1078 | `injectImagesIntoSourceSummary` appends `## Embedded Images` to source page using marker-bracket idempotency. Skipped when `multimodalConfig.enabled=false`. | — |
| 3.7 | Source-summary fallback | 1042 | If LLM didn't generate `wiki/sources/<slug>.md`, write a minimal stub with the first 3K chars of the analysis. Skipped on abort. | — |
| 4 | Parse review items | 1097 | `parseReviewBlocks` on generation + reviewSuggestionOutput. Push to `useReviewStore`. | `.llm-wiki/review.json` |
| 5 | Save cache | 1106 | `saveIngestCache`. **Skipped if any `hardFailures`** (next ingest retries). Long-source checkpoint cleared on success. | `.llm-wiki/ingest-cache.json` |
| 6 | Embeddings | 1126 | If `embeddingConfig.enabled`, call `embedPage` per writtenPath (skip `index/log/overview`). Writes to `lancedb/wiki_chunks_v{N}.lance` (N bumps when embedding model/dim changes). | lancedb |

---

## 3. Long-source sub-pipeline (between Step 0.6 and Step 1)

When sourceContent exceeds `sourceBudget` (default 300K chars), the
entire Step 1/2 chain is replaced by a chunked pre-analysis.

Constants (`ingest.ts` lines 41–46):
```
LONG_SOURCE_MIN_BUDGET             = 8_000
LONG_SOURCE_MAX_SINGLE_PASS_BUDGET = 300_000
LONG_SOURCE_CHUNK_MIN              = 12_000
LONG_SOURCE_CHUNK_MAX              = 60_000
LONG_SOURCE_DIGEST_MAX             = 15_000
LONG_SOURCE_CHUNK_ANALYSIS_MAX     = 40_000
```

Algorithm (`analyzeLongSourceInChunks`, line 2361):

1. `targetChars = clamp(floor(sourceBudget * 0.55), 12_000, 60_000)`
2. `overlapChars = clamp(floor(targetChars * 0.08), 800, 3_000)`
3. `splitSourceIntoSemanticChunks(content, targetChars, overlapChars)`
   — splits at markdown heading boundaries + paragraph breaks, with
   `overlapSuffix(prev, overlapChars)` tacked onto each chunk for
   cross-chunk context.
4. **Checkpoint load** at
   `<project>/.llm-wiki/ingest-progress/<slug>-<hash>.json`.
   FNV-1a 64-bit hash of sourceContent as key. If found AND parameters
   match (`sourceLength`, `sourceBudget`, `targetChars`, `chunkTotal`),
   resume from `completedThrough+1`.
5. **Per-chunk serial `streamChat`** — system prompt is fixed
   (`buildChunkAnalysisSystemPrompt(purpose, schema, index, fullContent)`,
   carrying the schema/index so each chunk knows about the wiki it's joining).
   User prompt is `buildChunkAnalysisUserPrompt(sourceIdentity, chunk,
   trim(globalDigest, 15_000))`. After each chunk:
   - Extract `## Chunk Analysis` and `## Updated Global Digest` sections
   - `globalDigest = nextDigest || (globalDigest + chunkAnalysis)`, trimmed to 15K
   - Save checkpoint (durable JSON on disk; survives crash mid-loop)
6. After all chunks: build `analysis` (digest + per-chunk sections) and
   `sourceContext` (digest + concatenated chunk notes, trimmed to fit
   `sourceBudget`). Both replace the original `enrichedSourceContent` for
   Steps 1 and 2.

**Pitfall:** chunks are processed **serially**, not in parallel. The
digest depends on prior chunks' updated-digest sections, so the
concurrency cap is 1. Long books can take many minutes even on a fast
provider.

---

## 4. Prompt structure that explains the two-step design

Karpathy's original gist suggested one LLM call to digest a document.
NashSU's split exists for two reasons:

1. **Context budget**: dense books (200K+ chars) blow past any single
   model's context when prompt + thinking + output stack. Splitting
   Analysis (max_tokens=4096, reasoning=off) and Generation (max_tokens=8K–32K)
   keeps each call under budget.
2. **Output format discipline**: Generation must produce strict
   `---FILE:<path>--- body ---END FILE---` blocks. Free-form summarization
   is unreliable when mixed with the analysis task. Putting analysis in
   a separate call lets the generation call's system prompt lead with
   the format spec, and the user prompt can say "Stage 1 analysis is
   context only — do not echo it; emit FILE blocks now."

The `analysis` output is **never** echoed verbatim into wiki pages. It's
fed to Step 2 as context, and Step 3.7 uses only the first 3K chars of
analysis as a fallback if the LLM fails to write `wiki/sources/<slug>.md`.

---

## 5. Cross-references with state files

| Stage | Reads | Writes |
|---|---|---|
| Cache check (pre-Step-0.5) | `.llm-wiki/ingest-cache.json` | — |
| Long-source loop | `.llm-wiki/ingest-progress/<slug>-<hash>.json` | same path (overwrite) |
| Caption | `.llm-wiki/image-caption-cache.json` | same path |
| Step 5 | — | `.llm-wiki/ingest-cache.json` |
| Step 6 | — | `lancedb/wiki_chunks_v{N}.lance` |
| Image extraction (0.5) | raw source PDF/PPTX/DOCX | `wiki/media/<source-slug>/...` |
| File writing (3) | — | `wiki/sources/...`, `wiki/concepts/...`, `wiki/entities/...` |

---

## 6. Failure modes mapped to stages

| Symptom | Likely stage | Look at |
|---|---|---|
| "Chunk analysis stream failed" in ingest-progress JSON | Long-source Step, per-chunk `streamChat` | `app-state.json` → `llmConfig.maxContextSize` vs actual model window; `reasoning.mode`; provider 529s |
| Generation produces no `---FILE:` block | Step 2 | `llmConfig.reasoning.mode` (must be off); `maxContextSize`; check the abort fast-path (cancelled → empty → fallback source-summary written but no concept/entity pages) |
| `aggregateRepairPaths` shows `index.md / overview.md / log.md` getting rewritten unexpectedly | Step 2.6 | `index/overview/log` size grew past `isAggregateRepairSafe` threshold (uses `aggregateRepairSectionCap(maxContextSize)`) |
| New wiki pages don't appear in search | Step 6 | `embeddingConfig.enabled`, model/dim change → lancedb version bump, old embeds stale |
| Review queue keeps growing | Step 2.5 + Step 4 | `shouldRunDedicatedReviewStage` fires on >10K chars or >4 blocks — verify by checking `REVIEW_STAGE_MIN_SIGNAL_CHARS` constant |
| Same source keeps re-ingesting | Step 5 cache skip path | `ingest-cache.json` hash mismatch — usually iCloud/FinderInfo metadata drift, see llm-wiki-local SKILL.md §"Why is the queue full of files I already digested?" |
| Source page exists but no images visible | Step 3.5 or Step 0.6 | `multimodalConfig.enabled=false` → both strip images AND skip the safety-net injection |