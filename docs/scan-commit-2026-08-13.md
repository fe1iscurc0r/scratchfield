# 物理层摸底 · 拉取决策字据

> 日期：2026-08-13 | 决策：实验田维护者摸底，用户拍板
> 状态：摸底完成，进入批量拉取

---

## 一、决策结论（已拍板）

1. **加码方向 = 物理层 AI 决策大脑**：scratchpad 补控制/规划层的 AI 空白，底座用开源，脑子用 LLM+逻辑引擎。
2. **摸底范围 = 所有"AI 红利盲区"**：物理层 + 传统工程 + 行业软件，不分相关性。
3. **企业级闭源对照**：射频是巨头都没啃下的真空地带（主攻）；工业 AI/机器人巨头刚进场（旁路）；EDA 是红海（但开源 license 友好，采用其开源项目作参考）。

## 二、许可策略（沿用扫货铁律）

- **有许可证**（含 SSPL/GPL/AGPL/MIT/BSD/Apache）→ 全拉
- **无 LICENSE** → 暂缓（csdr 等）
- **GPLv2-only** → 需确认（LinuxCNC、QGIS 是否 v2+）

## 三、拉取清单（按方向）

### 物理层 physical/
| 项目 | license | 拉? |
|---|---|---|
| liquid-dsp | MIT | ✅ |
| sdrtrunk | GPL-3.0 | ✅ |
| gr-lora_sdr | GPL-3.0 | ✅ |
| BTLE | Apache-2.0 | ✅ |
| PythonRobotics | other | ✅ 确认后 |
| multi_agent_path_planning | MIT | ✅ |
| motion_planning | MIT | ✅ |
| mapf-IR | MIT | ✅ |
| osmnx | MIT | ✅ |
| Turfjs | MIT | ✅ |
| cartographer | Apache-2.0 | ✅ |
| ORB_SLAM3 | GPL-3.0 | ✅ |

### 传统工程 engineering/
| 项目 | license | 拉? |
|---|---|---|
| PyCNC | MIT | ✅ |
| svg2gcode | MIT | ✅ |
| SolidsPy | MIT | ✅ |
| pycalculix | Apache-2.0 | ✅ |
| gismo | MPL-2.0 | ✅ |
| PowerSimulationsDynamics.jl | BSD-3 | ✅ |
| JuliaGrid.jl | MIT | ✅ |
| openikcape | MIT | ✅ |
| differentiable-flowsheets | MIT | ✅ |

### EDA（用户采用，作参考）
| 项目 | license | 拉? |
|---|---|---|
| CircuitNet | BSD-3 | ✅ |
| HDLGen-ChatGPT | AGPL-3.0 | ✅ |
| EDA-Q | GPL-3.0 | ✅ |

### 卫星 satellite/
| 项目 | license | 拉? |
|---|---|---|
| wx-ground-station | MIT | ✅ |
| FAASGS | GPL-3.0 | ✅ |

## 四、下一步

拉取完成后 → 出「射频大脑」融合 SPEC（底座选型 + 分阶段 + 接口设计），执行侧照 SPEC 写代码。
