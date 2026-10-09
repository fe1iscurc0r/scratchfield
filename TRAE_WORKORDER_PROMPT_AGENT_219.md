# 工单 219 · EDA-AI 全流程 Skill 补全——"AI 怎么用嘉立创"从两件扩到八件

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：仓内 EDA skill 只有两件（schematic-autodraw 画图 / clearance-fix 修间距），覆盖"画"和"修"。但用户硬件主兴趣是嘉立创 EDA AI 全流程（PCB AI 布局布线），skill 版图缺"选、仿、查、产、购、归"六环。本单按 LoRaCanary v1.1 板的真实流程补全 skill 矩阵。

## 现状与缺口（按一块板子的真实生命周期）

| 环节 | skill 现状 | 缺口 |
|---|---|---|
| 选型（挑芯片/方案） | ❌ 无 | hardware-sourcing 在 Hermes 侧，仓内无 EDA 版 |
| 画原理图 | ✅ schematic-autodraw | — |
| PCB 布局布线 | 🟡 部分（clearance-fix 只管事后修） | 缺正向"布局→布线→检查"主流程 |
| 仿真验证 | ❌ 无 | ngspice 仿真零 skill |
| 查件（datasheet/参数） | ❌ 无 | datasheet-helper 类插件无 skill 对应 |
| 产出（BOM/Gerber/报告） | ❌ 无 | jlcpcb skill 在 Hermes 侧，仓内缺 |
| 采购下单 | 🟡 hardware-shopping-list 在 Hermes | 仓内无对接 |
| 归档复刻（知识入库） | 🟡 parasite-export 推数据 | 缺"入库后怎么查"的 skill |

## 任务一（P0）：补三件核心 skill（布局布线 / 仿真 / BOM-Gerber 产出）

均落 `~/scratchpad/skills/`，格式对齐既有两件（frontmatter + When to Use + Workflow + pitfalls），**每件必须含实测验证步骤**：

1. **easyeda-pcb-layout-route**（PCB 布局布线主流程 skill）：
   - 触发：autodraw 完原理图后进入 PCB；从网表导入→器件摆放策略（RF/电源/数字分区）→ `pcb autoroute`（Freerouting）→ `pcb check` 闭环
   - 与 clearance-fix 的边界写明（>20 错误回本 skill 重布局，不硬修）
   - 引用工单 218 的 M1 结论（pcb-router CLI 路径）
2. **easyeda-ngspice-sim**（仿真验证 skill）：
   - 触发：布局前验证关键电路（电源/RF 链路）；调用 eext-simulation-with-ngspice 或独立 simulation-engine
   - 含：常用分析类型（DC/AC/瞬态）速查、结果判读、失败常见原因
3. **easyeda-fab-output**（生产产出 skill）：
   - 触发：DRC 清零后；BOM 导出（对齐 LCSC 编号）→ CPL 坐标 → Gerber → 嘉立创下单参数（叠层/表面处理/阻焊）核对单
   - 与 Hermes 侧 jlcpcb skill 互相引用不重复（本件管 EDA 内产出，那件管下单流程）

## 任务二（P1）：补两件协同 skill（选型 / 知识回查）

1. **easyeda-component-sourcing**（选型 skill）：
   - 触发：新设计开始选主控/外设；从需求参数→LCSC 筛选→多源比价（淘宝/立创）→封装可得性核对→器件库 C 编号入库
   - 与 Hermes 侧 hardware-sourcing/hardware-shopping-list 互引（本件管 EDA 库侧落地）
2. **eda-knowledge-retrieval**（知识回查 skill）：
   - 触发：设计中的问题查历史项目/寄生链数据；查工单 217 落的 ingest 落盘数据 + lightrag 知识库
   - 含：查什么（历史文档源码/寄生估算/BOM 比价）+ 查询示例 + 结果如何回注 EDA

## 任务三（P1）：skill 矩阵索引页

1. 产出 `docs/eda-skill-matrix.md`：八环 × skill 对照表（含 Hermes 侧/仓内两处归属）、每环的典型触发语（用户说什么该进哪个 skill）、环间交接（autodraw 完→谁接棒）
2. 与 skills/easyeda-* 两件旧 skill 的 description 交叉校验：确保触发词不冲突不重叠

## 验收
- [ ] 任务一：三件 skill 落盘，frontmatter 合规，各含 Workflow + pitfalls + 实测验证步骤；与既有两件边界清晰
- [ ] 任务二：两件协同 skill 落盘，与 Hermes 侧 skill 互引关系明确
- [ ] 任务三：matrix 索引页覆盖八环全生命周期 + 触发语表 + 交接链
- [ ] 全程 CI 绿
