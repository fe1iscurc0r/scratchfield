# Matterix + molgraph 补充评估

> 2026-09-04 · 88号 M2 · 评估（不写实现）
> 上游：AccelerationConsortium/Matterix（BSD-3，★55）、akensert/molgraph（MIT，★65）

## 一、Matterix：实验数字孪生

- 能力边界：机器人辅助化学实验室的自动化**数字孪生**，仿真实验流程（与 pylabrobot 执行层互补）。
- 与 pylabrobot 组合：pylabrobot（虚拟后端先跑通）→ Matterix（数字孪生仿真）构成「虚拟先行 → 真机执行」路径。
- 结论：**仅参考**（数字孪生方向，作为 M1 的组合蓝图登记，不立即接入）。

## 二、molgraph：分子 GNN（TF 生态）

- 能预测：分子性质（QSAR/分类/回归），TensorFlow 生态分子图神经网络。
- 与 chemprop/m3gnet 关系：**互补**——chemprop（分子，PyG/TF 灵活）、m3gnet（晶体）、molgraph（分子，纯 TF）。补 TF 侧覆盖。
- 接入成本：TF 生态，与现有 PyG 栈并存需双框架；成本中。
- 结论：**仅参考 / 暂缓**（TF 侧补覆盖，非必需；现栈 PyG 为主）。

## 三、附注：ChemLint vs ChemMCP

- ChemLint（31★ MIT，ChemMCP 竞品）功能与已授粉 ChemMCP 重叠。
- 一句话结论：**不重复接入**（功能覆盖重叠，沿用 ChemMCP）。

## 四、结论汇总

| 项目 | 结论 |
|------|------|
| Matterix | 仅参考（数字孪生蓝图） |
| molgraph | 仅参考/暂缓（TF 侧补覆盖） |
| ChemLint | 不重复接入（与 ChemMCP 重叠） |

---
*评估：fe1iscurc0r · 2026-09-04 · 基于上游公开文档*
