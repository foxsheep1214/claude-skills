---
name: improved-wiki
description: "强制 Ingest Stage 清单——基于 NashSU v0.4.23 autoIngestImpl() 流水线的 17 Stage 规范，每个 Stage 含作用/跳过代价/产物/go-no-go 判断。用于约束任何 wiki 项目执行 ingest 时不漏步。"
tags: [ingest, mandatory, nashsu, pipeline]
related: [SKILL.md §7, known-issues, multimodal-vlm-pitfalls]
---

# 强制 Ingest Stage 清单

## 为什么需要"强制"？

Karpathy LLM-Wiki 模式 + NashSU LLM Wiki app (v0.4.23) 的 `autoIngestImpl()` 流水线包含 **18 个 Stage**（2026-06-16 全面重编号为 Phase.序列 格式）。**任何一个 Stage 都不能跳过**——即使后续 Stage 看起来成功了，也不能"先跑再说"。

**跳过的代价**：
1. **raw 是 sacred**（Layer 1 原则）—— PDF 里的图也是 raw 的一部分，跳过图片提取 = 丢了一半知识
2. **审计可追溯性**（三层模型）—— 缺了 stage 产物，审计时无法回溯"为什么这个页面这么写"
3. **增量缓存前提**（Stage 5.1）—— 不写 hash cache，下一次 ingest 不知道哪些文件已处理
4. **错误累积**（NashSU 实测）—— 跳过的 stage 永远不会被补做，错误会一直留在 wiki 里

**违反此清单的代价**已在 2026-06-11 HardwareWiki 第一次 ingest 中真实发生：漏掉 Stage 0.7/0.9 后，source 页面里没有任何图片引用——因为没强制流程就没人会回头补。

## 强制 Stage 清单（18 步）

每个 Stage 都标了：
- **作用**：该 Stage 做什么
- **跳过代价**：跳过的具体后果
- **产物**：Stage 完成后必须存在的文件
- **go/no-go 判断**：怎么知道这个 Stage 算"真的完成"了

### Stage 0.1 · 源页去重检查 ⭐ **任何文件选取前强制执行**

- **作用**：检查候选文件是否已消化。**唯一判断依据：`wiki/sources/<raw-rel-path>.md` 是否存在。** `<raw-rel-path>` = raw 文件相对于 `raw/` 的路径（去掉 `.pdf` 后缀），镜像 `raw/` 的目录结构。源页是 Stage 3.1 写入的不可变记录，永远不会被 pipeline 删除或覆盖。源页存在 = 消化完成 → 跳过。不存在 → 进入 Stage 0.3。
- **跳过代价**：重复消化已完成的书籍，浪费 LLM token、OCR 时间，且并行场景下可能导致 index.md / log.md 竞态覆盖。
- **为什么只用 `wiki/sources/`，不查 `ingest-cache.json`**：
  - **`wiki/sources/` 是不可变记录**：每个成功的 ingest 在 Stage 3.1 写入一个源页，pipeline 永不删除或覆盖它。
  - **`ingest-cache.json` 不可靠**：2026-06-14 HardwareWiki 两次事故——(a) agent 忽略缓存选了已消化的书；(b) 10 本书源页存在但缓存缺失。缓存可以被手动删除、跨对话丢失、runtime 目录切换后找不到、并发写入损坏。它只适合作为 ingest.py 内部的性能优化（跳过哈希计算），**绝不用于去重判断**。
- **产物**：过滤后的待消化文件列表（只含 `wiki/sources/` 中无对应源页的文件）。
- **go/no-go 判断**：
  - `wiki/sources/<raw-rel-path>.md` 存在 → 跳过。例如 `raw/book/xxx.pdf` → 检查 `wiki/sources/book/xxx.md`。
  - `wiki/sources/<raw-rel-path>.md` 不存在 → 未消化，进入 Stage 0.3。
  - **不依赖对话历史、agent 记忆、`ingest-cache.json`、或文件名猜测。**

### Stage 0.5 · PDF 文本提取（按 PDF 类型分两路径）

**先判断 PDF 类型**（三信号检测：① PyMuPDF `get_text()` 字符数 ② 全页大图占比 ③ `get_images()` 嵌入图数量），按结果走不同路径：

- **信号 ①**：`get_text()` 平均 chars/page
- **信号 ②**：渲染页面低分 Pixmap，检查非白像素占比（>80% 即视为全页扫描图）。这是 **2026-06-14 Johnson《High-Speed Signal Propagation》教训**引入的补充检测——OCR 处理的扫描版 PDF，其背景扫描图可能以 PyMuPDF `get_images()` 无法枚举的形式存储（form XObject / masked image / inline image），导致信号 ③ 漏检。仅靠 `get_images()` 是不够的。
- **信号 ③**：`get_images()` 返回的嵌入图数量。**⭐ OCR处理扫描版的最可靠检测信号**。如果每页只有一个大图（>50% 页面面积），说明 PDF 本质是扫描版——OCR 文字层是后来嵌入的。2026-06-15 童诗白《模拟电子技术基础》：信号①=609c/p（文字层达标），信号②=7%（漏判），信号③=100%（每页一个嵌入大图）→ 判定为扫描版。**信号③ 必须作为三信号检测的首要判断依据。**

#### 路径 A：文本层 PDF（chars/page >500 且全页大图占比 <60%）

- **作用**：PyMuPDF `page.get_text()` 直接抽文本层
- **跳过代价**：无；这是最快路径
- **产物**：`full.txt`（合并所有页）
- **go/no-go**：平均 chars/page >500 且抽样页中全页大图占比 <60%。**但如果书籍内容以图表为核心（信号完整性、眼图、波形图、电路图等），即使字符数达标，也优先选路径 B——图表丢失的代价远大于 OCR 的时间成本。**

#### 路径 B：扫描版 PDF（chars/page <50，或抽样页中 >60% 有全页大图，或图表密集型书籍）

- **作用**：强制走本地 minerU VLM OCR，同时提取文字和图片。**⚠️ OCR 处理的扫描版 PDF 会有高质量文字层（chars/page 可达数百甚至上千），`detect_pdf_type` 使用三信号检测来纠正这个误判：① 文字量 ② 全页大图占比（非白像素 >80%）③ `get_images()` 嵌入图数量。缺少任何一个信号都可能导致误判为路径 A。**
- **跳过代价**：扫描版 PDF 仅走 PyMuPDF → 全页波形图/眼图/示意图丢失 → 对于信号完整性、电路设计等图表密集型书籍，丢失了一半以上的知识价值。**2026-06-14 Johnson《High-Speed Signal Propagation》实际发生**：100% 页面有全页大图，但 OCR 文字层字符数达标，PyMuPDF `get_images()` 无法枚举背景扫描图，最终走了路径 A，全本图表丢失。
- **产物**：每页一个 `p<NNN>.txt`（与页号 1:1 对应）+ minerU 自动提取的图片
- **go/no-go**：每页 chars >100；无幻觉（chars<100 且无中文字符 → 重跑）；确认 minerU 输出的 `images/` 目录包含图表
- **关键实操**：扫描版 PDF 全本 OCR 使用本地 minerU（`~/.venv/bin/mineru -b vlm-auto-engine`），免费、自动提取图片、无需 API key。**并发限制**：系统级最多 2 个 minerU 实例并行（`MINERU_MAX_CONCURRENT=2`）。16GB 统一内存的 Mac 上同时跑 >2 个 VLM 模型实例会导致 SIGABRT 崩溃 + 僵尸进程死锁。`ingest.py` 在每次 minerU 调用前通过 `_wait_for_mineru_slot()` 自动排队，无需人工协调。

**Stage 0.1 强制前置：pilot（5-10 页）验证 OCR 质量再启全本**
- 不准直接 Stage 0.1 全本。**必须**先本地 minerU 切前 5-10 页 → OCR → 看输出质量（中文术语识别、公式 LaTeX 化、章节结构保留）→ 再决定全本路径
- 跳过 pilot 的代价：全本跑到一半才发现质量不行 → 浪费数小时

### Stage 0.7 · 图片提取 ⭐ **永远不能跳**
- **作用**：用 PyMuPDF `get_images()` 抽取 PDF 每页的嵌入图，存到 `wiki/media/<type>/<pdf-stem>/`。**`<pdf-stem>` = PDF 文件名去 `.pdf` 后缀，与 `wiki/sources/<pdf-stem>.md` 共用同一个 stem。2026-06-15: 出现同一 PDF 被两次 Stage 0.5 用不同 slug 命名产生两个 media 目录的 bug，根因是 `source-slug` 未强制等于 PDF stem。**
- **跳过代价**：图全部丢失，wiki 文字描述无法引用图，故障排查价值砍半
- **产物**：`wiki/media/<type>/<pdf-stem>/p<N>-fig<K>.<ext>` + manifest.json
- **go/no-go**：扫描完所有页，统计抽出的图总数 > 0；如确实没有图，在 source 页 `## Embedded Images` 段写"无嵌入图"
- **必须含**：
  - 文件命名带页号（`p123-fig4.png`）便于回溯
  - sha256 去重（一图复用多页只存一份）
  - 尺寸过滤（< 100×100 像素的装饰/logo 剔除）
  - manifest.json 记录：图路径 / 来源页 / 尺寸 / sha256
  - **方向修正**（2026-06-15）：使用 `fitz.Pixmap(doc, xref)` 而非 `doc.extract_image(xref).raw_bytes`。Pixmap 会应用 PDF 图像变换矩阵，自动纠正旋转/翻转——`extract_image()` 只给原始字节，不处理 PDF 层对图像施加的旋转。CMYK 色彩空间自动转 RGB。如果 Pixmap 对 JBIG2/JPEG2000 等特殊编码失败，fallback 回原始字节。
- **扫描版 PDF 特殊说明**：扫描版的"图"是整页 PNG（不是嵌入 raster），Stage 0.7 在扫描版路径下不走 PyMuPDF `get_images()`，由 Stage 0.5 的页图天然承担。Stage 3.3 注入 source 页时直接引用 page-level PNG 即可

### Stage 0.9 · 图片 captioning ⭐ **永远不能跳**
- **作用**：对每张抽出的图，用 VLM 生成 1-3 句描述（中文优先）
- **跳过代价**：图存在但无文字说明 → LLM 和用户都不知道图里是什么 → 故障排查时无法检索
- **产物**：
  - `wiki/media/<type>/<source-slug>/p123-fig4.png.caption.txt`（每图一个 .caption.txt）
  - 或 `wiki/media/<type>/<source-slug>/captions.json`（合并清单）
- **go/no-go**：每张图都有 caption 文件；caption 长度 ≥ 20 字符（防止空 caption）
- **VLM 选择**（按本地优先 + 批量优先）：
  1. 本地 VLM（零 API 成本；MinerU 2.5 Pro 1.2B 等）—— **实测有限制**（见 `multimodal-vlm-pitfalls.md`）
  2. **多图/请求批量 API**（1 次调用 N 张图，省 60-75% 时间）⭐ **默认推荐 — `anthropic/v1/messages` 多图 content blocks**（minimax M3 国内端，HardwareWiki 实测 5 张/批 17.7 秒）
  3. 单图/请求 API（不推荐，仅在 VLM 限制必须时）
  4. Anthropic Message Batches API（50% 折扣，**24h 异步**——不适用于会话内消化）
  5. 极简 fallback：每图固定 caption "图 N：源自 <book> p<page>，内容待人工补"
- **重要（2026-06-11 强制）**：批量策略不能凭直觉选——必须先跑 `caption_sample_test.py`（20 张样本双 VLM 对比），**经验性**选型，不靠启发式
- **HardwareWiki 实测选择**（2026-06-11 无源器件篇扫描版）：`anthropic/v1/messages` 多图批量 caption（minimax M3，5 张/请求约 3.5 秒/张，比 OCR 任务更快因为输出短）。Stage 0.9 走跟 Stage 0.5 相同的 endpoint 即可。

### Stage 1.1 · Analysis（Global Digest）
- **作用**：1 次 LLM 调用，喂整本 PDF + schema + index，输出 6 块结构化 YAML
- **产物**：保存在 progress checkpoint（`.llm-wiki/.ingest-progress/<hash>.json`），成功 ingest 后写入 cache 的 `stages.global_digest_keys`
- **6 个顶层 key**（与 ingest.py `build_global_digest_prompt()` 一致）：
  - `book_meta`：标题、作者、年份、类型、语言
  - `outline`：章节大纲（含 `key_topics` 列表 + `start_marker`）
  - `key_entities`：关键实体（术语、人物、器件型号、公式符号等）
  - `key_concepts`：关键概念（设计思想、方法论、理论框架等）
  - `key_claims`：关键论断（结论、数据、设计准则等）
  - `chunk_plan`：切块计划（`estimated_total_chunks` + 每块的章节范围 + 重叠策略）
- **go/no-go**：`stages.global_digest_keys ≥ 1`（cache 中有记录）

### Stage 1.3 · Chunk Analysis
- **作用**：对源文本切块分析（**永远不能跳过，即使短源也要跑**）。短源（≤ 60K 字符）按 1 块处理（1 次 LLM 调用）；长源（> 60K 字符）按 ~60K/块切分（N 次 LLM 调用）
- **产物**：保存在 progress checkpoint，成功 ingest 后写入 cache 的 `stages.chunks_analyzed`
- **每个 chunk 的 YAML key**（与 ingest.py `build_chunk_analysis_prompt()` 一致）：
  - `chunk_index`、`chunk_total`：当前块序号和总块数
  - `entities_found`：本块发现的新实体（含名称、类型、定义、首次出现位置）
  - `concepts_found`：本块发现的新概念（含名称、定义、关键关系）
  - `claims`：本块的关键论断（含论断内容、证据类型、置信度）
  - `formulas`：本块出现的公式（含 LaTeX 表达式、变量说明、物理意义）
  - `connections_to_existing_wiki`：与已有 wiki 页面的关联
  - `digest_updates`：对 global digest 的修正/扩展/矛盾
- **go/no-go**：`stages.chunks_analyzed ≥ 1`（cache 中记录 ≥1 块）

### Stage 2.1 · Source/Concept/Entity Generation（per-chunk / legacy synthesis 双模式）

- **作用**：根据源文本 chunk 数自动选择生成策略——**仅生成 source / concept / entity 三种 page type**：
  - **多 chunk 书（>1 chunk）→ per-chunk 并行生成**：每个 chunk 的 Stage 1.3 分析结果独立生成该 chunk 的概念/实体页。chunk 之间用 `ThreadPoolExecutor` 并行处理（max 4 concurrent）。所有 chunk 生成完毕后去重合并，再用 global digest 生成 source page。**per-chunk 避免了大 synthesis 的认知衰减问题，大书的覆盖率从 ~10% 提升到 ~60-100%。**
  - **单 chunk 书（≤1 chunk）→ legacy synthesis**：沿用原来的多轮 synthesis 模型（8 轮 gap-aware continuation，覆盖门禁 core≥80% supp≥50%）。
- **产物**：FILE blocks → `parse_file_blocks()` → 写入 `wiki/` 目录
- **输出格式**：`---FILE:wiki/<path>---\n<markdown content>\n---END FILE---`
- **go/no-go**：
  - `stages.file_blocks_generated ≥ 1`
  - source page FILE block 存在
  - 概念页路径在 `wiki/concepts/` 下（不在 bare `wiki/` 或 `wiki/sources/`）
  - per-chunk mode：至少 1 个 chunk 产出 ≥ 1 个 block
- **覆盖率门禁**（仅 legacy synthesis 模式适用）：
  - core 概念 ≥ 80%，supporting 概念 ≥ 50%
  - 由 chunk 分析中的 `importance` 字段驱动（LLM 自行判断 core/supporting/mentioned）
  - 未达标时自动继续追问未覆盖概念

### Stage 4.1 · Query Auto-Generation ⭐ **新增 2026-06-16**

- **作用**：识别书中**提出但未完全解答**的开放问题，生成 `wiki/queries/<slug>.md` 页面。query 是知识演化链中"从已知到未知"的第一跳——把书中隐含的认知边界显式化为可追问的问题。
- **跳过条件**：source 类型为 `datasheet` 或 `standard` 时自动跳过（纯事实罗列，不产生有意义的开放问题）。
- **产物**：0-5 个 `wiki/queries/<slug>.md` 页面，或 `---QUERIES: 0---` 标记。
- **go/no-go**：
  - 生成了 0-5 个 query FILE block 或 `---QUERIES: 0---` 标记
  - 每个 query frontmatter 含 `type: query` + `title:` + `sources:` 三必填字段
  - 每个 query body ≥200 字符（不含 frontmatter）
- **prompt 模板**：见 `references/query-generation.md`

### Stage 4.3 · Comparison Auto-Generation ⭐ **新增 2026-06-16**

- **作用**：生成对比分析页面，分三种场景：
  - **4.3A 域内消歧义**：新 concept 名称与 wiki 已有 concept 同名但不同 domain → 创建/更新消歧义页（`type: comparison`, `domain: general`）。对齐 NashSU `domains.md` 消歧义规则。
  - **4.3B 源内概念对比**：同一源内两个高度相关的概念天然适合对比（如 CCM vs DCM、EMI vs EMC）→ 生成对比页（对比维度 ≥4）。
  - **4.3C 跨源对比**：新 concept 与已有 wiki concept 有可比性 → **仅标记 suggestion** 到 Stage 4.5 review，不自动生成（需人工触发，因跨源对比需读取双方完整 concept 页面，token 消耗大）。
- **跳过条件**：本次无 concept 产出（纯 stub source）时自动跳过。
- **产物**：0-2 个 `wiki/comparisons/<slug>.md` 页面（消歧义 + 源内对比），或 `---COMPARISONS: 0---` 标记。
- **go/no-go**：
  - 生成了 0-2 个 comparison FILE block 或 `---COMPARISONS: 0---` 标记
  - 每个 comparison frontmatter 含 `type: comparison` + `title:` + `domain:` 三必填字段
- **prompt 模板**：见 `references/comparison-generation.md`

### Stage 4.5 · Review suggestions ⭐ **永远不能跳**（但低于阈值时自动 skip）
- **作用**：当满足以下 **任一** 条件时（NashSU 3 条件触发，与 `ingest.ts` 一致），跑一次 LLM 调用输出 5 类 review items：
  1. ≥ 4 FILE 块
  2. ≥ 10K 字符的 generation 输出
  3. 末尾有不完整的 REVIEW 块（已打开但未关闭）
- **自动跳过条件**：以上 3 条件全不满足时跳过
- **产物**：`review-suggestions.json`（runtime dir）+ `wiki/reviews/<type>/<date>-<source>-<NNN>.md` 每项一个 md 文件
- **go/no-go**：review items 数量 ≥ 0（即使 0 也要记"LLM 主动认为无问题"）

### Stage 4.7 · Aggregate repair ⚠️ **程序化 append + LLM 重写**
- **作用**：
  - `index.md`：程序化 append 新 source 链接到 `## Sources` 段
  - `log.md`：程序化 append ingest 记录（时间戳、source、hash、method）
  - `overview.md`：**LLM 重写**——传入当前 overview.md 全文 + 新 source 页 + 最近 10 个 source 摘要，LLM 在旧内容基础上融入新源，输出 2-5 段综合概述
- **产物**：3 个 aggregate 页面更新
- **go/no-go**：旧有条目全部保留 + 新条目已追加 + overview LLM 响应以 `# Overview` 开头

**🚨 2026-06-13 ADL8113 事故：LLM 整文件重写 → 静默丢失所有历史**

NashSU 原生让 LLM 在 Stage 2 同时输出 index/log/overview，但 LLM **不会读到旧的 wiki 文件内容**（prompt 太大塞不下），只会生成一份"干净的从零开始"版本。improved-wiki 的对策：
- `index.md` / `log.md`：**纯程序化 append**，LLM 完全不参与
- `overview.md`：**LLM 重写**，但把**当前 overview.md 全文**喂给 LLM 作上下文——与 ADL8113 事故的关键区别是 LLM **看到了现有内容**

```python
# Stage 2.1 prompt：只让 LLM 输出 source + entities + concepts + Round2 的余下部分
# 永远**不要**让 LLM 生成 index.md / log.md / overview.md 块

# Stage 4.7 单独的程序化 append
log_path = wiki_dir / "log.md"
log_text = log_path.read_text() if log_path.exists() else "# Log\n"
log_text += f"\n## {ts} — INGEST\n- Source: `raw/{rel}`\n- Source page: `wiki/{source_rel}`\n- Hash: {sha[:16]}\n- Method: {method}\n"
write_wiki_file(log_path, log_text)

index_path = wiki_dir / "index.md"
index_text = index_path.read_text() if index_path.exists() else "# Index\n\n## Sources\n\n"
new_link = f"- [[{source_path.stem}]]\n"
if "## Sources" in index_text and new_link not in index_text:
    index_text = index_text.replace("## Sources\n", f"## Sources\n\n{new_link}", 1)
    write_wiki_file(index_path, index_text)
```

**修复已损坏的 index.md / log.md（如果事故已发生）**：用 `stage47_aggregate_repair.py` 反向重建 —— 从现存 `wiki/sources/*.md` 文件列表 + `ingest-cache.json` 的 `timestamp` / `hash` 字段拼回完整 log.md，扫 `wiki/sources/concepts/entities/` 重建 index.md。**不能用 LLM 修复**（同一事故会再次发生）。

### Stage 3.1 · Write files
- **作用**：解析 FILE 块 → 原子写盘（先 .tmp 再 rename）
- **产物**：所有 wiki/ 下的页面
- **go/no-go**：解析出的 page_blocks 数 == 写盘成功数

### Stage 3.3 · 图片安全网注入 ⭐ **永远不能跳**（依赖 0.5/0.6）
- **作用**：在 source 页末尾追加 `## Embedded Images` 段，列出所有抽出的图 + caption
- **跳过代价**：图存在但没在 wiki 里被引用 → 用户的 wiki 等于没图
- **产物**：source 页有 `## Embedded Images` 段
- **go/no-go**：source 页包含 `## Embedded Images` 标题 + ≥ 1 行图引用

### Stage 3.5 · Source-summary fallback
- **作用**：如果 LLM 忘记写 `wiki/sources/<slug>.md`，从 analysis 里自动生成一个 stub
- **产物**：保证 sources/ 1:1 对应 raw/
- **go/no-go**：每个 raw/ 下的文件都有对应 wiki/sources/ 页面

### Stage 4.9 · Parse review items
- **作用**：把 LLM 输出的 review items 解析并写入 `wiki/reviews/` 目录（每个 review item 一个 .md 文件，含 frontmatter `resolved: false`），同时写入 `review-suggestions.json` 到 runtime dir
- **产物**：`wiki/reviews/<type>/<date>-<source>-<NNN>.md` + `review-suggestions.json`
- **go/no-go**：`wiki/reviews/` 目录存在且含 ≥1 个 .md 文件；或 `review.json`（`run_review_suggestions.py` 独立输出）合法

### Stage 5.1 · Save cache ⭐ **永远不能跳**
- **作用**：写 `<sha256(raw)>` → `[filesWritten...]` 映射到 `ingest-cache.json`
- **跳过代价**：下次跑同一文件会重做所有 stage，浪费时间
- **产物**：`ingest-cache.json`，含本次所有 raw 文件的 sha256
- **go/no-go**：每个本次处理的 raw 文件都有 hash 记录
- **2026-06-11 重要发现**：app 的 `cache entry ≠ 产物`。cache 里 `filesWritten=[]` 也会出现"已 ingest"假象。**必须用 `scripts/validate_ingest.py` 验产物侧**，不能只看 cache schema

### Stage 5.3 · Embeddings
- **作用**：把 wiki/ 下的页面 chunk 化 + embed，写到 LanceDB
- **跳过代价**：检索只能用纯关键词（wiki < 100 页可接受，> 100 页必须 embeddings）
- **产物**：`lancedb/` 表 + `embed-cache.json`
- **go/no-go**：LanceDB 表存在 + 已写 ≥ N 个 chunk

---

## 强制顺序（不能乱）

```
0.1 → 0.3 → 0.5 → 0.7 → 0.9 → 1.1 → 1.3 → 2.1 → 3.1 → [3.3] → [3.5] → 4.1 → 4.3 → 4.5 → 4.7 → 4.9 → 5.1 → [5.3]
```

- **Stage 0.3 Pilot 是新强制前置**（2026-06-11）：任何 PDF 走 Stage 0.5 之前必须先 5-10 页 pilot 验证
- 0.7 **必须先于** 0.9（先有图才能 caption）
- 0.7/0.9 **必须先于** 3.3（3.3 注入图引用）
- Stage 1.1 / 1.3 **永远不能跳过**（短源 1 chunk / 长源 N chunk，都是 1.3 内部逻辑，不是 skip）
- **Stage 2.1（source/concept/entity）是 Phase 2 的唯一生成步骤**（2026-06-16 新增）：
  
  
  
- **Phase 4（Reflect & Review）在 Phase 3（Write & Enrich）之后执行**（2026-06-16 订正）：
  - **Stage 4.1/4.3（query/comparison）在写盘后执行**——需要看到已落盘的页面内容才能做反思和对比
  - **Stage 4.5（review）运行在已写盘的文件上**，这样 human reviewer 可以直接看到实际页面内容（包括 4.1/4.3 产出的 query/comparison 页面）
  - **Stage 4.7（aggregate repair）在所有页面写盘后运行**，确保 index/log/overview 基于完整的磁盘状态
- 4.1 是 conditional（datasheet/standard 自动跳过）
- 4.3 是 conditional（无 concept 产出时自动跳过）
- 4.5 是 conditional（NashSU 3 条件触发：≥4 FILE 块 / ≥10K 字符 / 未闭合 REVIEW）
- 4.7 程序化 append index/log + LLM 重写 overview（喂入现有内容防丢失）
- **Stage 4.9（Parse review items）无独立函数** — 其产物在 Stage 4.5 的函数内部产出
- 3.5 在 3.1 之后（write 完才发现缺 stub 才补）
- 5.1 在所有 stage 之后（写最终缓存）；hard error（磁盘满/权限）阻止 cache save
- 5.3 auto-run 当 `EMBEDDING_BASE_URL` 已设置时；否则手动 `build_embeddings.py`

---

## 验证清单（每次 Ingest 完成后必查）

完成一个文件的 ingest 后，**必须**逐项过这个清单：

- [ ] **Stage 0.3 Pilot 已跑**：5-10 页 OCR 输出质量 OK
- [ ] **Stage 0.5**：源文本已提取（PyMuPDF 文本层 OR mmx vision OCR 后每页 chars >100）
- [ ] **Stage 0.7：图已抽到 `wiki/media/<type>/<slug>/`（数量 > 0 或确认无嵌入图）**
- [ ] **Stage 0.9：每张图有 .caption.txt（长度 ≥ 20 字符）**
- [ ] Stage 1.1：global-digest.yaml 合法
- [ ] Stage 1.3：所有 chunk analysis 合法
- [ ] Stage 2.1：generation_response.txt 的 stop_reason == end_turn（**不是 max_tokens**）
- [ ] **Stage 4.1：query 页面已生成或 `---QUERIES: 0---` 已记录**（datasheet/standard 自动跳过）
- [ ] **Stage 4.3：comparison 页面已生成或 `---COMPARISONS: 0---` 已记录**（无 concept 时自动跳过）
- [ ] **Stage 4.5：review-suggestions.json 存在（即使 0 items）**
- [ ] Stage 4.7：index/log/overview 三页存在
- [ ] Stage 3.1：所有 FILE 块写盘成功
- [ ] **Stage 3.3：source 页含 `## Embedded Images` 段**
- [ ] Stage 3.5：所有 raw 文件有对应 source 页
- [ ] Stage 4.9：review.json 合法
- [ ] **Stage 5.1：ingest-cache.json 含本次所有 raw 文件 hash**（且 `validate_ingest.py` 通过；ingest.py 末尾自动运行）
- [ ] Stage 5.3：lancedb 表已更新（如启用 embeddings）

**加粗的 9 个 stage 是最容易跳过的**（也是历史上最容易出事的）：
- Stage 0.3 Pilot（2026-06-11 新增）—— 没 pilot 直接全本 = 浪费数小时
- 0.7（图提取）— 看似 optional，实际丢一半知识
- 0.9（图 caption）— 看似 optional，实际让图无法检索
- 4.1（query 生成）— **2026-06-16 新增**；看似 optional，实际让知识库只有事实没有追问
- 4.3（comparison 生成）— **2026-06-16 新增**；看似 optional，实际让跨概念理解和消歧义缺失
- 4.5（review suggestions）— 看似 optional，实际让错误内容永久残留
- 3.3（图注入 source 页）— 看似 optional，实际让图与 wiki 脱节
- 5.1（cache 写入）— 看似 optional，实际下次跑会重做所有 stage

---

## wiki 项目的特定策略（边界明确）

每个 wiki 项目可以在自己的 `wiki/methodology/` 下写"**per-project 决策**"页（如 "本项目用 MiniMax 批量 API"），引用本清单 + 记录该项目的特定选择。

**重要边界（2026-06-11 明确）**：
- `wiki/methodology/` **只放项目特定决策**（VLM 选择、批量大小、嵌入维度等）—— **不放**本清单的复制，也不放"我跳过了哪些 stage + 原因"
- 通用消化策略是本 skill 的责任（在本文件）；项目特定的偏离 = 在 `(removed — validate_ingest.py covers this)` 里说明本项目怎么做，**不**等于把本清单再抄一遍
- 如果项目**真的**跳过了某个 ⭐ stage，**在 `wiki/methodology/` 里加一段说明**，并标注"已知违反 SKILL.md 强制清单，原因：……"——这是**显式记录偏离**而不是静默跳过
- 静默跳过 = 违反规范。显式记录偏离 = 合规（因为人类在下次 lint 时能看到）

---

## 验证清单的执行方式（**清单本身没用，配套脚本才有约束力**）

本清单的 17 项是**人工 check 用的**，但验证已在流水线中自动化：

### 自动验证（ingest.py 内置，2026-06-16+）

**每个 Stage 完成后有实时验证门禁**（`_verify_stage_N()`），失败直接 `RuntimeError` 中止：

| Stage | 门禁检查 | 失败行为 |
|-------|---------|---------|
| Stage 0.5 | 提取文本 ≥ 500 字符；MinerU ≥ 2000 字符 | RuntimeError |
| Stage 1.1 | Global Digest 含 5 个必需 key；≥ 1 个 concept | RuntimeError |
| Stage 1.3 | chunk 分析非空 | RuntimeError |
| Stage 2.1 | ≥ 1 个 FILE block；source page 存在；路径正确 | RuntimeError |
| Stage 3.1 | source page 落盘 | RuntimeError |

**Ingest 末尾自动运行 `validate_ingest.py`**（全阶段验证），结果打印到 stdout。

遵循 superpowers Iron Law：**NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE**。

### 手动补充验证

```bash
# 结构性 lint（覆盖 wikilink 健康）
./scripts/wiki-lint.sh --summary

# 图存在性（覆盖 Stage 0.7 / 0.9 / 3.3）
test -d wiki/media/*/<slug> && \
  find wiki/media/<type>/<slug> \( -name '*.jpeg' -o -name '*.png' \) | \
    while read f; do
      [ -f "$f.caption.txt" ] || echo "MISSING CAPTION: $f"
    done

# cache hash 完整性（覆盖 Stage 5.1）
python3 -c "
import json, hashlib
from pathlib import Path
cache = json.load(open('.llm-wiki/ingest-cache.json'))
for k, v in cache['entries'].items():
    p = Path('raw') / k
    if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()[:16] != v['hash'][:16]:
        print(f'HASH DRIFT: {k}')
"
```

## 修订记录

- **2026-06-11**：初版，源于 HardwareWiki 第一次 ingest 漏掉 Stage 0.7/0.9 的事故
- **2026-06-13**：**Stage 4.7 大改版**（原 Stage 2.6）——加 ⚠️ "LLM 永远不重写 index/log/overview"
- **2026-06-14**：**Stage 0.1 新增**（原 Pre-Stage / Stage 0）——缓存去重检查，源于《硬件十万个为什么 开发流程篇》重复选取事故
- **2026-06-14**：**Stage 0.5 检测升级为三信号**（原 Stage 0.1）（原双信号）——增加非白像素占比检测。源于 Johnson《High-Speed Signal Propagation》事故：100% 全页大图 + OCR 文字层达标，但 PyMuPDF `get_images()` 无法枚举背景扫描图，误判为路径 A，全本波形图/眼图丢失。
- **2026-06-11**：初版，源于 HardwareWiki 第一次 ingest 漏掉 Stage 0.7/0.9 的事故
- **2026-06-16**：**全面重编号为 Phase.序列 格式**——Phase 0 (Pre-processing): 0.1/0.3/0.5/0.7/0.9; Phase 1 (Analysis): 1.1/1.3; Phase 2 (Generation): 2.1; Phase 3 (Write & Enrich): 3.1/3.3/3.5; Phase 4 (Reflect & Review): 4.1/4.3/4.5/4.7/4.9; Phase 5 (Finalize): 5.1/5.3。Query/Comparison 从 Phase 2 移到 Phase 4。
- **2026-06-16**：**P0：阶段间实时验证门禁**——每个 Stage 完成后增加 `_verify_stage_N()` 检查，不通过则 `RuntimeError` 中止。**ingest 末尾自动运行 `validate_ingest.py`**。遵循 superpowers `verification-before-completion` Iron Law。**P2：runtime 文件迁移**——`wiki-lint.sh` 的 `lint-cache.json`/`lint-lock` 从硬编码 `wiki/` 改为 `$RUNTIME_DIR`；`_paths.py` 增加 `_migrate_lint_cache_out_of_wiki()` 自动迁移。
- **2026-06-14**：**NashSU parity audit**——对比 `ingest.ts` (2993 行) + `lint.ts` (299 行) 完成全面对齐。Runtime dir `.iwiki-runtime/` → `.llm-wiki/`；状态文件去点号前缀（`ingest-cache.json` 等）；`purpose.md` → `schema.md`；Stage 2.5 阈值对齐 NashSU 3 条件；新增 Stage 2.6b (LLM overview 更新)；页面合并（已有页 LLM merge 而非覆盖）；路径安全校验（`is_safe_ingest_path` 8 项检查）；CRLF 规范化 + 栅栏感知解析；错误分类（hard/soft）；页面历史备份（`.llm-wiki/page-history/`）；内容清理（`sanitize_ingested_content`）；动态 token 预算；内联 embedding；lint orphan/no-outlinks 对齐 NashSU 无条件检测；slug 优先级 last-write-wins。
- **2026-06-13**：**Stage 1.1 / 1.3 YAML schema 与 SKILL.md spec 对齐**——Stage 1 改用 ingest.py `build_global_digest_prompt()` 的实际 6 keys (`book_meta` / `outline` / `key_entities` / `key_concepts` / `key_claims` / `chunk_plan`)。Stage 1.3 用上面那组。修复原因: 之前 SKILL.md spec 写的 `part_meta` / `key_specs` 是 datasheet 专属 schema,不能用于 book/paper 等其他类型。
- **2026-06-13**：**Stage 4.5 触发阈值修正**（原 Stage 2.5）——从旧的 "≥10K 字符或 ≥4 FILE 块" 改成 **"≥4 FILE 块"** (ingest.py 第 1136 行)。原因: ≥10K 字符阈值对 datasheet 太小,绝大多数 datasheet ingest 都会触发,产生过多 noise review; 应该按 FILE 块数判定。
- **2026-06-13**：**Stage 1.3 LLM YAML 输出 pitfall**（原 Stage 1.5）——LLM 经常会忘在 `key_details:` / `claims:` 等 list 子项加 `- ` 前缀(典型错例:`key_details:\n  "小信号增益 14.0 dB"` 应为 `key_details:\n  - "小信号增益 14.0 dB"`)。`yaml.safe_load()` 会报 `expected <block end>, but found '<scalar>'`。**修复**: 启发式 fix 脚本 `stage15_yaml_fix.py`(见 ADL8113 示例)——遍历行,当 `indent ≥ 4` + `stripped` 是带引号 scalar + 上下文是 list(`prev 是 "xxx:" 或 "- xxx:"`)**且当前行不以 `- ` 开头** 时,补 `- ` 前缀。**关键**: 用 `prev = fixed_lines[-1]` 而非 `lines[i-1]`,否则 fix 后的行不能传播 list context 给后续行。