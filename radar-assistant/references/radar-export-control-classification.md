---
title: Radar Export Control Classification — ITAR / EAR / Wassenaar
date: 2026-06-09
sources:
  - 22 CFR 121 (USML) — eCFR 2026-06-04
  - 15 CFR 774 Supp.1 (CCL) — eCFR 2026-06-04
  - Wassenaar ML + Dual-Use List 2025 Corrigendum
applicable_to: Tracker II (counter-UAV radar)
---

# 雷达出口管制分类速查

> **核心结论**：作用距离不是军/民雷达的清晰边界。**真正边界是清单制**——三组互斥清单（USML 军用 / CCL 两用 / EAR99 民用）按"功能 + 数值参数"组合触发。
> 作用距离只是组合判据的**一个**参数，且**不能**孤立使用。

---

## 三层清单结构

```
┌─────────────────────────────────────────────────────────┐
│ USML Category XI(a)(3) — 军用雷达（ITAR 管控）           │  ← 出口需国务院 DDTC 许可证
│   触发即"明显军品"                                       │
├─────────────────────────────────────────────────────────┤
│ EAR ECCN 6A008 / 6A108 — 两用雷达（商务部 BIS 管控）     │  ← 出口需 BIS 许可证
│   触发即"军民两用"                                       │
├─────────────────────────────────────────────────────────┤
│ EAR99 — 民用（无管制）                                   │  ← 自由出口
│   不命中以上任何清单                                      │
└─────────────────────────────────────────────────────────┘
```

一个现代 AESA 机载雷达几乎必然**同时**触发 USML + ECCN——出口需同时走两套许可证。

---

## 关键阈值速查表

### 军用（ITAR USML Cat XI(a)(3)）— 任一条件满足即触发

| 子条 | 触发条件 | 备注 |
|------|---------|------|
| (i) | 机载雷达 + 维持目标位置状态（除天气外） | 豁免：1 m² RCS 探测 ≤ 8 nmi 且 ≤ 1 Hz |
| (ii) | SAR 分辨率 < 0.3 m 或 CCD 配准 < 0.3 m | |
| (iii) | ISAR | |
| (iv) | TLE50 ≤ 10 m @ range > 1 km | |
| (v) | 海洋监视 平均功率孔径积 > 50 Wm² | |
| (vi) | 海洋监视 瞬时带宽 > 100 MHz 且转速 > 60 RPM | |
| **(vii)** | **空中监视雷达 1 m² RCS ≥ 85 nmi（≈ 157 km），按 RCS^(1/4) 缩放** | **最常引用的"距离线"** |
| (viii) | 反迫击炮雷达 1 m² 在 65,000 ft 仰角 > 20° | |
| (x) | 波束立体角 ≤ 16°² 跟踪 1 m² ≥ 25 nmi 重访 ≥ 1/3 Hz | |
| (xii) | 脉冲电子扫描雷达 | 豁免：峰值功率 ≤ 550 W |
| (xvii) | MTI/PD 单滤波器归一化杂波衰减 > 60 dB | |
| **(xviii)** | **ECCM 超过 MGC/AGC/CFAR/PRI jitter** | 关键技术分界 |
| (xix)-(xxvi) | EA / ES / NCTR / ATR / LPI（非 FMCW 线性）/ 弹头-诱饵区分 / 照射制导 | |
| (xxix) | 专门用于 ML 武器（500 kg 载荷 / 300 km 以上） | |

**豁免（明确不属军用）**：需飞机应答机配合的雷达、ICAO 标准 PAR、FAA TSO C87 无线电高度表。

### 两用（EAR ECCN 6A008）— 任一条件满足即触发

| 子条 | 触发条件 | 备注 |
|------|---------|------|
| a | 40–230 GHz + 平均功率 > 100 mW 或定位精度 ≤ 1 m/0.2° | 毫米波门槛 |
| b | 可调带宽 > ±6.25% 中心频率 | |
| c | 同时多载波 | |
| d | SAR / ISAR / SLAR | |
| e | 电子扫描阵列（AESA / ESA） | |
| f | 非合作目标测高 | |
| g | 机载多普勒动目标检测 | |
| h | 扩频/频率捷变 | |
| **i** | **地面雷达 最大仪表范围 > 185 km** | **地面两用"距离线"** |
| j | 空间 LIDAR / 相干 20 µrad / 海道 IHO 1a | |
| k | 脉冲压缩比 > 150 或压缩脉宽 < 200 ns | |
| l | 自动目标跟踪、地理分散融合（> 1500 m, < 6 s） | |

**6A008 豁免**：SSR、Civil Automotive Radar、ATC 显示、气象雷达、ICAO PAR。

**6A008(i) 进一步豁免**：渔场监视、航路 ATC（≤ 500 km、永久安装、单向传至 ATC 中心、不可远程控制扫描率）、气象气球。

### 导弹相关（EAR ECCN 6A108）— MT 触发

- a. 为"missiles"设计或修改的雷达/激光雷达（含地形等高线、成像传感器、Doppler 导航雷达）
- b. 载体射程 ≥ 300 km 的精密跟踪系统
  - b.2 测距 ≥ 30 km + 分辨率 < 10 m rms + 速度分辨率 < 3 m/s

**射程 300 km 是分水岭**——载体超过 300 km 触发 MT（Missile Technology），极严格。

---

## 瓦森纳（国际多边协调）

### 军用 ML5（功能性定义，非数值阈值）

> *"Fire control, surveillance and warning equipment, and related systems, test and alignment and countermeasure equipment, as follows, **specially designed for military use**, and specially designed components and accessories therefor"*

- a. 武器瞄准、轰炸计算机、炮瞄、武器控制
- b. 目标获取/指示/测距/监视/跟踪；检测/识别/鉴别；数据融合/传感器集成
- c. 对抗设备
- d. 测试/对准设备

**边界判据 = "specially designed for military use"**，**不是数值**。

### 两用 6.A.8 — 与 EAR 6A008 完全协调

结构、a–l 各子条、阈值、注脚均一致。**地面两用距离线 185 km 在瓦森纳同步生效**。

---

## Tracker II 出口管制判别流程

```
Step 1 — 用途问询
  ├─ 反无人军用 → 触发 USML XI(a)(3)（机载/地基都算）
  ├─ 边海防/要地防护 → Step 2
  └─ 民用/通航监视 → Step 2

Step 2 — 性能参数检查
  ├─ 命中 ECCN 6A008 任一条 → 触发两用管制
  │   重点核对：地面仪表范围、频段、AESA、SAR/ISAR、MTI/PD、ECCM、LPI
  └─ 全部不命中 → EAR99（民用自由出口）

Step 3 — 距离线（仅作辅助）
  ├─ 地面雷达 > 185 km：触发两用（除非 ATC ≤ 500 km/气象/渔场）
  ├─ 空中监视 1 m² ≥ 85 nmi：触发军用（USML）
  └─ 单独距离不构成触发条件

Step 4 — MT 触发检查
  └─ 载体（导弹/火箭/UAV）射程 ≥ 300 km → 触发 6A108 MT
```

**Tracker II 当前形态**（X 波段地基反无雷达）：
- 探测距离 ≤ 15 km（地面仪表范围 < 185 km）：**6A008(i) 不触发**
- 频段 9.2–9.8 GHz：**6A008(a) 40–230 GHz 不触发**
- 纯地基无 SAR/ISAR：**6A008(d) 不触发**
- 单面 AESA：**6A008(e) 触发**（AESA 本身即两用管制）
- 数字阵列/有源相控阵：**6A008(e) 触发**
- 具备 MTI/MTD 处理：**6A008(g) 不直接触发**（g 是机载多普勒）
- 脉冲压缩：**6A008(k) 需复核压缩比是否 > 150**
- 自动化跟踪：**6A008(l) 需复核是否提供"下次波束过境位置预测"**

**Tracker II 当前 AESA + 数字阵列体制 → 几乎必然触发 6A008(e)**——出口需要商务部 BIS 许可证。

如果 Tracker II 加 ECCM（NCTR/ATR/LPI）、SAR 处理、ECCM 阈值超 60 dB 杂波衰减等 → 进一步触发 USML XI(a)(3)(xvii)/(xviii)/(xxi)/(xxii)/(xxiv) → 国务院 DDTC 许可证。

---

## 官方原文来源（可重复抓取）

| 清单 | URL | 抓取命令 |
|------|-----|---------|
| USML (22 CFR 121) | eCFR title-22.xml | `curl -sL "https://www.ecfr.gov/api/versioner/v1/full/2026-06-04/title-22.xml?part=121" > /tmp/usml.xml` |
| CCL ECCN (15 CFR 774) | eCFR title-15.xml | `curl -sL "https://www.ecfr.gov/api/versioner/v1/full/2026-06-04/title-15.xml?part=774" > /tmp/ccl.xml` |
| Wassenaar ML 2025 | PDF corrigendum | `curl -sL "https://www.wassenaar.org/app/uploads/2026/01/Stand-alone-Munitions-List-2025-Corr.pdf" -o /tmp/wasm-ml.pdf` |
| Wassenaar Dual-Use 2025 | PDF corrigendum | `curl -sL "https://www.wassenaar.org/app/uploads/2026/01/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025-Corr.pdf" -o /tmp/wasm-dual.pdf` |

**浏览器对 eCFR 全部 anti-bot 拦截**（"Request Access" 页面）——**必须用 eCFR API + grep**，不能用 browser_navigate。详见 `web-tool-selection` skill 的"Browser blocked by anti-bot"小节。

---

## 国内对应（待核对最新版本）

| 国外 | 国内 |
|------|------|
| ITAR USML | 《军品出口管制清单》（商务部 + 国防科工局） |
| EAR CCL ECCN 6A008 | 《核两用品及相关技术出口管制条例》/ 临时管制办法 |
| 瓦森纳 ML5 | 军品出口管制清单 |
| 瓦森纳 Dual-Use 6.A.8 | 核两用品 |

**国内清单的逻辑是"功能/用途优先 + 数值辅助"**——和瓦森纳 6.A.8 类似，但具体阈值可能和 EAR/瓦森纳不完全一致。**企业出口需走专业律师事务所的 commodity classification**，不要直接套用美国阈值。
