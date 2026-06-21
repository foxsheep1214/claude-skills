# Dedup 设计：两种去重的职责划分

improved-wiki 有**两种职责不同、不可互换**的去重。它们名字不同、时机不同、侧重点不同——不要混淆，也不要合并。

## 命名

| 种类 | 中文名 | 英文名 | 模块 | 入口 |
|---|---|---|---|---|
| ① 消化时 | **源内去重** | intra-source dedup | `_stage_2_5_dedup.py` | `stage_2_5_dedup()` |
| ② 检查时 | **跨源去重** | cross-source dedup | `cross_source_dedup.py`（CLI）+ `_dedup.py` / `_dedup_merge.py`（引擎）| `cross_source_dedup.py` CLI |

## 职责对比

| 维度 | 源内去重（Stage 2.5） | 跨源去重（lint sweep） |
|---|---|---|
| 范围 | 单源——只看本次 LLM 生成的 file_blocks | 全 wiki——跨所有已消化源 |
| 目标问题 | LLM 在**同一本书内**把同一概念起两个名（如生成 PAO + 聚磷菌 两个块）| 跨源累积——多次 ingest 把同一主题命名不同；同 title 变体 slug 堆积 |
| 时机 | 写盘前（3.1 之前），是 file_blocks 的**过滤器** | 离线，用户手动 `--dedup` 触发，在多次 ingest 之后 |
| 速度要求 | 必须快（inline，阻塞 ingest）| 可慢（离线，两阶段慢慢跑）|
| 激进度 | **保守**——页面还没写，误合并=丢数据，且无备份 | **彻底**——有 backup + report，可回滚，可大胆合并 |
| 跨引用改写 | **不做**——页面尚未落盘，没有 `[[wikilink]]` 可改 | **必须做**——全 wiki 重写 `[[old-slug]]` + `related:` 指向 canonical，否则合并后留断链 |
| 检测方法 | 确定性候选（词级 Jaccard ≥0.6）+ LLM 逐组确认；LLM 失败则不合并 | 两阶段：phase 1 确定性同 title 合并（无 LLM）→ phase 2 LLM 语义检测（NashSU `dedup.ts` 移植，无 Jaccard 预筛）|
| 输出 | 静默过滤——dup 块直接不写盘 | backup 目录 + JSON report，供人复核 |
| 可逆性 | 不可逆（dup 页根本没生成）| 可逆（有 backup，可还原）|

## 核心区别一句话

- **源内去重**：预防性、单源、保守过滤。问"LLM 这次有没有重复造轮子"——写盘前把 dup 块踢掉，**不碰跨引用**（没东西可碰）。
- **跨源去重**：治疗性、全 wiki、彻底合并 + 跨引用修正。问"整个 wiki 累积了哪些重复"——合并后**必须**全 wiki 重写链接，否则留断链。

## 为什么不合并

侧重点不同：
- 源内去重必须**快、保守、不写盘前不动链接**——它是一个 inline 过滤器。
- 跨源去重必须**彻底、可回滚、改全 wiki 链接**——它是一个离线 reconcile。

合并成一个模块必然让其中一边的约束污染另一边（要么 ingest 被拖慢，要么 lint 不够彻底）。所以分开，名字不同（源内 / 跨源），职责清晰。

## 跨源去重的内部结构（3 文件分层）

```
cross_source_dedup.py        # CLI + 编排：phase 1 → phase 2，backup，report
  ├─ _dedup_merge.py         # phase 1 引擎：确定性同 title 合并（无 LLM）
  └─ _dedup.py               # phase 2 引擎：LLM 语义检测 + 合并（NashSU dedup.ts 移植）
```

这是**分层**（编排 + 两个 phase 引擎），不是重复实现——跟 Phase 2 拆成 `_stage_2_analyze` / `_stage_2_4_generation` 多文件一个模式。

## 何时用哪个

- **ingest 时**：自动跑源内去重（Stage 2.5），无需人工干预。
- **积累了一批 ingest 后**：手动跑跨源去重清理全 wiki：
  ```bash
  python3 scripts/cross_source_dedup.py --project /path/to/wiki            # phase 1 only
  python3 scripts/cross_source_dedup.py --project /path/to/wiki --semantic # phase 1 + 2
  python3 scripts/cross_source_dedup.py --dry-run                          # preview only
  ```
