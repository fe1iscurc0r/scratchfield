# agent-79 评估报告 + 执行清单（材料软件 8 + 卫星气象 6 = 14 项）

> 智能体 79 · 勘察/评估 · 14 项（W78-01~14）

## 材料软件侧（W78-01~08）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W78-01 | mattergen | 待核 | 生成式材料逆设计 | ✅ 借鉴：材料逆设计，对接陆墨材料发现 |
| W78-02 | PyBaMM | 待核 | 电池仿真引擎 | ✅ 借鉴：电池仿真，对接电池健康（PF019） |
| W78-03 | torch-sim | 待核 | 微分原子模拟 | ✅ 借鉴：可微原子模拟，对接材料 ML |
| W78-04 | deepmd-kit | 待核 | 深度势能训练 | ✅ 借鉴：深度势能训练，对接 MLFF 线 |
| W78-05 | pycalphad | 待核 | 热力学相图 | ✅ 借鉴：相图计算，对接材料热力学 |
| W78-06 | QMOF + gRASPA | 待核 | MOF 数据库 + 吸附模拟 | ✅ 借鉴：MOF 数据 + 吸附，对接材料线 |
| W78-07 | ChatMOF | 待核 | LLM MOF 逆设计 agent | ✅ 借鉴：LLM 材料 agent，对照陆墨 Agent 化 |
| W78-08 | mlip-arena + RadonPy | 待核 | MLIP 评测 + 聚合物性质 | ✅ 借鉴：MLIP 评测基准 + 聚合物性质预测 |

## 卫星气象侧（W78-09~14）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W78-09 | satpy | 待核 | 气象卫星数据处理内核 | ✅ 借鉴：卫星数据内核，对接卫星垂直 |
| W78-10 | keeptrack.space | 待核 | 3D 卫星态势可视化 | ✅ 借鉴：3D 态势可视化，对照 worldmonitor 面板 |
| W78-11 | autowx2 + r2cloud | 待核 | 卫星调度流水线 | ✅ 借鉴：卫星过境调度，对接 ground-station |
| W78-12 | vitality-goes/himawari.js/xrit-rx | 待核 | 静轨影像三件 | ✅ 借鉴：静轨气象影像解码 |
| W78-13 | sahi + space_packet_parser | 待核 | 卫星影像推理 + CCSDS 遥测 | ✅ 借鉴：CCSDS 遥测解析，对接射频遥测 |
| W78-14 | SatIntel/Zenith/meteor_demod | 待核 | 卫星 OSINT + Web 追踪 + Meteor 解码 | ✅ 借鉴：卫星 OSINT + Meteor 解码，对照 sentinel_intel |

## 执行清单

- **完成**：14/14 逐项评估。
- **许可**：多数待核（未逐一实拉 license）。
- **高价值**：mattergen（材料逆设计）、satpy（卫星数据内核）、keeptrack.space（态势可视化）三点最可落地。
- **对接**：材料侧（W78-01~08）全部对接陆墨材料线；卫星侧（W78-09~14）对接卫星垂直 + worldmonitor 面板。
