---
description: "Image captioning strategy for ingest Stage 0.6 — A) 8 images per request (preferred), B) Anthropic Message Batches API (cost), C) mmx CLI single-image (fallback). Verified benchmarks from HardwareWiki 电源篇 738-image run (2026-06-11)."
tags: [vlm, captioning, batch, mmx, minimax, strategy]
related: [multimodal-vlm-pitfalls, ingest-stages-mandatory §0.6, SKILL.md §7]
---

# Image Captioning 策略

Stage 0.6 captioning 的 4 种实现方式，按优先级排序。基于 **2026-06-11 HardwareWiki 电源篇 738 张图实测**（不是凭空推荐）。

---

## 决策树

```
需要跑多少张图 caption？
│
├─ < 50 张（小型项目 / 单本书 / 验证阶段）
│   │
│   └─ 走 C 方式（mmx CLI 单图）—— 工程简单，无需写代码
│       $ mmx vision describe --image foo.jpg --prompt "..."
│       约 7 秒/图（含 CLI 启动开销）
│
├─ 50-1000 张（中大型项目）
│   │
│   └─ 走 A 方式（8 张图/请求，HTTP 直发）—— 速度 + token 双优
│       1 个 POST 含 8 张图 + 共享 system prompt
│       约 2-3 秒/张（vs 单图 6-8 秒/张）
│       见 scripts/caption_batch.py
│
├─ > 1000 张（超大批量）+ 不急（可等 24h）
│   │
│   └─ 走 B 方式（Anthropic Message Batches API）—— 50% 折扣
│       单批 10,000 请求上限
│       适合夜间 cron 跑
```

---

## 3 种方式详解

### A. **优选** — 8 张图/请求，HTTP 直发

**实施**：`scripts/caption_batch.py`（已实现，参数化）

```python
# 1 个 messages API 调用，content 包含 8 张图（base64）+ 1 个 text prompt
content = [{"type": "text", "text": "8 张图按序描述，输出 JSON 数组..."}]
for i, img in enumerate(images):
    content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
    })
payload = {
    "model": "MiniMax-M3",
    "max_tokens": 2048,  # batch_size × 256
    "system": "你是硬件知识库图像解读专家...",
    "messages": [{"role": "user", "content": content}],
}
```

**实测数据**（2026-06-11，电源篇 738 张图）：
| 指标 | A 方式 | 单图单请求 | 节省 |
|---|---|---|---|
| 速率 | 2-3 秒/张 | 7.5 秒/张 | **3 倍快** |
| input tokens/张 | ~300 | ~370 | ~20% |
| output tokens/张 | ~40 | ~55 | ~25% |
| 总耗时（738 张） | 21-35 分钟 | 92 分钟 | **62%** |

**关键设计**：
- **强制 JSON 数组输出**（`[{"idx":1, "caption":"..."}, ...]`）—— 不要 LLM 自由发挥
- `max_tokens = batch_size × 256`（每张预留 256 token）
- Prompt 末尾明确"8 个对象都要有，idx 与图顺序一致"

**适用**：50-1000 张图的主流选择。

### B. **成本优选** — Anthropic Message Batches API

**适用**：> 1000 张 + 可等 24h 的非实时任务。

```python
# 提交 1 批最多 10,000 请求
batch = requests.post(f"{BASE}/v1/messages/batches",
    json={"requests": [
        {"custom_id": f"img-{i}", "params": <标准 messages 参数>}
        for i in range(10000)
    ]})
# 24h 内轮询 processing_status == "ended"
# 下载 results_url
```

**优势**：50% 折扣（成本减半）

**劣势**：24h 异步（不能实时看进度）

**适用**：夜间 cron ingest、批量归档、数据准备。

### C. **工程友好** — mmx CLI 单图（备份）

**适用**：< 50 张 / 验证阶段 / 单图调试。

```bash
# 单图：CLI 启动 + 网络 + LLM ≈ 7.3 秒
mmx vision describe --image foo.jpg --prompt "请用中文描述这张图..."
# 输出：完整 JSON，content 字段是 caption

# shell 循环多图（不上传）：
for img in *.jpg; do
  mmx vision describe --image "$img" --prompt "..." --quiet
done
```

**实测对比**（2026-06-11，3 张图）：
| 方式 | 耗时 |
|---|---|
| A（8 张/请求） | **2.83 秒/张** |
| C（mmx shell 循环） | **6.4 秒/张**（慢 2.3 倍）|
| C（mmx 启动开销占比） | 7.3 秒（含 CLI 启动）/ 6.4 秒（稳态）|

**B' 子方式（mmx file upload + file-id）**：❌ **404 不可用**。`mmx file upload` 走的是通用文件检索 endpoint，不是 vision 专用 file-id。

**为什么 C 比 A 慢**：
- 每次都重新传 system prompt（无共享）
- mmx CLI 启动开销（python 解释器 + 配置加载 ≈ 0.5-1 秒）
- 无 base64 共享优化
- 串行调用无并发

**价值**：
- **工程简单**（不用写 Python 循环代码）
- **错误处理内置**（CLI 自动 retry + timeout）
- **官方维护**（跟随 API 变化）

**适用**：**作为 A 失败时的备份**，或少量图调试。

---

## 实测对比表（2026-06-11，电源篇 738 张）

| 方式 | 速率 | token 成本 | 工程复杂度 | 中文质量 | 适用规模 |
|---|---|---|---|---|---|
| **A** 8 张/请求 | **2-3 秒/张** | 低（共享 system） | 中 | ✅ 高 | 50-1000 |
| **B** Batches API | 同 A | **50% off** | 高（轮询） | ✅ 高 | > 1000 |
| **C** mmx shell 循环 | 6-8 秒/张 | 高（无共享） | **低** | ✅ 高 | < 50 |
| 单图单请求（基线） | 7.5 秒/张 | 中 | 低 | ✅ 高 | 任意 |

---

## 自动化策略（推荐默认）

**默认走 A**（`scripts/caption_batch.py`），失败 fallback：

```python
def caption_with_fallback(images, batch_size=8):
    # 1. 主路径：MiniMax M3 8 张/请求
    try:
        return caption_batch_minimax(images, batch_size)
    except RateLimitError:
        # 2. 退避 60s 后重试
        time.sleep(60)
        return caption_batch_minimax(images, batch_size)
    except NetworkError:
        # 3. 切 mmx CLI（工程简单）
        for img in images:
            mmx_run(img)
        return parse_mmx_outputs()
```

---

## 修订记录

- **2026-06-11**：初版，基于 738 张电源篇实测
- **2026-06-11**：删除 D 方式（MinerU 1.2B），按用户指令"删 minerU 备份"；保留 A/B/C 三种
