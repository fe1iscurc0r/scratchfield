# M15 剪枝方法决策笔记

> 附于 `m15_physics_pruning.py`，记录"为什么最终用分段切换（贪心→OBS@80%）"。
> 实验脚本留存于 worktree `scratchpad-pruning-research/`（分支 `research/pruning-method`）。

## 1. 问题

物理信息剪枝（目标 = 剪权重同时保 PDE 残差 `u'' + π²u` 低）在 32 权重小 MLP 上，
one-shot 残差显著性在 80% 剪枝率后退化（残差崩到 83@90%、442@80%）。根因：one-shot
一次性按"单权重残差增量"排序，忽略移除多个权重时的交互效应，高稀疏度下旧排序失效。

## 2. 最终方案：分段切换（staged）

- **阶段 1（0→80%）**：贪心 leave-one-out 残差显著性——逐个置零权重、实测残差增量，
  移除增量最小的权重。一阶实测在中低稀疏度最准。
- **阶段 2（80%→95%）**：OBS（Optimal Brain Surgeon）——二阶显著性 `s_q = w_q²/(2[H⁻¹]_qq)`
  （Gauss-Newton Hessian `H=JᵀJ`）+ 移除后对剩余权重补偿 `δw = -w_q·H⁻¹[:,q]/H⁻¹_qq`，
  显式建模高稀疏度下的权重交互。

## 3. 关键证据（全程 PDE 残差 MSE，越低越好）

| 剪枝率 | one-shot | 纯贪心 | 纯 OBS | **分段(80%切换)** | 随机 |
|---|---|---|---|---|---|
| 20% | 22.42 | 0.12 | 3.71 | **0.12** | 110 |
| 60% | 88.39 | 0.96 | 2.08 | **0.96** | 152 |
| 80% | 442 | 0.70 | 0.17 | **0.70** | 121 |
| 90% | 564 | 83 | 19 | **1.32** | 115 |
| 95% | — | 130 | 1.99 | **1.12** | 51 |

**拐点扫描（switch_frac，全程 mean 残差）**：0.70→4.48，0.75→3.69，**0.80→2.34**，
0.85→13.56，0.90→14.17 —— 80% 是尖峰最优，不是平平台。

## 4. 试过的替代方案及失败原因

| 方案 | 结果 | 失败原因 |
|---|---|---|
| one-shot 残差显著性 | 80% 后崩 | 忽略权重交互，排序过时 |
| 纯 OBS | 中低稀疏度更差（20% 3.71 vs 0.12） | 二阶近似不如贪心一阶实测准 |
| 单步混合（贪心选+OBS补偿） | 残差 10¹¹~10¹⁶ | 补偿必须配二阶显著性，硬拼 H⁻¹ 病态放大 |
| 贪心+重训 | 中低更差，仅极端有帮助 | 重训数据拟合引入毛刺、放大 u''（且目标不匹配） |
| leverage 采样+重解（谱稀疏化） | 全程 5.41 > 2.34 | one-shot 近视，丢了迭代重排序 |
| log-sum 连续松弛 | 稀疏度-残差非单调 | 非凸，梯度下降卡局部极小 |
| CoSaMP 回补 | 振荡不收敛 | "删一个+回补一个"不保证支撑缩小 |
| best-subset 局部 swap | 太慢 | O(active×inactive×候选) 三重循环，边际收益不值 |

## 5. 结论一句话

**贪心一阶实测（中低稀疏）+ OBS 二阶补偿（极端稀疏）+ 80% 分段切换**，是小尺度物理
约束网络的最优剪枝配方；跨领域启发（谱稀疏化/压缩感知/连续松弛）概念有价值，但在此
规模下被各自固有代价（one-shot 近视、非凸、振荡、复杂度）抵消。

## 6. 实验脚本（worktree `scratchpad-pruning-research/`）

`pruning_experiment.py`（one-shot vs 贪心）、`pruning_obs_experiment.py`（贪心 vs OBS）、
`pruning_hybrid_experiment.py`（单步混合反例）、`pruning_retrain_experiment.py`、
`pruning_staged_experiment.py`（分段切换胜出）、`pruning_switch_sweep.py`（拐点扫描）、
`pruning_shootout.py`（leverage/log-sum）、`pruning_cosamp_bestsubset.py`、
`pruning_cosamp_fixed.py`。
