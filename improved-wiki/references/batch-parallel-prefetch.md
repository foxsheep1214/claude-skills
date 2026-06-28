# Batch Parallel Prefetch — 多书并行预取（subagent 模式）

> **归属**：batch ingest 的成本优化模式。**不是**默认行为，是主对话在消化多本书时可选的并行调度方式。
> **边界**：只并行 **wiki-independent** 的预取阶段（Phase 0/1 + Stage 2.1 + 2.2）；**2.3 起的 wiki-dependent 主干必须串行一本一本**（见 [[batch-digest-patterns]]、[[delegate-mode]]）。

## 为什么要并行 + 用 subagent

多书 batch ingest 全程串行在主对话里跑，有两个成本问题：

1. **主对话上下文累积税**：主对话每答一个 Stage 2.2 chunk（读 ~760k 字符 prompt + 写 ~30k 答案），答案留在主对话里，后续每次工具调用都把越积越多的历史作为 input 重新计费。到第 3 个 chunk，每次调用背着 ~210k 历史。
2. **预取阶段空等**：Phase 0/1/2.1/2.2 是 wiki-independent（不读 wiki 现有页），规则**允许**跨书并行，但全程串行没利用这点。

subagent 方案同时解决两者：

- **上下文隔离**：subagent 是独立 Claude 实例，上下文从零开始，只装任务指令 + chunk prompt。读 760k 字符、写答案都在 subagent 自己的上下文里完成，**不回灌主对话**。主对话只回收一个摘要，保持精瘦。每个 chunk 省 ~150k+ input token。
- **并行预取**：三本书的 2.1/2.2 同时推进（受 minerU `fcntl.flock` 串行约束，提取阶段排队，LLM 阶段重叠）。

## 严格的阶段边界（不可逾越）

| 阶段 | subagent 可做？ | 说明 |
|------|----------------|------|
| Phase 0.1 raw 命名 / 0.2 去重 | ✅ | wiki-independent |
| Phase 1.1 minerU 提取 | ✅（受 fcntl.flock 串行） | wiki-independent，本地 |
| Phase 1.2/1.3 图像 + caption | ✅ | wiki-independent，caption 走 MiniMax |
| Stage 2.1 global digest | ✅ | wiki-independent |
| Stage 2.2 chunk 分析 | ✅ | wiki-independent |
| **Stage 2.3 incremental association** | ❌ | wiki-dependent，读 wiki 现有页 |
| **Stage 2.4 generation / 2.5 dedup / 2.6 source page / 2.7 queries / 2.8 / 2.9** | ❌ | wiki-dependent |
| **Phase 3.x write / enrich / 4.1 validate** | ❌ | wiki-dependent，写 wiki/ |

**subagent 必须在 Stage 2.3 handoff 出现时停下**，把 2.3 交给主对话。越过边界会让两本书的 2.3 dedup/linking 互相看不见对方刚写的页，破坏 wiki 一致性。

## 调度结构

```
主对话（串行主干，一本一本）：
  Book1 2.3→2.4→2.6→2.7→2.9→3.x→4.1  （2.1/2.2 已被 subagent 预取缓存）
  → Book2 2.3→…→4.1
  → Book3 2.3→…→4.1

并行 subagent（wiki-independent 预取，三本同时）：
  subagent-Book1: 2.1 → 2.2 (chunk 1..N) → 停在 2.3
  subagent-Book2: ingest.py → minerU(锁) → 2.1 → 2.2 → 停在 2.3
  subagent-Book3: ingest.py → minerU(锁) → 2.1 → 2.2 → 停在 2.3
```

主对话到达某本书的 2.3 时，其 2.1/2.2 已缓存，ingest.py 直接从 2.3 开始。

## subagent 任务模板

给每个 subagent 的指令要点（general-purpose agent，有 Bash/Read/Write）：

1. **工作目录**：`cd /Users/skyfend/Documents/知识库/HardwareWiki`（或目标项目根）。venv python：`~/.venv/bin/python3`。
2. **驱动 ingest**：`~/.venv/bin/python3 ~/.claude/skills/improved-wiki/scripts/ingest.py "raw/Book/<书名>.pdf"`。minerU 阶段长（20-40 min），用 `run_in_background` 跑，exit 101 时收到通知。
3. **handoff 循环**：ingest.py exit 101 = ConversationPending。读输出里的 `CONVERSATION → <Stage>` 块，拿到 Prompt 文件路径和 Result 文件路径。读 Prompt，按该 stage 的输出 schema 产出答案，写到 Result（.txt）。重跑 ingest.py。
4. **答案要 grounded**：读 prompt 里的 `<extracted_text>` 原文，**不要**用任何旧消化产物。公式逐字转写为 LaTeX，YAML 里单引号包裹（见 [[improved-wiki-yaml-latex-escape-bug]]）。
5. **停止条件**：handoff 是 `Stage-2-3` / `Stage-2-4` 或任何 ≥2.3 的 stage → **不写 .txt，直接返回**摘要（完成了哪些 stage、停在哪儿）。
6. **minerU 锁**：若另一本书的 minerU 在跑，你的 ingest 会在 `fcntl.flock` 上等待——正常，等锁即可，不要并发开两个 minerU。
7. **不要动 wiki/**：2.1/2.2 只写 `.llm-wiki/`，不写 `wiki/`。若发现要写 `wiki/`，说明越界了，停下。

## 主对话侧

- 在**一条消息里**发起所有 subagent（多个 Task 调用并发）。
- 等全部返回后，逐本串行跑 2.3+ 主干：`cd 项目根 && ingest.py "raw/Book/X.pdf"`，循环作答 2.3→…→4.1。
- 每本主干写完再下一本（保证 2.3 association 看到前一本的 wiki 页）。

## 何时用 / 何时不用

- **用**：≥2 本书的 batch；主对话上下文已经较满（省的税多）；minerU 提取可提前跑。
- **不用**：单本书（没有可并行的对象）；主对话上下文还很空（隔离省不了多少）；或 subagent 调度本身的复杂度不划算（如只跑一两本书的轻量预取）。

## 成本预期

- 省：每个 chunk 分析省 ~150k+ input token（主对话历史那部分），三本 × 数 chunk ≈ 省 1M+ token。
- 不省：2.3+ 主干仍串行、仍主对话作答；minerU 提取受锁串行（LLM 阶段才重叠）。
- 净效果：多书 batch 总成本约降 30-50%，墙钟时间约缩 30-40%（取决于 minerU 占比）。

## 相关

- [[batch-digest-patterns]] — batch ingest 串行主干规则与坑
- [[delegate-mode]] — conversation mode 的 agent 作答机制
- [[conversation-mode-agent-workflow]] — 单书 ingest 的逐 stage 作答 cheat sheet
