# Ingest 流程改进计划（基于实际测试）

## 📊 实测数据（Encyclopedia Vol 1 - 28M, 302页）

### 当前性能
- **OCR 阶段**：~3.5 分钟（第 1 块 134s，后续块 19-31s）
- **图片提取**：~386 张
- **文本提取**：~870K 字符
- **内存占用**：~435MB

---

## 🔴 Critical 优化（立即实施）

### 1. 进度显示改进
**问题**：用户无法知道总耗时，最后一块运行了多久

**解决方案**：
```python
# ingest.py 修改
def ocr_chunk(chunk_idx, total_chunks, start_time):
    elapsed = time.time() - start_time
    avg_time = elapsed / chunk_idx if chunk_idx > 0 else 0
    eta = avg_time * (total_chunks - chunk_idx)
    
    print(f"  [{chunk_idx}/{total_chunks}] " + 
          f"[{chunk_idx*100//total_chunks}%] " +
          f"ETA: {eta:.0f}s — ")
```

### 2. 错误恢复机制
**问题**：如果 OCR 块失败，整个流程停止

**解决方案**：
- 每个块都应该有重试机制（最多 3 次）
- 失败块应该记录详细错误信息
- 提供"继续"选项让用户跳过失败的块

---

## 🟡 High 优化（本周）

### 1. minerU 预热优化
**问题**：第一块 OCR 耗时 134s，之后为 19-31s（7 倍差异）

**解决方案**：
```python
# Stage 0 前的预热
def warmup_mineru_api():
    # 发送一个小的测试调用（1-2 页）
    response = mineru_api.process_page(sample_page, metadata)
    print(f"  [warmup] minerU ready ({response.time:.1f}s)")
```

**预期效果**：减少冷启动延迟，总时间从 3.5 分钟 → 2.5 分钟

### 2. 内存优化
**问题**：435MB 内存占用，对超大文件（>100M）可能有问题

**解决方案**：
- 流式处理：处理完一个块后立即释放其内存
- 图片流式写入：不全部保存在内存中
- 定期 GC：处理完大块后强制垃圾回收

### 3. 日志改进
**问题**：错误信息不够详细，难以调试

**解决方案**：
```python
# 添加结构化日志
logger.info("ocr_chunk", {
    "chunk": chunk_idx,
    "pages": f"{start_page}-{end_page}",
    "time_sec": elapsed,
    "chars_extracted": char_count,
    "images_extracted": image_count,
    "cache_hit": was_cached
})
```

---

## 🟢 Medium 优化（下周）

### 1. 暂停/恢复功能
允许用户在长时间运行中暂停，保存进度，之后恢复

### 2. 并行化 OCR
如果硬件支持（多核 CPU），可以并行处理多个块
- 前提：minerU 支持并发调用（需要验证）
- 风险：内存占用会成倍增加

### 3. 性能基准测试
- 不同大小的 PDF：小（<5M）、中（5-50M）、大（>50M）
- 不同类型：文字 PDF vs 扫描 PDF
- 目标：建立性能预测模型

---

## 📝 实施路线图

### Week 1（本周）
- [ ] 实施进度显示改进
- [ ] 添加错误重试机制
- [ ] minerU 预热优化

### Week 2（下周）
- [ ] 内存优化和流式处理
- [ ] 结构化日志系统
- [ ] 性能基准测试

### Week 3+
- [ ] 暂停/恢复功能
- [ ] 并行化 OCR（可选）
- [ ] 性能调优基于基准测试数据

---

## 🎯 改进目标

| 指标 | 当前 | 目标 | 改进 |
|------|------|------|------|
| OCR 耗时 | 3.5 min | 2.0 min | -43% |
| 内存占用 | 435 MB | 200 MB | -54% |
| 错误恢复 | 无 | 3 次重试 | 提升可靠性 |
| 用户体验 | 无反馈 | ETA + 进度条 | 显著改善 |

---

## 关键发现

✅ **架构设计良好**
- 自动降级到 minerU ✓
- 分块处理避免超时 ✓
- 缓存复用提升性能 ✓

⚠️ **需要改进的地方**
- 缺少实时反馈（用户不知道何时完成）
- 缺少错误恢复（一个块失败则全部失败）
- 冷启动延迟较大（第一块特别慢）

---

**状态**：改进计划确定  
**下一步**：等待第一本书的 ingest 完成，观察后续阶段的问题
