---
name: easyeda-component-sourcing
description: 嘉立创 EDA 器件选型 skill：从需求参数到 LCSC 筛选、多源比价、封装可得性核对、器件库 C 编号入库。适用于新设计开始时挑主控/外设的场景。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: scratchpad
  workorder: "219"
---

# easyeda-component-sourcing

## Overview

新设计的第一步：**需求参数 → LCSC 筛选 → 比价 → 封装核对 → C 编号入库**。
本件管 **EDA 库侧的落地**（选完的件能直接被 autodraw/layout 用）；
需求调研与购物清单归 Hermes 侧 `hardware-sourcing` / `hardware-shopping-list`（互引）。

## When to Use This Skill

- 用户说"选个主控 / 这个功能用什么芯片 / 帮我找替代料"。
- 原选型缺货/停产，需要 pin-to-pin 或近似替代。
- 新板（LoRaCanary v1.x 迭代）定 BOM 前的器件冻结。

不要用于：
- 已经定了 C 编号的 BOM 复核（走 fab-output 的在售检查）；
- 非嘉立创渠道采购（走 Hermes 侧 shopping-list）。

## Workflow

### 1. 需求参数表（先写下来再筛）

| 维度 | 示例（LoRaCanary 主控换代） |
|---|---|
| 硬需求 | ≥2×SPI、deep-sleep <20µA、可焊接（手焊友好 QFP/不用 BGA） |
| 软需求 | Rust/Arduino 工具链、库存 >1k |
| 预算 | 单片 ¥15 内 |

### 2. LCSC 筛选

```
easyeda-cli lib search "ESP32-S3" --stock min:1000 --pkg exclude:BGA
```
- 库存 <1000 的慎选（打样后量产断供）；
- **基础库（免费打样档）优先**——筛选结果带基础库标识的加权。

### 3. 多源比价（立创 vs 淘宝散件）

- 立创价（阶梯价取打样量 10pcs 档）；
- 淘宝散件价（仅 debug 阶段便宜，量产不认）；
- 结论记录在选型表：**EDA 库以立创 C 编号为准**（淘宝件无 C 编号，只能调试用）。

### 4. 封装可得性核对（最容易翻的一步）

- 器件库中该 C 编号**有原理图符号 + PCB 封装 + 3D**三件齐吗？
- 封装焊盘与数据手册推荐一致吗（pitch/盘宽——库里有旧版错封装的坑）；
- **symbol 缺失** → 记下来走 symbol-builder 思路补（或换件）。

### 5. C 编号入库

选型定稿 → 更新项目器件表（`SPEC-20-*` 系列文档的 BOM 节）→ C 编号进网表定义，
供 `easyeda-schematic-autodraw` 的 `lib search` 直接解析。

## Pitfalls

1. **只看首件价不看阶梯价**——打样 10 片和量产 1k 价差可达 3 倍。
2. **封装图与实物不一致**（库旧版）——第 4 步必须对照数据手册推荐焊盘。
3. 替代料的**软件兼容性**没人替你管：pin-to-pin 但寄存器不兼容 = 白换（需求表加一行"固件改动量"）。
4. 基础库/扩展库标记影响打样费用——扩展库件每颗加扩展费。

## 与 Hermes 侧的互引

- `hardware-sourcing`（Hermes）：需求调研、跨渠道（含非嘉立创）初选 → 给出候选清单。
- **本件**：候选清单 → LCSC 落地核对 → C 编号进 EDA 库。
- `hardware-shopping-list`（Hermes）：最终采购执行。

## 实测验证步骤

1. 对 LoRaCanary v1.1 现役 BOM 的 5 个关键件重走 2→5 步：断言每个 C 编号
   库存 > 阈值、封装三件齐、价格与上次采购记录偏差 <30%。
2. 任选一停产料（如旧款 LDO）做替代选型，产出完整选型表。
