# 工单 223 · 授粉四线并进——扫货 Top3 勘察 + FLoRa 龙雀调度 + EngramEdit 记忆更新 + 材料机理建模

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-09
> 料源：GitHub 扫货日报 2026-10-09（已归档 docs/pollination/batches/，guard FAIL=0）+ 论文增量授粉 2026-10-09 轮（791 篇新增，weekly_pollination.md:812 起）。

## 料源摘要（沈遥初勘实证）

**扫货侧**（10-09 日报 Top3，许可全绿，均未勘察过）：
- **xerj-org/xerj**（3395★ Apache-2.0）：AI 搜索新范式，自动索引任意数据。与现有 LightRAG/知识库检索直接同赛道，日报建议下一步勘察其索引 schema。
- **chainstart/openlabs**（0★ Apache-2.0）：材料科学可恢复自主研究工厂——正中生物质科研方向。风险：太早期。勘察定性，不预设拉库。
- **phoiex/AAAAGENT**（137★ 自定义 NC 许可）：Live2D 伴侣语音+情感记忆+微信，与 NEKO 定位高度重合。⚠️ NC 许可铁律：**只读参考设计，禁止任何代码并入主仓**，情感记忆架构思路单独成文。

**论文侧**（10-09 增量轮两个高价值授粉点）：
- **FLoRa（2610.09226）**：无人机辅助采集休眠 LoRa 节点，SA 路径 + CMA-ES 悬停定位 + POMDP 探测三层架构，VIP 信息价值指标。对龙雀 NR11+Ra-01 线是直接可用的调度模型。
- **EngramEdit（2610.10533）**：条件记忆解耦知识更新——多表达联合目标 + 共享嵌入按复用频率加权惩罚，编辑近满分且无关知识不伤。对 Hermes 记忆管理是"外科手术式更新"范式。

## 任务一（P0）：xerj 索引 schema 勘察报告

1. 浅 clone xerj-org/xerj（Apache-2.0，可拉），只读分析其自动索引 pipeline：数据摄入→索引构建→查询计划三段。
2. 产出 `docs/pollination/xerj-index-schema-2026-10.md`：
   - 索引数据结构（字段/schema/存储格式）与增量更新机制
   - 与现有 LightRAG 接入和 FTS5 轻量路线的对照表（各自强项/盲区）
   - 授粉判定：融合 / 参考级 / 不收，三选一，给理由
3. 结论若为"融合"：另出实施 SPEC（不本单实施）。

## 任务二（P0）：FLoRa → 龙雀 LoRa 调度设计稿

1. 精读 2610.09226（digest 全文在 research/papers/digests/full/，PDF: arxiv.org/pdf/2610.09226v1）。
2. 产出 `docs/hardware/longque/flora-scheduling-2026-10.md` 设计稿：
   - 论文三层架构（SA 路径 / CMA-ES 悬停 / POMDP 探测）逐层拆解 + VIP 指标定义
   - 降维映射：无人机→移动网关（ESP32-S3 + SX1278 背包节点），休眠节点→龙雀 Ra-01 节点，"飞行采集"→"巡检路径采集"
   - 可实现版本：无 UAV 条件下的退化解（固定中继轮询 + 占空比调度），给出节点级 POMDP 的状态/动作/奖励表
   - 与 rf_brain（skill）决策层的对接点标注
3. **不要求实跑**，设计稿级；但 VIP 指标的公式要抄准（论文原文核对）。

## 任务三（P1）：EngramEdit → Hermes 记忆更新模式报告

1. 精读 2610.10533，重点拆"多表达联合目标 + 共享嵌入复用频率加权惩罚"机制。
2. 产出 `docs/pollination/engramedit-memory-update-2026-10.md`：
   - 机制拆解 + 与 Hermes 现有记忆（memory 工具 + FTS5 session_search）的映射：哪一层可借"按条件触发更新而非全量重写"
   - 记忆污染防御：现有"若 full 先清后加"策略与论文"保护高频复用条目"的对照
   - 落地判定：值得做的最小改动是什么（如 memory 写入前的复用度检查），不实施
3. cs.CL 论文，注意别把训练层机制（嵌入编辑）误搬到推理层应用（条目管理）——分两节写清。

## 任务四（P1）：openlabs + AAAAGENT 双勘察（轻量）

1. **openlabs**（Apache-2.0）：浅 clone，定性其"可恢复自主研究工厂"的 workflow schema——编排单元、断点恢复、实验记录结构。材料线对口，出半页结论：值得跟踪 / 不值得，理由。
2. **AAAAGENT**（⚠️ NC 许可）：**不 clone 进主仓**。仅通过 GitHub 网页/API 读目录结构与 README，提取"情感记忆"模块的架构描述（存储/触发/衰减机制若公开），写成只读参考笔记 `docs/pollination/aaaagent-emotion-memory-nc-readonly-2026-10.md`，页眉标注 NC 许可来源与"禁止代码融合"声明。

## 验收

- [ ] 任务一：xerj schema 报告落地，含三段 pipeline 图/表 + 与 LightRAG/FTS5 对照表 + 三选一判定
- [ ] 任务二：FLoRa 设计稿落地，VIP 公式与论文原文核对一致，含节点级 POMDP 表
- [ ] 任务三：EngramEdit 报告落地，训练层/推理层分节，含最小落地判定
- [ ] 任务四：openlabs 半页定性 + AAAAGENT NC 只读笔记（页眉含许可声明）
- [ ] 全部文档进 docs/ 相应目录，CI 绿
