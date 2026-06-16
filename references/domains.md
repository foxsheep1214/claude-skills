# Domains — 知识库领域分类

> 用于消歧义、跨领域链接和知识图谱分析。每个概念页面的 frontmatter 中应包含 `domain` 字段。

---

## 领域列表

| domain slug | 中文名 | 说明 | 典型概念示例 |
|---|---|---|---|
| `circuit-fundamentals` | 电路基础 | 电阻/电容/电感、欧姆定律、KCL/KVL、交流分析 | Voltage, Current, Impedance |
| `power-electronics` | 电力电子 | 开关变换器、DC-DC、AC-DC、磁性元件 | Buck Converter, CCM, Duty Cycle |
| `thermal-management` | 热管理 | 传热学、散热设计、冷却技术 | Conduction, Fin Efficiency, Heat Sink |
| `emc` | 电磁兼容 | 电磁干扰、屏蔽、滤波、接地 | Common Mode Noise, EMI Radiation |
| `signal-integrity` | 信号完整性 | 传输线、反射、串扰、眼图 | Impedance Matching, Crosstalk |
| `digital-circuits` | 数字电路 | 逻辑门、时序、FPGA、存储器 | Flip-Flop, Setup Time, Metastability |
| `pcb-design` | PCB设计 | 叠层、布线、过孔、DFM | Thermal Via, Annular Ring, Impedance Control |
| `rf-microwave` | 射频微波 | S参数、Smith圆图、天线、功放 | Return Loss, Noise Figure, PAE |
| `radar-systems` | 雷达系统 | 阵列天线、波束成形、信号处理 | Phased Array, CFAR, Pulse Compression |
| `analog-circuits` | 模拟电路 | 运放、滤波器、ADC/DAC、传感器 | Op-Amp, Sallen-Key, Nyquist Rate |
| `semiconductor-devices` | 半导体器件 | MOSFET、IGBT、GaN、SiC | Threshold Voltage, SOA, Gate Charge |
| `reliability-engineering` | 可靠性工程 | 寿命预测、加速试验、失效分析 | MTBF, Arrhenius, Coffin-Manson |
| `general` | 通用 | 跨领域共用概念（数学、物理、方法论） | Fourier Transform, Uncertainty Principle |

---

## 消歧义规则

1. **同一概念名出现在不同领域 → 各领域独立页面**，如：
   - `switch-circuit-fundamentals.md` (电路基础：机械开关)
   - `switch-power-electronics.md` (电力电子：开关管)
   - 两者通过消歧义页 `Switch.md` 关联

2. **跨领域概念 → 标注 `general`**，在各领域页面中引用

3. **领域由 ingest 时根据书籍类型和章节上下文自动判定**，也可在 review 阶段手动修正

4. **消歧义页面**（`type: comparison`）列出所有同名词条的领域归属和简要定义

---

## 使用方式

### 在 frontmatter 中

```yaml
---
type: concept
title: "Conduction Heat Transfer"
domain: thermal-management
tags: [heat-transfer, conduction, Fourier]
---
```

### 在消歧义页中

```markdown
---
type: comparison
title: "Switch (消歧义)"
domain: general
---
# Switch (消歧义)

在不同领域有不同含义：
- [[switch-circuit-fundamentals]] — 机械开关（电路基础）
- [[switch-power-electronics]] — 开关管（电力电子）
```
