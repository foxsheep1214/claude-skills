# Scanned PDF OCR Pipeline (无源器件篇端到端，2026-06-11)

适用于**扫描版 PDF**（无文本层，PyMuPDF `get_text()` 全空）的完整 OCR pipeline。从 HardwareWiki「无源器件篇」312 页全本 OCR 实战沉淀。其它项目的扫描版 PDF 都可以复用这个流程。

## 何时使用这条 pipeline

- PDF 是**扫描版**（无 text layer）：`fitz.open(p).get_text()` 返回空或近乎空。
- PDF 内有中文/数学公式/硬件图等需要**像素级识别**的内容。
- 不适用：text-layer PDF（直接 PyMuPDF `get_text()` 即可，毫秒级）。

## 完整流程

```
1. PyMuPDF 预检（5 秒）
   ├─ 全 312 页 `get_text()` 字符数 = 0 → 确认扫描版
   ├─ 全 312 页 `get_pixmap(dpi=72).samples` → PIL Image → 算 avg brightness
   └─ avg > 250 → 空白页（4 页典型，pilot 实测 bimodal 分布无 overlap）
2. PyMuPDF 渲染所有页 PNG @ 150 DPI（~30 秒）
3. 跳过空白页（avg > 250），剩余页按 batch_size=5 分批
4. 调 minimax `anthropic/v1/messages`，每批 5 张图，content blocks 数组（详见 multimodal-vlm-pitfalls.md §5 endpoint 矩阵）
5. 响应按 `## 第N页` regex 切分 → 写到 ocr/p<NNN>.txt
6. 异常检测：chars<200 或无中文 → 标 _failed_pages.txt
7. **retry 必须 catch 所有 transient failure**（关键，2026-06-11 教训）：
   - HTTP 5xx（500/520/529）+ `requests.exceptions.RequestException`
   - **ReadTimeout / ConnectTimeout / ConnectionError / ChunkedEncodingError 必须显式 catch 并 raise 自定义可重试异常**
   - **Naive retry（仅 catch HTTPError 或仅 retry 529）会让进程 crash**——无源器件篇第一次 batch30 就是因为 `requests.ReadTimeout` 没被 catch 直接 exit code 1
   - Retry 策略：最多 8 次 + exponential backoff (base 8s, cap 90s) + ±30% jitter
8. 进度持久化：每批写一次 _stats.json → 崩溃可恢复
9. 失败 batch 用独立脚本 retry（不要从头跑）：读 _stats.json 找 fail batch_id，单独跑这些 batch
10. 模型漏页补救：response 里"## 第N页"缺失的页标 missing from response，单页 sequential 重 OCR/caption 即可（不要全本重跑）
```

## 关键技术决策

### 为什么是 minimax 而不是 MinerU 本地 VLM

用户（胡杨）2026-06-11 明确选择 minimax 路径（"stage0 ocr 也走 minimax"）。**不要默认 MinerU**——硬件书 OCR 在 16GB Mac 上有 gotcha #21 VLM + MPS 内存压力，多图 API 调用比本地 VLM 简单且并发好。

### minimax endpoint 矩阵（澄清，2026-06-11 教训）

| endpoint | 多图支持 | auth header | 适用 |
|---|---|---|---|
| `https://api.minimaxi.com/anthropic/v1/messages` | ✅ 单请求 content blocks 数组 | `Authorization: Bearer<key>` | **OCR / caption 批量任务（首选）** |
| `https://api.minimaxi.com/v1/coding_plan/vlm` | ❌ 只支持单图（image_url 单字符串） | `Authorization: Bearer<key>` | mmx CLI 内部用，单图 sequential |

**不要混淆**。`mmx vision describe --image X` 走 v1/coding_plan/vlm（sequential 单图）。**批量多图必须直接调 `anthropic/v1/messages`**。

### 为什么 5 张/批（而不是 8 张/批）

电源篇 caption 实测用 8 张/批。但 OCR 任务的 prompt+响应 tokens 比 caption 大很多：
- 单张扫描页 PNG ~500KB（base64 后 ~700KB）
- 输入 token ~2000/页（5 张图 = 10K tokens）
- 输出 token ~500-3000/页（dense 正文可达 3000/页）
- 8 张/批时 input 16K + output ~12-24K → 可能撞 cluster slot（529 overload）

5 张/批实测 23.5 秒，token 控制在 10K/批，比较稳。

### max_tokens 预留

**关键**：OCR 任务 `max_tokens: 12000`（5 张/批）。dense 扫描页输出可能 2000-3000 tokens/页，5 张 = 10-15K tokens。`max_tokens: 8192` 在密集正文页可能触发截断（stop_reason=max_tokens）。

### 为什么用 PyMuPDF 而不是 pdf2image

PyMuPDF (`fitz`) 在 skill venv 里现成可用，不需要额外装 poppler。`get_pixmap(dpi=150)` 直接拿到 RGB bytes，写 PNG 一步到位。

## PyMuPDF avg brightness 阈值的验证方法（避免拍脑袋）

`avg > 250` 阈值看似拍脑袋，实测 312 页分布 bimodal：

```
>=253 (基本空白): 1
250-253: 3
245-250: 55   ← 下一邻近
240-245: 167
<240: 86
```

最坏情况是 250.2（p122/p243）和最低的非空白 245.1（p185），gap 5.1。**0% 误杀**。但**必须先做这个分布验证**（5-10 页样本），不要默认 250 适用于所有 PDF——不同扫描源可能有差异。

```python
# 验证脚本（5 秒跑完）
from collections import Counter
brightness = []
for i in range(len(doc)):
    pix = doc[i].get_pixmap(dpi=72)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    avg = sum(v*c for v,c in enumerate(img.histogram())) / sum(img.histogram())
    brightness.append(avg)
# 然后用 buckets (>=253 / 250-253 / 245-250 / ...) 看分布
```

## 完整工作脚本（核心骨架，含正确 retry）

参考架构（完整可执行版本见 `scripts/scanned_pdf_ocr.py`）：

```python
import fitz, requests, base64, json, re, time
from PIL import Image
from pathlib import Path

class BatchError(Exception):
    """可 retry 的 batch 错误 — 必须 catch HTTP5xx + 所有 requests.RequestException 子类"""
    def __init__(self, kind, detail):
        self.kind = kind; self.detail = detail

def call_batch(page_nums, manifest, api_key):
    content = [{"type": "text", "text": OCR_PROMPT}]
    for pn in page_nums:
        b64 = base64.standard_b64encode(manifest[pn]["png"].read_bytes()).decode()
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    payload = {"model": "MiniMax-M3", "max_tokens": 12000,
               "messages": [{"role": "user", "content": content}], "temperature": 0.1}
    try:
        resp = requests.post(
            "https://api.minimaxi.com/anthropic/v1/messages",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "anthropic-version": "2023-06-01"},
            timeout=(30, 240))  # (connect, read) 双 timeout
    except requests.exceptions.ReadTimeout as e:
        raise BatchError("timeout", f"ReadTimeout 240s")
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError) as e:
        raise BatchError("network", f"{type(e).__name__}")
    except requests.exceptions.RequestException as e:
        raise BatchError("network", f"{type(e).__name__}")

    if resp.status_code == 429:
        raise BatchError("http_429", "rate limited")
    if 500 <= resp.status_code < 600:
        raise BatchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise BatchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")

    data = resp.json()
    if data.get("base_resp", {}).get("status_code") != 0:
        raise BatchError("api_error", str(data.get("error", {}).get("message", ""))[:200])

    text = "".join(c["text"] for c in data["content"] if c.get("type") == "text")
    return text, data.get("usage", {})

def call_with_retry(page_nums, manifest, api_key, batch_label, max_retries=8):
    """exponential backoff + jitter — 8 次 base 8s cap 90s"""
    for attempt in range(max_retries):
        try:
            return call_batch(page_nums, manifest, api_key)
        except BatchError as e:
            if attempt < max_retries - 1:
                wait = min(8 * (2 ** attempt), 90)
                wait = wait * (0.7 + 0.6 * (hash((batch_label, attempt)) % 100) / 100)
                time.sleep(wait)
            else:
                raise  # 最后一轮失败，让调用方处理

def parse_pages(text):
    """响应按 '## 第N页' 切分"""
    parts = re.split(r"##\s*第\s*(\d+)\s*页", text)
    out = []
    for i in range(1, len(parts)-1, 2):
        try:
            n = int(parts[i]); body = parts[i+1].strip().strip("-").strip()
            out.append((n, body))
        except ValueError: continue
    return out
```

## 实测数据（无源器件篇 312 页）

| 指标 | 值 |
|---|---|
| PDF 大小 | 123 MB |
| 总页数 | 312 |
| 空白页 (avg>250) | 4（p4/p6/p122/p243）|
| 待 OCR 页 | 308 |
| 批数 | 62（5 页/批）|
| 单批耗时 | ~24-60 秒（cluster 压力大时慢）|
| 5 张 sample 23.5s 验证 | input 10505 + output 2727 tokens |
| 异常页率 | ~5-10%（HTTP500 / 部分页缺失 / 输出字符少）|
| **retry 100% 有效**：22 个 fail batch 重跑后 100% 转 ok（实测 10/10，11/11，22/22 等多次）|
| 全本预估 | ~25-90 分钟（取决于 cluster；首次跑 30 batch + retry 40 batch 共 90 min）|
| 备份位置 | `.llm-wiki/extract-tmp/<slug>/` |

## 异常处理

### 空白页 (avg > 250)

跳过 OCR 不调 API。但**保留 PNG 文件**（4 张空白页 PNG 还是渲染了，只是不送 OCR）。

### 异常页（OCR 失败/输出字符少/无中文）

写入 `_failed_pages.txt`，格式：
```
p007  chars=145, chinese=no
p022  missing from response
p155  HTTP 500 after 3 retries
```

待所有 batch 跑完后**补救**——按 `scripts/recover_missing.py` 模式：单页 sequential 重 OCR/caption。

### HTTP 500（非 529）

minimax cluster 也会返回 500（不是 overloaded，是真 server error）。**必须 retry**——实测 22/22 个 500 batch 在 retry 后全部成功。retry 的关键不是"区分 500/529"，而是**所有 5xx 都 retry + 所有网络异常都 retry**。

### ReadTimeout / ConnectionError（关键 pitfall）

`requests.exceptions.ReadTimeout` 是这次 batch30 crash 的直接原因。**第一次写脚本时只 catch HTTPError，导致 server 端 read 不响应时进程直接 crash**（exit code 1，无 _stats.json 写入）。

**修法**（见上面 call_batch 完整版）：
- 显式 catch `requests.exceptions.RequestException`（父类，覆盖所有子类）
- 或显式 catch `ReadTimeout` + `ConnectTimeout` + `ConnectionError` + `ChunkedEncodingError`
- 抛 `BatchError` 让 retry 循环接走

**教训**：retry 不只是 backoff 数字问题，**catch 的异常类型必须全**。第一次写 Naive retry 是常见错误。

### 模型坍缩（空白页触发循环生成）

实测：空白页 + OCR prompt（"逐字抽取"严格约束）会让 M3 陷入模式坍缩，循环输出某段外文（pilot p4 73 秒循环 50+ 次 "言いだす"）。**前置 PyMuPDF avg>250 预筛**是最佳防护。

### 模型漏页（response 里"## 第N页"缺失）

5-10% 概率某些 batch 会漏掉个别页（如 batch17 整批漏 p88-92；batch36/42 各漏 1 页）。

**补救策略**（不要全本重跑）：
- 读 _stats.json 找 failed batch
- 单独调 API 重跑这些页（一次 sequential 调用即可）
- Stage0.6 caption 同理

## Stage 0 之后的下一步

OCR 全本跑完后，下一步是 Stage 1（Global Digest）+ Stage 2（Generation）—— 这些是 LLM 调用，对 OCR 后的 .txt 文件做分析。**Stage 1-6 不在本 reference 范围**，见 `references/ingest-stages-mandatory.md`。

## 修订记录

- **2026-06-11**：初版，源于 HardwareWiki 无源器件篇 312 页 OCR 全本实战
- **2026-06-11**：修订 retry 逻辑——必须 catch 所有 requests.RequestException 子类（ReadTimeout 是 batch30 crash 的根因）；retry 次数从 3 升到 8 + exponential backoff (8s base) + jitter；retry 100% 有效实测（22 个 fail batch → 22 个 ok）；新增 PyMuPDF 阈值验证方法（避免拍脑袋）；新增 endpoint 矩阵（`anthropic/v1/messages` vs `v1/coding_plan/vlm`）；新增"模型漏页补救"策略