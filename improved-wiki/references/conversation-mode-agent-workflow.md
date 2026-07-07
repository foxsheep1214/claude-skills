# Conversation Mode — Agent Driving Pattern

When an agent (Hermes, Claude Code) drives the improved-wiki pipeline, it must
answer each LLM step that `ingest.py` delegates via prompt files. This file
documents the practical workflow for a single-book ingest.
(机制与政策见 `references/delegate-mode.md`；本文是逐 stage 作答的 hands-on cheat sheet。)

## Generation guardrails (any FILE-block prompt)

- **Never generate index/log/overview pages** — Stage 3.5 handles these three
  programmatically (index/log appended, overview LLM-rewritten). An LLM-emitted
  full rewrite silently drops history entries (the ADL8113 incident).
- **Frontmatter completeness**: every page needs the 6 required fields
  (`type`/`title`/`tags`/`related`/`created`/`updated`; `sources` is an
  additional field where applicable — see `references/naming-conventions.md`).

## Prerequisites

- **Python**: `~/.venv/bin/python3` (3.10+). System python3 (3.9) fails on PEP 604 — see `scripting-pitfalls.md` Pitfall 4.
- **Environment**: `IMPROVED_WIKI_ROOT=<project-path>` exported or prefixed.
- **minerU**: Local API server on port 19999 must be running (auto-started by pipeline).

## LLM Step Sequence (single-book, serial)

Each step: `ingest.py` exits 101 → read prompt `.md` → write response `.txt` → re-run `ingest.py`.

| Step | Prompt file pattern | What to produce | Key tips |
|------|-------------------|-----------------|----------|
| Stage 2.1 | `Stage-2-1-Global-Digest-*.md` | YAML with 6 top-level keys (book_meta, outline, key_entities, key_concepts, key_claims, chunk_plan) | **Read full text from `.llm-wiki/extract-tmp/<stem>/p*.txt`** — the prompt only includes ~4K chars sampled from the middle |
| Stage 2.2 | `Stage-2-2-Chunk-N-*.md` | YAML with chunk_index, entities_found, concepts_found, claims, formulas, connections_to_existing_wiki | Include detailed concept definitions with key_details — these feed directly into generation |
| Stage 2.4 | `Stage-2-4-Generation-*.md` | FILE blocks (`---FILE:wiki/<path>---\n...\n---END FILE---`) for source + concepts + entities | The largest step. Generate a page for EVERY concept/entity listed. Use exact slugs from the prompt. Only link to pages in the "Linkable pages" list. |
| Stage 2.7 | `Stage-2-7-QueryGeneration-*.md` | 0-5 query FILE blocks or `---QUERIES: 0---` | Each query: type=query, title, background, clues, to-explore, see-also |
| Stage 2.9 | `Stage-2-9-ComparisonReview-*.md` | 0-N comparison FILE blocks or `---COMPARISONS_IN_SOURCE: 0---` | Each comparison: why compare, table (≥4 dimensions), selection guide, see-also. |
| Stage 3.4 | `Stage-3-4-Review-*.md` | YAML array of ≥5 review items (`type`/`title`/`description`/`affected_pages`/`severity`/`search_queries`) | Runs **after** Stage 3.1 write, on the already-written pages. Single handoff, no chunk chain — same as 2.1/2.6/2.7/2.9: just answer it and move on, no cap/dispatch decision to make. |
| Merge tasks | `LLM-task-*.md` | Merged page body (no frontmatter) | **Delegate to subagent** — see below |
| Wikilink enrichment | `LLM-task-*.md` (JSON) | `{}` to skip | Safe to skip if Stage 2.4 already added inline wikilinks |

## Handling the merge loop

After Stage 3.1 write, the pipeline generates many `LLM-task-*.md` merge prompts.
These are repetitive — the same pages may be re-merged across runs.

**Pattern**: Dispatch a `delegate_task` subagent with:
- `toolsets: ['terminal', 'file']`
- Instructions to loop: read `.md` → write `.txt` → re-run `ingest.py` → repeat
- For merge tasks: output merged body (prefer richer version, keep all wikilinks)
- For JSON wikilink tasks: output `{}`
- Stop when `ingest.py` exits 0 (pipeline complete) or a non-merge/non-JSON LLM stage appears

## Stage 2.2 quality gate (mandatory, added 2026-07-07)

**Incident (Skolnik, 14 chunks)**: a driving sub-agent kept answering
`CONVERSATION →` turn after turn without ever exiting — the existing L4 chain
cap (`references/delegate-mode.md`, "链式作答": max **2** same-stage handoffs
per sub-agent, then exit and let the parent dispatch a fresh one) was not
enforced. Context accumulated monotonically; Stage 2.4 prompts are 290–440 KB
each (they embed the full chunk source text), and after chaining well past the
cap the sub-agent degraded to placeholder outputs ("Radar Handbook Content"
instead of real concept names) rather than actually reading the source.

**This is not a new cap — it's a reminder that the existing one is not
optional**: the L4 rule's "上限2个handoff" is a hard ceiling, not a target to
approach. A sub-agent chaining Stage 2.2 or Stage 2.4 handoffs MUST exit after
its 2nd handoff and report progress back to the parent, every time, regardless
of book size or batch size. If a driving agent ever finds itself answering a
3rd consecutive same-stage handoff, that is the bug to fix (the exit-after-2
step was skipped), not a sign the cap should be relaxed.

**Quality gate (new — catches degradation at the cheapest point, Stage 2.2,
before it propagates into Stage 2.4's generated pages)**: after every Stage 2.2
response, before deciding whether to chain the next handoff or hand back to the
parent, verify:
- ≥ 5 real concepts (count `- name:` entries in `concepts_found`)
- No placeholder names (regex: `(?i)chunk \d|handbook content|reference material|technical content|book content`)
- Response size ≥ 3000 bytes

Run `scripts/qc_stage22.py` (generalized from the ad-hoc script that caught the
Skolnik incident; scans every `Stage-2-2-Chunk-*.txt` under
`.llm-wiki/conversation/*/`) to check all responses at once. If a response
fails the gate, delete the `.txt` and re-dispatch that turn — the sub-agent
must actually read the chunk source text this time.

**What NOT to do**:
- Do NOT let a sub-agent drive an entire multi-chunk book or multi-book batch
  end-to-end by ignoring the L4 exit-after-2 step — that is exactly how
  Skolnik degraded.
- Do NOT skip the quality gate even when context is tight — a thin Stage 2.2
  response propagates to Stage 2.4 (ALREADY COVERED) and silently drops whole
  chapters from the wiki (Skolnik chapters 5–26).

## Reading extracted text for Stage 2.1

```bash
EXTRACT_DIR=".llm-wiki/extract-tmp/<book-stem>"
# Sample pages across the book
for i in 1 15 30 50 70 90 110 130 150 170 190 210 230 250 270; do
  f=$(printf "%s/p%04d.txt" "$EXTRACT_DIR" "$i")
  [ -f "$f" ] && echo "=== Page $i ===" && head -10 "$f"
done
# Count total
ls "$EXTRACT_DIR"/p*.txt | wc -l
```

## Stage 2.2/2.4: scale extraction density + ground formulas (updated 2026-07-01)

At the **64K default ceiling** a large book splits into several ~256K-char chunks
(~2–3 chapters each), each analyzed and generated in ONE inline pass. Two practices
keep each chunk well-extracted and formula-faithful:

1. **Enumerate section by section — completeness, not a count.** The Stage 2.2
   prompt nudges you to read the WHOLE chunk section by section and list every
   genuine page-worthy concept the source defines or uses. It does **not** set a
   per-char concept quota (the old ~1-per-20K-chars target was dropped 2026-07-02:
   density is a property of content, not char count, and a number invited
   padding/splitting). Quality over count — never pad, never split one concept into
   several, never skip a real one to keep the list short. Select only the most
   significant named systems/people as entity pages — do not make a page for every
   model number a survey handbook mentions (over-extraction).

2. **Ground every formula by targeted grep back to source.** Don't transcribe
   formulas from memory. For each formula you cite, locate it in the chunk text or
   the per-page extract and copy the LaTeX verbatim:
   ```bash
   EXTRACT_DIR=".llm-wiki/extract-tmp/<book-stem>"
   grep -n "frac\|tag{2-\|sigma\|lambda" "$EXTRACT_DIR"/p0NNN.txt   # find the eqn
   ```

**Answer each chunk DIRECTLY yourself — do NOT fan out to per-chapter sub-agents.**
A ~256K-char chunk (~2–3 chapters) is directly manageable in a single analyze pass
and a single generate pass. A 2026-07-01 A/B ingest confirmed this: the 64K arm ran
the whole book in **10 native round-trips with no fan-out**, cleaner than a 192K
whole-book single chunk that had to be fanned out into per-chapter helpers +
split-generation groups (which stalled repeatedly on orchestration for no quality
gain). Sub-agent fan-out is only worth considering if you deliberately override the
ceiling far up (`IMPROVED_WIKI_TARGET_TOKENS_CEIL=192000`) so one chunk spans the
whole book — which is not the default and not recommended for dense references.
For Stage 2.4, generate the chunk's exact slug list inline; verify block-count ==
requested slugs (minus the `foo-bar` placeholder) before advancing.

## Re-ingest (comparison or correction)

完整流程（backup → delete → re-ingest → compare）见 `references/re-ingest-comparison.md`；速查命令：

```bash
# 1. Delete old ingest
~/.venv/bin/python3 ~/.agents/skills/improved-wiki/scripts/ingest.py \
  --delete "raw/Book/<file>.pdf"

# 2. Re-run fresh
IMPROVED_WIKI_ROOT="$(pwd)" ~/.venv/bin/python3 \
  ~/.agents/skills/improved-wiki/scripts/ingest.py \
  "raw/Book/<file>.pdf"
```
