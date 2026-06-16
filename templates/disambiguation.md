# Disambiguation Page Template

用于同一术语在多个领域有不同含义时的消歧义导航。

Saved as `wiki/concepts/<term>.md` (the bare term), or `wiki/comparisons/<term>-disambiguation.md`.

---

## Template

```markdown
---
type: comparison
title: "<TERM> (消歧义)"
domain: general
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [disambiguation]
related: []
---

# <TERM> (消歧义)

**<TERM>** 在不同领域有不同含义：

| 领域 | 含义 | 页面 |
|------|------|------|
| circuit-fundamentals | <brief definition> | [[<term>-circuit-fundamentals]] |
| power-electronics | <brief definition> | [[<term>-power-electronics]] |
| thermal-management | <brief definition> | [[<term>-thermal-management]] |
| <other domain> | <brief definition> | [[<term>-<other-domain>]] |

## 参见

- [[<related concept 1>]]
- [[<related concept 2>]]
```

## 命名规则

1. 消歧义页使用裸术语名（如 `Switch.md`）
2. 各领域的特定页面添加领域后缀（如 `switch-circuit-fundamentals.md`）
3. 后缀使用 domain slug（见 `references/domains.md`）
4. 各领域页面在 `## 参见` 中链接回消歧义页

## 何时创建

- 同一术语已存在 ≥2 个不同领域的独立页面时，创建消歧义页
- 新建概念页时，若检测到同名但不同领域的已有页面，自动触发消歧义流程
