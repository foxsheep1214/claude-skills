# NashSU 分离架构重构计划（2026-06-20）

## 🎯 核心目标

改进 improved-wiki 的架构，采用 NashSU 的**分离命令模式**和**每 stage 立即验证**的方式。

```
现在 (问题)：
  ingest.py
    ├─ Stage 0-3.5 (生成)
    ├─ Validation (最后，非强制)
    └─ return "ok" (可能不完整)

改进后 (目标)：
  ingest.py
    ├─ Stage 0 + _verify_stage_0() [fail fast]
    ├─ Stage 1 + _verify_stage_1() [fail fast]
    ├─ Stage 2 + _verify_stage_2() [fail fast]
    ├─ Stage 3 + _verify_stage_3() [fail fast]
    ├─ Stage 3.5 + _verify_stage_3_5() [fail fast]
    └─ return "ok" (全部通过)

  validate.py [独立命令]
    └─ 详细的离线验证（用于 CI/CD）

  lint.py [独立命令]
    └─ 全局 wiki 一致性检查

  graph.py [独立命令]
    └─ 知识图谱构建
```

---

## 📋 实施分三个 Phase

### Phase 1: 基础设施（本周完成）✅ 进行中

**目标**：为每个 stage 添加立即验证，实现 fail-fast。

**任务**：
- [x] 创建 `_stage_validators.py` 模块
  - verify_stage_0() - 文本提取验证
  - verify_stage_1() - 图片/Caption 验证
  - verify_stage_2() - 分析验证
  - verify_stage_3() - 生成验证
  - verify_stage_3_5() - Embedding 验证

- [ ] 修改 ingest.py：在每个 stage 后添加验证调用
  ```python
  # 示例
  text = extract_text(file)
  if not verify_stage_0(text):
      raise StageValidationError("Stage 0 failed")
  ```

- [ ] 测试 fail-fast 行为：
  - [ ] 测试 Stage 0 失败时，立即停止
  - [ ] 测试 Stage 1 失败时，不浪费资源
  - [ ] 验证错误信息清晰

**预期效果**：
- ingest 变快（fail fast）
- 错误更快被发现
- 用户体验改善

---

### Phase 2: 命令分离（下周）

**目标**：分离 validate/lint/graph 为独立命令。

**任务**：
- [ ] 重构 validate_ingest.py
  - 从"ingest 的最后一步"变为"独立命令"
  - 添加详细的验证报告格式
  - 支持离线运行（CI/CD）

- [ ] 提取 lint 逻辑为独立的 lint.py
  - 全局 wiki 一致性检查
  - 可异步运行
  - 生成改进建议

- [ ] 提取 graph 逻辑为独立的 graph.py
  - 知识图谱构建
  - 确定性算法
  - 可按需运行

**命令行接口**：
```bash
# 快速 ingest（Stage 0-3.5，每 stage 验证）
$ ingest file.pdf
  ✅ All stages passed

# 详细验证（离线）
$ validate file.pdf
  ✅ Stage 1.1: Text extraction ..................... PASS
  ✅ Stage 1.2: Image extraction ................... PASS
  ❌ Stage 2.5: Query generation .................. FAIL (no queries generated)
  
# 全局检查（可选）
$ lint
  ℹ️  Found 3 orphan pages
  ℹ️  Found 2 broken references

# 构建索引（可选）
$ graph
  ✅ Built knowledge graph: 234 nodes, 567 edges
```

---

### Phase 3: 性能优化和文档（第三周）

**目标**：优化性能，完善文档。

**任务**：
- [ ] 性能测试和优化
  - [ ] 测试 fail-fast 带来的时间节省
  - [ ] 优化验证函数（避免重复检查）
  - [ ] 考虑验证的并行化

- [ ] 编写文档
  - [ ] 用户指南（三个命令的使用方式）
  - [ ] 开发者指南（如何添加新 stage）
  - [ ] 迁移指南（从旧设计升级）

- [ ] 更新 CI/CD
  - [ ] ingest 作为快速检查
  - [ ] validate 作为详细检查
  - [ ] lint 作为代码质量检查

---

## 🏗️ Phase 1 的详细设计

### 修改 ingest.py 的伪代码

```python
# 当前（问题）
def ingest_one_source(config, raw_file):
    text = extract_text(raw_file)
    images = extract_images(raw_file)
    captions = caption_images(images)
    
    analysis = analyze_chunks(text)
    generation = generate_concepts(analysis)
    
    files_written = write_files(generation)
    save_cache(...)
    
    # 最后才验证（延迟发现问题）
    _auto_validate_ingest(config, raw_file)  # 非强制
    
    return {"status": "ok"}  # 可能不完整


# 改进（Phase 1）
def ingest_one_source(config, raw_file):
    # Stage 0: 提取文本
    text = extract_text(raw_file)
    if not verify_stage_0(text):  # ← 立即验证
        raise StageValidationError("Stage 0: 文本提取失败")
    print("✅ Stage 0 passed")
    
    # Stage 1: 提取图片和 Caption
    images = extract_images(raw_file)
    captions = caption_images(images)
    if not verify_stage_1({"count": len(images)}, captions):  # ← 立即验证
        raise StageValidationError("Stage 1: 图片提取失败")
    print("✅ Stage 1 passed")
    
    # Stage 2: 分析
    analysis = analyze_chunks(text)
    if not verify_stage_2(analysis):  # ← 立即验证
        raise StageValidationError("Stage 2: 分析失败")
    print("✅ Stage 2 passed")
    
    # Stage 3: 生成
    generation = generate_concepts(analysis)
    if not verify_stage_3(generation):  # ← 立即验证
        raise StageValidationError("Stage 3: 生成失败")
    print("✅ Stage 3 passed")
    
    # Stage 3.5: Embeddings
    embeddings = stage_3_5_embeddings(generation)
    if not verify_stage_3_5(embeddings):  # ← 立即验证
        raise StageValidationError("Stage 3.5: Embeddings 失败")
    print("✅ Stage 3.5 passed")
    
    # 写入文件和更新缓存
    files_written = write_files(generation)
    save_cache(...)
    
    return {"status": "ok"}  # ← 到这里时，全部都通过了


# 处理异常（fail fast）
try:
    result = ingest_one_source(config, raw_file)
except StageValidationError as e:
    print(f"❌ {e}")
    return {"status": "failed", "error": str(e)}
```

### 导入改变

```python
# ingest.py 顶部添加
from _stage_validators import (
    verify_stage_0,
    verify_stage_1,
    verify_stage_2,
    verify_stage_3,
    verify_stage_3_5,
    StageValidationError,
)
```

---

## 💡 关键优势

### 1. **Fail Fast** - 快速失败
```
旧：ingest 用 1 小时完成 → 最后 5 分钟发现错误 → 浪费 55 分钟
新：Stage 0 失败 → 1 分钟内就知道 → 快速修复
```

### 2. **清晰的职责** - 关注点分离
```
ingest  = 生成（Stage 0-3.5）
validate = 检查（详细报告）
lint    = 优化（全局检查）
graph   = 索引（知识图谱）
```

### 3. **易于调试** - 问题隔离
```
旧：validation 显示 5 个失败 → 难以判断根本原因
新：Stage 1 失败 → 明确知道是图片提取问题
```

### 4. **可扩展** - 易于添加新 stage
```
添加新 stage 时：
1. 在 _stage_validators.py 添加 verify_stage_X()
2. 在 ingest.py 的相应位置调用验证
3. 完成！
```

---

## ⚠️ 风险和缓解措施

### 风险 1：向后兼容性
**问题**：现有的 ingest cache 和输出格式可能不兼容  
**缓解**：
- [ ] 添加版本号到 cache 格式
- [ ] 提供迁移脚本（旧→新）
- [ ] 在文档中说明变更

### 风险 2：验证规则定义
**问题**：什么是"通过"？什么是"失败"？什么是"跳过"？  
**缓解**：
- [ ] 在 _stage_validators.py 中明确定义每个验证规则
- [ ] 添加注释和示例
- [ ] 为复杂的规则添加单元测试

### 风险 3：错误恢复
**问题**：Stage 失败后应该怎么办？允许重试吗？  
**缓修**：
- [ ] 不允许跳过任何 stage（要么全部通过，要么全部失败）
- [ ] 允许用户重新运行 ingest（会自动重试）
- [ ] 不自动清理部分完成的文件（用户自己决定）

---

## 📊 预期改进效果

| 指标 | 现在 | 改进后 | 提升 |
|------|------|--------|------|
| 错误发现时间 | 全 pipeline 完成后 | 当前 stage 完成后 | ↓ 50-90% |
| ingest 失败的成本 | 高（浪费时间） | 低（fail fast） | ↓ 显著 |
| 调试难度 | 高（多个问题混在一起） | 低（问题隔离） | ↓ 显著 |
| 代码维护 | 困难（混杂） | 容易（分离） | ↑ 显著 |
| 新 stage 添加 | 需要修改多处 | 仅需添加验证函数 | ↑ 显著 |

---

## 📁 相关文件

```
✅ scripts/_stage_validators.py
   └─ 新创建的验证模块（Phase 1）

📝 ingest.py
   └─ 需要修改：在每个 stage 后添加验证调用（Phase 1）

📝 validate_ingest.py
   └─ 需要分离为独立命令（Phase 2）

📝 lint.py
   └─ 需要分离为独立命令（Phase 2）

📝 graph.py
   └─ 需要分离为独立命令（Phase 2）
```

---

## 🎓 参考

**相关文档**：
- [VALIDATION-ARCHITECTURE-2026-06-20.md](VALIDATION-ARCHITECTURE-2026-06-20.md) - 当前架构分析
- [STAGE-3-5-EMBEDDINGS-MANDATORY-2026-06-20.md](STAGE-3-5-EMBEDDINGS-MANDATORY-2026-06-20.md) - Embedding 强制化

**NashSU 参考**：
- 分离命令架构：ingest / validate / lint / graph
- 每 stage 后立即验证
- Fail fast 设计

---

**状态**：Phase 1 进行中 🔄  
**下一步**：修改 ingest.py 在每个 stage 后调用验证
