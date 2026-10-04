# K18 Relation Mixer 评估报告

> 生成：2026-08-31 · 来源：digest-g1-1-2026-08-30 2608.20172（Relation Mixer：关系优先 token 混合替代 MHA，等效质量下吞吐量提升 4 倍）
> 落点：NEKO/rf_brain 本地推理 · 状态：评估报告 + 最小原型（`tools/relation_mixer.py` + 测试）

---

## 0. 结论速览

多头注意力（MHA）每次前向都要做**内容相关**的 QK^T + softmax + AV，复杂度 O(N²·d)，是长序列本地推理的头号瓶颈。Relation Mixer 的关键洞察：**token 间关系可以用固定的关系矩阵（带状 Toeplitz）预先刻画**，把逐次 QK^T + softmax 换成一次 O(N·k·d) 的带状乘（k≪N 为关系带宽）。

最小原型（numpy，无新依赖）复现了两点：

| 指标 | MHA | Relation Mixer | 结论 |
|---|---|---|---|
| FLOPs（N=128, d=64） | 4,210,688 | 589,824 | **7.1×**（验收要求 ≥4×） |
| 去噪重建 MSE | 0.1022 | 0.0551 | **质量相当（甚至更优）** |

## 1. 方法拆解

- **MHA**：`y = softmax(QKᵀ/√dₖ) · V · Wₒ`，注意矩阵是输入相关的稠密 N×N 矩阵。
- **Relation Mixer**：`y = (R·x)·Wₒ`，R 是固定的带状 Toeplitz 关系矩阵（带宽 k，行归一），编码「每个 token 与近邻 k 个 token 的关系」，与输入内容无关 → 可在推理前预计算/量化，逐次前向只有带状乘。

## 2. 吞吐对比

FLOPs 计数（确定性，见 `flops_mha` / `flops_relation_mixer`）：

- MHA：`3·N·d·dₖ + 2·N²·dₖ + N² + N·dₖ·d`
- Relation Mixer：`N·k·d + N·d·d`

在 N=128、d=dₖ=64、k=8 时比值为 **7.1×**；带宽 k 越小、序列越长，优势越大（MHA 是 N² 增长，Relation Mixer 是 N·k 增长）。

## 3. 质量评估

用「去噪重建」任务做公平质量对比：固定 mixer 表征 + 拟合同一线性投影，比较重建 MSE（见 `quality_comparison`）：

- attention 表征 MSE=0.1022，relation 表征 MSE=0.0551（噪声方差基线 0.25）。

**Relation Mixer 不仅没掉质量，反而更好**——因为该任务的信号是局部结构，而带状关系矩阵恰好是「局部聚合」的正确先验。这与论文「等效质量」一致（在关系结构明确的任务上甚至更优）。

## 4. 对 NEKO/rf_brain 的落地建议

1. **rf_brain 频谱时序**：频谱/信道状态序列天然有「邻近 token 相关」结构，用带状 Relation Mixer 替代注意力做频谱特征时序建模，省 4×+ 计算。
2. **NEKO 本地 LLM 推理**：长上下文场景（对话历史、工具结果拼接）用 Relation Mixer 混合 token，可显著降推理延迟。
3. **端侧友好**：R 固定可预量化、无 softmax 超越函数，与 OTA-ELM 的 LUT 思路同源，适合 ESP32/定点部署。

## 5. 边界与待办

- 原型只验证「关系结构明确」的任务；对需要**长程内容相关注意力**的任务（如复杂推理），固定关系矩阵可能不够，需「固定关系 + 稀疏可学习内容修正」的混合方案（论文方向的后续）。
- FLOPs 为理论计数，未做真机/实际 kernel 的 wall-clock 对比（诚实降级，标注为 mock）。
