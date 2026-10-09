---
name: easyeda-ngspice-sim
description: EasyEDA Pro ngspice 仿真验证 skill：布局前验证关键电路（电源/RF 链路）。覆盖 DC/AC/瞬态分析的调用方法、结果判读与失败排查。适用于 PCB 定稿前的电路正确性验证。
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: scratchpad
  workorder: "219"
---

# easyeda-ngspice-sim

## Overview

**布局前**验证关键电路（电源完整性 / RF 链路增益），避免"布完线才发现电路错了"。
两条执行路径（工单218 的 M2/M1 判定）：
- **A 编辑器内**：`eext-simulation-with-ngspice`（人用 GUI；agent 经 daemon typed action 触发，SPEC-A 桥落地后）；
- **B 独立引擎**：`easyeda-simulation-engine`（NGspice 本地、无 GUI 依赖——agent 场景首选，当前即可用）。

## When to Use This Skill

- 原理图完成、**进入 PCB 布局之前**（关键电路验证黄金时点）。
- 用户说"仿真一下 / 验证电源 / 看 RF 增益 / 跑个 AC"。
- 换料后想确认关键参数没漂（LDO 压降/滤波器截止频率）。

不要用于：
- DRC/物理规则（那是 `pcb check`）；
- 整板级 SI/PI（ngspice 不做高速信号完整性——需要专业工具，当前不做）。

## Workflow

### 0. 前置

- 原理图已保存；关键子电路可隔离（电源树 / RF 前端）。
- 路径 B 需 ngspice 可执行（`ngspice -v`；缺则提示安装，不静默失败）。

### 1. 导出网表并附加仿真指令

```
easyeda-cli sch export-spice --out sim.cir
# 手工补 .op/.tran 指令（EDA 导出常缺分析语句——高频失败原因，见 pitfalls #1）
```

### 2. 分析类型速查（何时用哪个）

| 分析 | ngspice 指令 | 用来看 | 判读 |
|---|---|---|---|
| **DC 工作点** | `.op` | 静态偏置对不对 | 节点电压 vs 手算；晶体管区态 |
| **DC 扫描** | `.dc VIN 0 5 0.1` | 稳压器压降曲线 / 阈值 | 转折点位置 |
| **AC 小信号** | `.ac dec 10 1k 100Meg` | 滤波器截止/RF 增益 | -3dB 点；通带平坦度 |
| **瞬态** | `.tran 1u 10m` | 上电软启/振荡/纹波 | 稳态时间；纹波峰峰值 |

### 3. 运行与结果回读（路径 B）

```bash
ngspice -b sim.cir -r sim.raw > sim.log
# 结果解析：raw 文本 raw → 提取关键节点曲线摘要（工具链待 SPEC-A 桥统一后自动化）
```

### 4. 结果回传云服（SPEC-A 落地后）

`POST /api/eda/simresult`（复用 ingest 的 token/落盘/事件模式）→ rf_brain 订阅做寄生链验证。

## Pitfalls（失败常见原因）

1. **导出网表缺 `.tran/.ac` 分析指令**（EDA 只导器件+连接）——必须手工补，90% 的"跑不出结果"是这个。
2. **器件模型缺失**：LCSC 元件的 spice 模型覆盖率低；缺模型时用等效模型（LDO→压控源+阻抗）并在报告注明。
3. **地节点命名**：EDA 导出的 GND 常叫 `GND_0/0`——ngspice 不认，统一改成 `0`。
4. 收敛失败（`.options gmin=1e-10 reltol=1e-4` 放宽）或初值缺失（加 `.ic`）。
5. RF 链路的 S 参数器件模型需要专门 s2p 文件（厂商官网下，LCSC 通常不带）。

## 实测验证步骤

1. 对 LoRaCanary 电源树（电池→LDO→MCU）跑 `.op` + `.tran`（上电软启）：
   断言输出电压 = 标称 ±5%、软启无过冲 >10%。
2. 对 SX1278 前端匹配网络跑 `.ac`：断言 433MHz 处插损在仿真预期带内。
3. 结果摘要（节点电压表/增益数）回报对话，原文档不动。
