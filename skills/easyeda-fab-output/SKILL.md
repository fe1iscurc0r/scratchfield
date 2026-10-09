---
name: easyeda-fab-output
description: EasyEDA Pro 生产产出 skill：DRC 清零后的 BOM 导出（对齐 LCSC 编号）、CPL 坐标、Gerber 打包与嘉立创下单参数核对单。适用于"要打样了/出生产文件"的场景。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: scratchpad
  workorder: "219"
---

# easyeda-fab-output

## Overview

**DRC 清零后**的生产文件闭环：BOM（带 LCSC C 编号）→ CPL（贴片坐标）→ Gerber → 下单参数核对单。
本件管 **EDA 内的产出**；下单流程走 Hermes 侧 `jlcpcb` skill（互引不重复）。

## When to Use This Skill

- 用户说"出 BOM / 出 Gerber / 准备打样 / 交给嘉立创"。
- DRC 已清零（没清零先回 `easyeda-pcb-layout-route` 步骤 3）。
- 换版归档时产出全套生产文件存底。

不要用于：
- 还在改板（产出无意义）；
- 只想看元件统计（EDA 内置报告即可，不出全套）。

## Workflow

### 0. 前置门槛（不满足则终止并回报）

- [ ] `pcb check` 错误数 = 0（或仅剩豁免项且已备注）。
- [ ] 板框闭合、原点在板左下角。
- [ ] 所有器件 LCSC 编号已绑定（`pcb bom` 导出无空 C 编号——缺号回 sourcing skill 补）。

### 1. BOM 导出（对齐 LCSC）

```
easyeda-cli pcb bom --out bom.csv --align lcsc
```
核对：位号聚合正确（同值同封装合并）、C 编号与立创商城**在售状态**一致（缺货标注替代料）。

### 2. CPL 坐标

```
easyeda-cli pcb cpl --out cpl.csv
```
核对：原点/方向约定与嘉立创 SMT 要求一致（左下原点、度数逆时针）；只含 SMD 件。

### 3. Gerber 打包

```
easyeda-cli pcb gerber --out fab/ --format jlcpcb
```
核对：层文件齐全（铜/阻焊/丝印/钻孔/边框）、命名符合嘉立创模板、压缩为单个 zip。

### 4. 下单参数核对单（人工确认后随文件交 Hermes 侧 jlcpcb skill）

| 参数 | 本板取值示例（LoRaCanary v1.1） | 核对点 |
|---|---|---|
| 板层 | 2 层 | 与布线假设一致 |
| 板厚 | 1.6mm | 特殊阻抗要求才改 |
| 尺寸 | ≤100×100mm | 打样免费档 |
| 表面处理 | HASL(铅) / ENHG（无铅） | 焊接工艺匹配 |
| 阻焊 | 绿油默认 | 白油只给 RF 板 |
| 工艺 | SMT 贴片（有 BOM+CPL 才勾） | 与 1/2 步联动 |

## Pitfalls

1. **C 编号失效/缺货**是打样翻车首因——BOM 导出后必须过一遍在售检查。
2. CPL 原点方向搞反 → 贴片镜像 → 整批报废；首件确认时用嘉立创预览图的器件丝印方向核对。
3. Gerber 少边框层 → 厂家自动猜测板框 → 尺寸错；zip 里必须看到 `.GKO/Outline`。
4. 盲埋孔/异形板不在打样免费档——先算加价再下单（Hermes 侧 jlcpcb skill 的职责）。

## 与 Hermes 侧 jlcpcb skill 的边界

本件：**EDA 内**产出三件套 + 参数核对单 → 移交。
jlcpcb skill：**下单流程**（上传/算价/加价判断/订单跟踪）。

## 实测验证步骤

1. 用 LoRaCanary v1.1（或最近一块已打样板）重出全套，与**上次实际下单文件**逐项 diff：
   BOM 行数/CPL 首器件坐标/Gerber 层数必须一致。
2. 参数核对单填好后人工签认一项，未签认不上传。
