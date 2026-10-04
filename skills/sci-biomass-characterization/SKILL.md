---
name: sci-biomass-characterization
description: 生物质与材料热分析数据解读（TGA 热重 / DSC 差热 / XRD 衍射 / Raman 拉曼 四件套）。帮用户解析仪器导出的 CSV/TXT 数据、做预处理（基线扣除/归一化/平滑/拉曼去尖峰去噪）、生成科研风曲线图并入库 ELN。当用户说"帮我分析这条热重曲线""DSC 数据怎么归一化""处理一下拉曼谱""把这批 XRD 数据出图"时使用。
version: 1.0.0
author: 陆墨
tags:
  - biomass
  - materials
  - characterization
  - data-tools
enabled: true
---

# 生物质材料热分析四件套

基于本仓 `apiserver/routes/data_tools.py`（TGA/DSC/XRD/Raman 四类型）与前端 DataView（数据工具台）落地。上游授粉：K-Dense-AI/scientific-agent-skills 材料表征类技能改造。

## 使用流程

1. **解析**：用户提供 CSV/TXT（分隔符自动探测）→ 调 `/api/data-tools/parse` 预览表头。
2. **预处理**：按数据类型选择参数——TGA 基线扣除、DSC 质量归一化、XRD 平滑窗口、Raman 去尖峰+去噪+基线+归一化（走 `tools/raman_utils`）。
3. **出图**：调 `/api/data-tools/plot` 生成科研风 PNG，标题标注数据来源。
4. **入库**：PNG → vault attachments → ELN 记录（复用既有 ELN 流程）。

## 常见用户诉求 → 动作

| 诉求 | 数据类型 | 预处理要点 |
|------|---------|-----------|
| 生物质热解失重曲线 | tga | 基线扣除（从 100% 起算） |
| 木质素玻璃化转变 | dsc | 质量归一化（mg 必填，缺省 min-max） |
| 纤维素结晶度 | xrd | 平滑窗口按峰宽试 5/7/9 |
| 拉曼官能团（G/D 带） | raman | 去尖峰→SavGol→ASLS 基线→归一化 |

## 验证

- 样例：`/api/data-tools/samples` 各类型样例直接跑通 parse→plot 全链路。
- 验收：出图坐标轴标签正确（°C/2θ/cm⁻¹）、预处理前后峰位不漂移（Raman 峰位保留 1240-1260 cm⁻¹ 级）。
