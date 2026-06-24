---
description: "Image captioning strategy — unified pipeline over office-extracted (PPTX/DOCX zipfile) + minerU-extracted (PDF) images, parallel batch dispatch via ThreadPoolExecutor, grayscale→RGB preprocessing, VLM failure detection. Verified: HardwareWiki 18,709 images (2026-06-17), EMC book fix (2026-06-17)."
tags: [vlm, captioning, batch, minimax, strategy, parallel, preprocessing]
related: [multimodal-vlm-pitfalls, ingest-stages-mandatory §0.6, known-issues]
---

# Image Captioning 策略

Unified image captioning pipeline. Implemented as `stage_1_3_caption_images()` / `_stage_1_3_caption_images_batch()` in `scripts/_stage_1_extract.py` (moved out of `ingest.py` during the 2026-06-22 explicit-stage-naming refactor — old name was `_caption_images()`).

**2026-06-23 update**: the "Path A / Path B" split below is now stale terminology. PyMuPDF no longer extracts any images (PDF image extraction moved to minerU — see `ingest-stages-mandatory.md` Stage 1.2). The two sources captioning actually sees today are:
- **PDF images** — harvested by minerU (`_stage_1_2_harvest_images()` inline during Stage 1.1 chunk processing, or `_stage_1_2_extract_from_mineru()` for the opt-in CLI pipeline path)
- **PPTX/DOCX images** — extracted via `_stage_1_2_extract_images_office()` (zipfile, not PyMuPDF)

The code still passes `source_label="pyMuPDF"` as a hardcoded literal in `stage_1_3_caption_images()` — that label is leftover from before the migration and no longer reflects where the images actually came from. Harmless (it's just a log/manifest label, not used for branching), but don't trust it as a source-of-truth indicator.

---

## Architecture (2026-06-17, function names updated 2026-06-23)

```
PDF (minerU harvest)                  PPTX/DOCX (zipfile office extract)
  → media_dir / p0007-mineru_a1b2.png   → media_dir / image1.png
  → {"filename":..., "page":N, ...}     → {"filename":..., "page":0, ...}
                │                              │
                └──────────┬───────────────────┘
                           ▼
        _stage_1_3_caption_images_batch()  ← unified entry point
                │
                ├── _stage_1_3_preprocess_image()
                │     • grayscale (mode L/LA/P/PA) → RGB
                │     • oversized (>1568px) → thumbnail
                │     • base64 encode
                │
                ├── ThreadPoolExecutor (max CAPTION_MAX_WORKERS batches parallel)
                │     • _stage_1_3_caption_one_batch(): builds multi-image request
                │
                └── _stage_1_3_is_caption_failed()
                      • Detects VLM error responses
                      • Writes "[待重试]" fallback for later retry
```

(The "Path A/B" labels still in the code itself — `source_label="pyMuPDF"` default, the docstring inside `_stage_1_3_caption_images_batch()` — are stale leftovers from before the 2026-06-23 PyMuPDF-removal; harmless, just don't read them as describing current image sourcing.)

## Key parameters

| Parameter | Default | Env var | Description |
|-----------|---------|---------|-------------|
| Batch size | 8 | `CAPTION_BATCH_SIZE` | Images per API call |
| Max workers | 6 | `CAPTION_MAX_WORKERS` | Parallel batch concurrency |
| Image max dim | 1568 | — | Downscale threshold (Anthropic vision limit) |

## Performance

| Metric | Before (serial) | After (parallel) | Speedup |
|--------|----------------|------------------|---------|
| 40 images (5 batches) | ~90s | 15.8s | **5.7×** |
| 200 images (25 batches) | ~450s | ~25s (est.) | **~18×** |
| 2,196 images (The Art of Electronics) | ~6,600s | ~90s (est.) | **~73×** |

HardwareWiki verified (2026-06-17): 18,709 images, 18,701 captions (99.96% coverage).

## Image preprocessing

`_preprocess_image_for_caption()` in `ingest.py`:
- **Normalize to RGB**: palette/alpha modes converted to plain RGB for consistent encoding (MiniMax M3 handles grayscale fine per A/B test; normalization is defensive)
- **Downscale oversized**: images >1568px in any dimension are thumbnailed (VLM context window limit)
- Handles modes L, LA, P, PA, RGB, RGBA

## VLM failure detection

`_is_caption_failed()` detects these failure patterns:
- `解析失败`, `无法识别`, `无法描述`, `抱歉`, `sorry`
- `unable to`, `cannot describe`, `I can't`, `not clear`
- Text length < 15 characters

Failed captions are written as `[待重试] 图片 <filename>，尺寸 W×H` — the cache filter in `_caption_images()` will re-process them on next run.

## Formula transcription (LaTeX-only)

MiniMax-M3 transcribes formula images ~81% of the time (verified on Tudoroiu
2021: 52/64 tiny formula strips successfully transcribed). `CAPTION_SYSTEM_PROMPT`
includes a special rule for formula images:

- **Transcribe formula content symbol-by-symbol in LaTeX** — e.g.
  `$x_{k+1}=Ax_k+Bu_k$`, `$\sum_{i=0}^{2n} W_c^{(i)}[Y^i-\hat{y}]$`,
  `$\dot{T}=\frac{1}{mc_p}\dot{Q}$`
- **Do NOT use Unicode subscripts/superscripts or Greek letters** — write
  `x_1`, `\eta`, `\alpha`, `\Sigma`, NOT `x₁`, `η`, `α`, `Σ`. Rationale: LaTeX
  renders in markdown and is reusable downstream; Unicode subscripts are
  unparseable and don't render.
- **Word limit relaxed to 150 chars** for formula images (vs 100 default) to
  avoid truncating long equations.
- Unknown symbols use `?` placeholder.

## Tiny-image filter (`_is_image_too_small`)

Filters only true noise (1×1/2×2 pixel artifacts). Threshold is deliberately
conservative (`MINERU_IMG_MIN_WIDTH=20`, `MINERU_IMG_MIN_HEIGHT=20`, env-overridable)
because tiny formula strips (29-70px tall) are valuable — MiniMax transcribes
them. The filter must NOT be aggressive or it throws away recoverable formula
content.

> **Bug fixed 2026-06-22**: `MINERU_IMG_MIN_WIDTH`/`MINERU_IMG_MIN_HEIGHT` were
> referenced but never defined → `_is_image_too_small()` raised `NameError`,
> silently swallowed by the surrounding `try/except Exception: pass`, so the
> filter was completely non-functional (every image was kept). Fix: defined the
> constants AND moved the size check outside the broad try/except so future
> regressions surface instead of being swallowed.

## Usage

```bash
# Env vars for tuning
export CAPTION_BATCH_SIZE=10    # more images per call
export CAPTION_MAX_WORKERS=8    # more parallel workers
```

Direct call from Python (e.g., to repair failed captions for a specific book):
```python
from _stage_1_extract import _stage_1_3_caption_images_batch
media_dir = Path("wiki/media/Book/Some Book - 2024 - Author")
images = [{"filename": f.name, "page": 0, "width": 0, "height": 0}
          for f in sorted(media_dir.iterdir())
          if f.suffix.lower() in ('.png', '.jpg', '.jpeg')]
captioned = _stage_1_3_caption_images_batch(images, config, media_dir, source_label="repair")
```

## Known issues discovered 2026-06-24 (从零开始学散热 re-ingest, 528 images)

A full re-ingest of a 272-page Chinese thermal-design book exposed 5
quantifiable issues in the current image extraction + captioning pipeline.
Issues 1 & 2 were **fixed and verified** in a second re-ingest run. All
before/after measurements below are from those two runs.

### Issue 1: ✅ FIXED — MinerU's built-in `image_caption` is wasted on the API path

**Root cause**: minerU API's `build_result_dict()` (in `fast_api.py`) calls
`get_infer_result()` which reads `_content_list.json` with `fp.read()` —
returning a JSON **string**, not a parsed list. `_stage_1_2_harvest_images()`
checked `isinstance(cl, list)` which was always `False` for a string, so
`content_list` was silently skipped → `page_figs` empty → fallback triggered
→ ALL 528 images dumped to chunk-start page.

**Fix** (commit `a2bfb3e`, 2026-06-24): added `json.loads(cl)` before the
isinstance check. Also added: harvest now reads `content_list`'s
`image_caption` field and writes it as a sidecar `.caption.txt` before
Stage 1.3 runs, so pre-captioned images skip VLM entirely.

**Verified**: 141/340 images got minerU sidecar captions (42%), VLM calls
dropped from 528→157 (↓70%), caption coverage rose from 62%→98%.

### Issue 2: ✅ FIXED — 188 fragment images not filtered

**Root cause**: same as Issue 1. Once `content_list` is correctly parsed,
`page_figs` only contains image/chart blocks (340), not all `images` dict
entries (528). The 188 extra images (formula crops, table crops, noise) are
no longer extracted.

**Verified**: 528→340 images (↓36%), page numbers correctly mapped to 180
distinct pages (vs 6 before — all dumped to chunk-start page).

### Cascading effect: Stage 2.1 input quality

The `json.loads(cl)` fix also fixed Stage 2.1 (Global Digest) input. Before
the fix, the harvest fallback corrupted OCR text assembly → Stage 2.1 received
only 4,306 chars → 1 chunk → 36 concepts, 24 entities. After the fix,
Stage 2.1 receives 200,000 chars → 3 chunks → 55 concepts (+53%), 48 entities
(+100%). This is a 46× improvement in text input to the LLM.

### Issue 3: Open — No retry for failed/uncaptioned images (single-pass only)

Caption dispatch is a single `ThreadPoolExecutor` pass — batches that fail
JSON parsing or have truncated responses are logged but **not retried**.
After fixing issues 1+2, the failure rate dropped from 38% (202/528) to 1%
(4/340), so this is now a minor issue. A second-pass retry would eliminate
the remaining 4 uncaptioned images.

### Issue 4: Open — batch_size inconsistency

`CAPTION_BATCH_SIZE=8` (env var, line 66/1103) is the intended default, but
the minerU path call at line 990 hardcodes `batch_size=6`. JSON truncation
happens because 6-image batches can exceed MiniMax response token limits.

### Issue 5: Open — Formula images extracted as pictures instead of text

MinerU `content_list` marks **114 equation blocks** as LaTeX text (e.g.
`$$Q = P/d/C_p/\Delta t$$`) with `type=equation`, `text_format=latex`.
These are NOT in the `images` dict and NOT extracted as image files —
minerU handles them correctly as text.

However, ~112 narrow+short images (W/H > 2.5, height < 100px) were found
among the 528 extracted images, and 77 of their captions mention "公式"
or "formula". This means minerU's layout analysis sometimes classifies
formula regions as `image` blocks (with `img_path`) rather than `equation`
blocks (with LaTeX text), especially for complex multi-line formulas or
formulas embedded in figure captions.

### Summary table (updated post-fix)

| Issue | Status | Before fix | After fix | Impact |
|-------|--------|-----------|-----------|--------|
| 1: MinerU caption not used as sidecar | ✅ Fixed | 269 redundant VLM calls | 141 sidecar (42% skip VLM) | ↓70% VLM calls |
| 2: 188 fragment images not filtered | ✅ Fixed | 528 images (188 noise) | 340 images (0 noise) | ↓36% images |
| 3: No retry for failed captions | Open | 202 uncaptioned (38%) | 4 uncaptioned (1%) | Minor |
| 4: batch_size=6 hardcoded | Open | 7 JSON truncation events | Same | Low |
| 5: Formulas as images | Open | ~112 formula VLM calls | Same | Medium (upstream) |

## Revision history

- **2026-06-11**: Initial version, 738-image benchmark
- **2026-06-17**: Unified Path A + Path B into single `_caption_images()`; parallel batch dispatch via ThreadPoolExecutor; grayscale→RGB preprocessing; VLM failure detection with retry; cache filter checks existing caption content for failures
- **2026-06-22**: LaTeX-only formula transcription rule in `CAPTION_SYSTEM_PROMPT` (no Unicode subscripts/Greek, 150-char limit for formulas); fixed `_is_image_too_small` NameError bug (undefined `MINERU_IMG_MIN_WIDTH/HEIGHT` silently disabled the filter — constants now defined at 20px, size check moved outside broad try/except)
- **2026-06-23**: functions moved from `ingest.py` to `_stage_1_extract.py` with explicit stage prefixes (`_caption_images` → `stage_1_3_caption_images`/`_stage_1_3_caption_images_batch`, etc.); PyMuPDF removed entirely from PDF image extraction (Path A description above is now historical only — see note at top of doc)
- **2026-06-24**: Documented 5 issues from 从零开始学散热 re-ingest (528 images, 202 uncaptioned). **Issues 1 & 2 fixed same day** (commit `a2bfb3e`): root cause was `content_list` returned as JSON string by minerU API's `get_infer_result()` → `isinstance(cl, list)` always False → fallback dumped all 528 images including 188 fragments, wasted 269 minerU captions. Fix: `json.loads(cl)` + write minerU `image_caption` as sidecar. Verified: 528→340 images, VLM 528→157 calls, caption 62%→98%, Stage 2.1 input 4K→200K chars (46× improvement).
