---
name: easyeda-pcb-layout-route
description: EasyEDA Pro PCB 布局布线主流程 skill：从网表导入、器件分区摆放（RF/电源/数字）、Freerouting 自动布线到 DRC 检查的完整闭环。适用于原理图完成后进入 PCB 阶段的正向设计流程。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: scratchpad
  workorder: "219"
---

# easyeda-pcb-layout-route

## Overview

PCB 阶段的正向主流程：**网表导入 → 器件摆放（分区策略）→ 自动布线 → DRC 闭环**。
布线引擎走 `easyeda-pcb-router`（Freerouting CLI，工单218 判定的 M1 路线——独立 CLI，无需 EDA 客户端在线）；布局与 DRC 走 easyeda-agent typed action。

## When to Use This Skill

- schematic-autodraw 完成原理图后，用户说"进入 PCB / 布局 / 布线"。
- 新板（如 LoRaCanary v1.1）从网表开始做 PCB。
- 布局不合理导致 DRC 大量错误，需要**重布局**（见与 clearance-fix 的边界）。

不要用于：
- 只有零星几个间距/丝印错误 → 用 `easyeda-clearance-fix`（事后修）。
- 还没有原理图/网表（先走 schematic-autodraw）。

## 与 clearance-fix 的边界（必须遵守）

> **>20 个 DRC 错误 → 回本 skill 重布局，不硬修。** clearance-fix 是"少量错误的术后处理"，
> 不是"烂布局的抢救室"。反过来 <20 个孤立错误且拓扑没问题 → 别推倒重来，用 clearance-fix。

## Workflow

### 0. 前置检查

- `easyeda health` → `status: found`；PCB 文档已打开（或从工程树 open）。
- 网表已由原理图同步（`eda.pcb_Document` 可读到器件）。

### 1. 器件摆放（分区策略）

按信号域分区，顺序：

1. **RF 区**（LoRa/SX1278 天线链路）：靠近板边 + 天线馈点，**远离数字区**；
   匹配网络器件按信号流向一字排开（最短路径）。
2. **电源区**：LDO/DCDC 输入输出电容紧贴对应引脚（<500mil）；发热件远离晶振与温敏件。
3. **数字区**（MCU/Flash）：去耦电容每 VDD 一个就近放；晶振紧贴 MCU。
4. **接口区**（USB/排针/开关）：板边对齐，按机械外壳约束摆。
- typed action：`pcb move`（批量）/ `pcb place`；坐标单位 **mil**（⚠️ EDA 内部 1mil，
  与原理图 0.01inch 不同，工单215 调研已记此坑）。

### 2. 自动布线（Freerouting CLI 路线）

```bash
# 导出 DSN（typed action 或菜单 网表→导出 DSN）
easyeda-cli pcb export-dsn --out board.dsn
# Freerouting CLI（easyeda-pcb-router 包的引擎，独立进程）
java -jar freerouting.jar -de board.dsn -do board_routed.dsn -mt 4
# 回导
easyeda-cli pcb import-dsn board_routed.dsn
```

- 层约定：双层板 → 顶层横向、底层纵向（L 型为主，工单215 三选一调研的同款约定）。
- RF 链路**手动预布**后再自动布其余（自动布线器不懂阻抗）。

### 3. DRC 闭环

- `pcb check`（typed action）→ 错误分类计数：
  - 间距/短路 ≤20 且孤立 → 转 `easyeda-clearance-fix`；
  - 未布通（unrouted）多 → 回步骤 2 调参数（网格/过孔成本）；
  - 大面积错误 → 回步骤 1 重摆。

## Pitfalls

1. **单位陷阱**：PCB mil vs 原理图 0.01inch，10 倍偏差（上游文档明示）。
2. RF 走线交给自动布线 = 灾难；先手布 RF 再自动布数字。
3. Freerouting JVM 未装时：健康检查提示安装（ROS 线"接口先行"纪律），不要静默失败。
4. DSN 回导会重建网络 → 先备份文档源码（`parasite-export` 推一次云服即存档）。

## 实测验证步骤

1. 用 LoRaCanary v1.1 的既有网表（或合成小网表：MCU+LoRa+电源 3 区 15 器件）走完 0→3。
2. 断言：DRC 错误数 = 0 或全部可归类到 clearance-fix；RF 链路走线长度手工核对。
3. `parasite-export` 推送布线后文档 → 云服 `/api/eda/ingest` 返回 `stored: true`。
