# Tracker II 需求论证文档格式规范

> 2026-05-20 确立，来自多次文档格式统一会话

## 列表项格式标准

**一级列表项**（`- ` 开头，顶格）统一格式：
```
- **加粗标签**：描述文字
```

**二级子项**（缩进2空格）：
```
  - 子项内容
```

**三级嵌套**（再缩进2空格）：
```
    - 嵌套内容
```

## 格式检查脚本

```python
from pathlib import Path

path = Path("/Users/skyfend/Documents/Tracker II/01_论证/总体需求及方案/Tracker II 需求论证.md")
content = path.read_text()
lines = content.split('\n')

issues = []
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('- ') and not stripped.startswith('- >') and not stripped.startswith('|-'):
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            colon_pos = stripped.find('：')
            key_part = stripped[:colon_pos] if colon_pos != -1 else stripped
            if '**' not in key_part:
                issues.append(f"Line {i}: {stripped[:100]}")

if issues:
    print(f"Found {len(issues)} non-bold list items:")
    for x in issues:
        print(x)
else:
    print("All top-level list items have bold keys. Format is consistent.")
```

## 常见格式错误

| 错误类型 | 示例 | 正确写法 |
|---------|------|---------|
| 一级列表无加粗 | `- 方位角扫描范围：...` | `- **方位角扫描范围**：...` |
| 子项未缩进 | `- 10km处：**≤100m**` | `  - 10km处：**≤100m**` |
| 多级嵌套缩进不足 | `    - 子项` | `      - 子项` |
