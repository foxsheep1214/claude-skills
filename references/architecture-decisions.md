# Architecture Decisions

Stable decisions and their rationale live here; operational runbooks link to
this file instead of repeating incident histories.

## ADR-001 — One fresh worker per conversation handoff

**Decision:** Except for the context probe, each prompt is answered by one
fresh worker/subagent that handles exactly one handoff. The main conversation
only orchestrates.

**Reason:** Large chunk prompts accumulated in a reused context and diluted
attention. Skolnik (2026-07-07) degraded after a 14-chunk chain; the EW/Radar
Handbook (2026-07-08) showed that even main-conversation one-by-one answering
still accumulated enough context to degrade. Hansen (2026-07-09) exposed a
second risk: an answering worker reported completion after internally
fan-outing work but never published one complete result.

**Consequences:** More handoff overhead, but stable per-call attention.
Responses publish through `.txt.tmp` plus validation and atomic rename.

## ADR-002 — Serial Stage 2.2, bounded-parallel Stage 2.4

**Decision:** Stage 2.2 remains serial because each chunk consumes the prior
validated rolling digest. Stage 2.4 chunk generation runs in independent
bounded waves capped by `--parallel`.

**Reason:** 2.2 has a real data dependency; 2.4 has a precomputed owner-slug
inventory and no rolling content dependency.

**Consequences:** `--parallel 1` is the explicit serial diagnostic mode.
Normal operation must not serialize Stage 2.4 or parallelize Stage 2.2.

## ADR-003 — Two-stage cross-book pipeline with one write spine

**Decision:** Phase 1 may overlap across books using two coordinated resource
roles (minerU and captioning), while Stage 2.3+ is a single ordered spine.

**Reason:** OCR/caption artifacts are source-local. Wiki association, merges,
aggregates, and finalization mutate shared state and require deterministic
ordering.

**Consequences:** Kernel worker leases supervise detached processes; a
coordinator lock prevents competing batch/watch schedulers; a short project
flock protects active mutation; a durable spine reservation survives
exit-101 handoffs.

## ADR-004 — No silent quality fallback

**Decision:** Missing caption, embedding, LLM, merge, schema, or required-media
dependencies pause the source after retries.

**Reason:** Quietly substituting OCR figure text, keyword-only retrieval, or
partial merge output produces an apparently complete but lower-quality wiki.

**Consequences:** Repair the dependency and resume from checkpoints. Corrupt
cache/checkpoint files are the exception: they warn and re-derive because that
is correct recovery rather than a quality downgrade.

## ADR-005 — Focused modules with compatibility facades

**Decision:** Configuration, progress/locking, schema/path safety, parsing,
retry, single-source running, batch supervision, status, CLI, and queue logic
have separate owners. `_core.py` and `ingest.py` retain established imports as
compatibility facades.

**Reason:** The former monoliths mixed unrelated mutation boundaries and made
parallelism, recovery, and tests hard to reason about.

**Consequences:** New code imports focused modules. Compatibility names remain,
but internal private monkeypatching should migrate to the owning module.
