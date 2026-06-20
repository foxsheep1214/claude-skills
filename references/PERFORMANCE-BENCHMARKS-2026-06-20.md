# OCR 性能基准测试库（HIGH 改进 #3）

## 📊 使用方式

### 1. 运行 ingest 后分析性能

```bash
# 消化一本书
python3 ingest.py /path/to/book.pdf

# 分析性能
python3 analyze_ocr_performance.py extract-tmp/ocr_log.jsonl
```

### 2. 生成详细报告

```bash
python3 analyze_ocr_performance.py extract-tmp/ocr_log.jsonl --report report.json
```

## 📈 报告格式

### 文本报告示例

```
======================================================================
OCR PERFORMANCE ANALYSIS REPORT
======================================================================

📊 SUMMARY
  Total time:           210.50 sec
  Chunks processed:     7
  Success rate:         100.0%
  Characters extracted: 870,000
  Throughput:           4,132 chars/sec

⏱️  CHUNK PERFORMANCE
  Chunk count:          7
  Min time:             19.00 sec
  Max time:             134.00 sec
  Avg time:             30.07 sec
  Median time:          30.00 sec

📄 CHARACTER EXTRACTION
  Total chars:          870,000
  Avg per chunk:        124,286
  Rate:                 4,132 chars/sec

🔧 JSON RECOVERY
  Truncations:          3
  Avg recovery rate:    100.0%

📦 FILE CLASSIFICATION
  Estimated size:       large
  Estimated pages:      350
======================================================================
```

### JSON 报告格式

```json
{
  "summary": {
    "total_chunks": 7,
    "failed_chunks": 0,
    "success_rate": 100.0,
    "total_time_sec": 210.5,
    "total_chars_extracted": 870000,
    "throughput_chars_per_sec": 4132
  },
  "chunk_performance": {
    "chunk_count": 7,
    "min_time_sec": 19.0,
    "max_time_sec": 134.0,
    "avg_time_sec": 30.07,
    "median_time_sec": 30.0,
    "stdev_time_sec": 37.5
  },
  "character_extraction": {
    "total_chars": 870000,
    "avg_chars_per_chunk": 124286,
    "chars_per_second": 4132
  },
  "json_recovery": {
    "truncation_count": 3,
    "avg_recovery_rate": 100.0,
    "min_recovery_rate": 100.0,
    "max_recovery_rate": 100.0
  },
  "file_classification": {
    "chunk_count": 7,
    "estimated_size": "large",
    "estimated_pages": 350
  }
}
```

## 🎯 性能基准对标

### 小文件基准（<5M, <50 页）
```
成本: 2-5 分钟
吞吐: 3,000-4,000 chars/sec
平均块时间: 20-25 sec
```

### 中等文件基准（5-50M, 50-300 页）
```
成本: 5-15 分钟
吞吐: 3,500-4,500 chars/sec
平均块时间: 25-35 sec
```

### 大文件基准（>50M, >300 页）
```
成本: 15-30 分钟
吞吐: 3,000-4,000 chars/sec
平均块时间: 30-45 sec
```

### PDF 类型对标

| 类型 | 速度 | 注意 |
|------|------|------|
| 文字 PDF | 快（PyMuPDF） | 直接提取，无 OCR |
| 扫描 PDF | 慢（minerU） | 需要 OCR + 模型初始化 |
| 混合 PDF | 中等 | 自动选择最优方法 |

## 🔍 日志分析高级用法

### 使用 jq 查询 JSONL 日志

```bash
# 查看所有事件类型
jq '.event_type' extract-tmp/ocr_log.jsonl | sort | uniq -c

# 过滤块完成事件
jq 'select(.event_type == "chunk_complete")' extract-tmp/ocr_log.jsonl

# 计算平均块时间
jq '.elapsed_sec' extract-tmp/ocr_log.jsonl | awk '{s+=$1} END {print s/NR}'

# 查找失败的块
jq 'select(.event_type == "chunk_error")' extract-tmp/ocr_log.jsonl

# 分析 JSON 截断恢复
jq 'select(.event_type == "json_truncation") | {batch: .batch, recovery_rate: (.recovered / .total * 100)}' extract-tmp/ocr_log.jsonl
```

### 使用 Python 分析

```python
import json

with open("extract-tmp/ocr_log.jsonl") as f:
    logs = [json.loads(line) for line in f]

# 计算总时间
total_time = sum(e["elapsed_sec"] for e in logs if e["event_type"] == "chunk_complete")
print(f"Total OCR time: {total_time:.2f} sec")

# 计算吞吐量
total_chars = sum(e["chars"] for e in logs if e["event_type"] == "chunk_complete")
print(f"Throughput: {total_chars / total_time:.0f} chars/sec")

# 分析错误率
chunks = [e for e in logs if e["event_type"] == "chunk_complete"]
errors = [e for e in logs if e["event_type"] == "chunk_error"]
print(f"Success rate: {len(chunks) / (len(chunks) + len(errors)) * 100:.1f}%")
```

## 🚀 改进建议

基于性能数据，可能的优化方向：

1. **吞吐量 < 3000 chars/sec**
   - 检查 CPU 使用率
   - 考虑并行化处理
   - 检查磁盘 I/O

2. **单块耗时 > 60s**
   - 减小块大小（MINERU_CHUNK_SIZE）
   - 检查网络延迟
   - 考虑本地模型缓存

3. **JSON 恢复率 < 90%**
   - 检查 API 响应大小限制
   - 考虑减小批处理大小
   - 增加超时时间

## 📋 建立基准库

建议在不同配置下运行基准测试：

```bash
# 测试 1：小文件（<10M）
python3 ingest.py small_file.pdf
python3 analyze_ocr_performance.py extract-tmp/ocr_log.jsonl --report small_benchmark.json

# 测试 2：中等文件（20-30M）
python3 ingest.py medium_file.pdf
python3 analyze_ocr_performance.py extract-tmp/ocr_log.jsonl --report medium_benchmark.json

# 测试 3：大文件（>50M）
python3 ingest.py large_file.pdf
python3 analyze_ocr_performance.py extract-tmp/ocr_log.jsonl --report large_benchmark.json

# 比较报告
python3 << 'PYEOF'
import json
for f in ["small_benchmark.json", "medium_benchmark.json", "large_benchmark.json"]:
    with open(f) as fp:
        data = json.load(fp)
        print(f"{f}: {data['summary']['throughput_chars_per_sec']} chars/sec")
PYEOF
```

---

**测试日期**：2026-06-20  
**目的**：建立性能基准库，支持 OCR 性能分析和优化  
**状态**：✅ 完成，可开始收集数据
