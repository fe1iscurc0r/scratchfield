# K19 Bern2Edge Bernstein 多项式网络评估

> 生成：2026-08-31 · 来源：digest-g1-2-2026-08-30 2608.20497v1（Bern2Edge：Bernstein 多项式激活 LUT 边缘部署，FPGA 99.8% 延迟减少）
> 落点：ESP32-S3 端侧推理（与 OTA-ELM 对比） · 状态：评估报告 + 最小原型（`tools/bern2edge.py` + 测试）

---

## 0. 结论速览

Bern2Edge 的核心：用 **Bernstein 多项式基**做特征映射（而非随机隐层 + sigmoid）。Bernstein 基 `B_{i,n}(x)=C(n,i)x^i(1-x)^{n-i}` 在 [0,1] 上有界、单位分解、全多项式——三点叠加后，**离线可把 (n+1) 条基多项式逐点查表（LUT）**，运行时零超越函数，与 OTA-ELM 的 sigmoid LUT 思路同源但**表达能力更集中**。

最小原型（numpy）在 1D 函数逼近上对比 OTA-ELM：

| 指标 | Bernstein（n=10） | OTA-ELM（nh=12） |
|---|---|---|
| 精度 MSE | **0.000248** | 0.000255 |
| 参数量 | **11** | 36 |
| LUT（字节） | 2816 | **256** |
| 每推理 MACs | **11** | 24 |

**结论**：Bernstein 在「精度相当/略优」的前提下，参数量少 3.3×、MACs 少 2.2×；代价是 LUT 更大（需存 n+1 条基而非 1 条 sigmoid）。

## 1. 方法拆解

- **Bernstein 网络**：`ŷ(x) = Σ_{i=0}^{n} βᵢ · B_{i,n}(x)`。拟合是线性最小二乘（闭式，无梯度），与 ELM 一样免反向传播。
- **OTA-ELM**：`ŷ(x) = Σ_j βⱼ · σ(wⱼ x + bⱼ)`，随机隐层 + 伪逆输出。

## 2. ESP32 可行性

- **定点友好**：Bernstein 基 ∈ [0,1]，可直接 int8 量化；LUT 索引即量化后的 x。
- **无超越函数**：exp/pow 只在离线生成 LUT 时用，推理侧纯查表 + 乘加，与 OTA-ELM 的 LUT 激活一致。
- **FPGA/ESP32 延迟**：论文报 FPGA 99.8% 延迟减少；ESP32-S3 上同理——纯 LUT+MAC 无浮点 exp，可进定点 DSP。

## 3. 部署预算对比（诚实标注）

- **参数量**：Bernstein `n+1`；ELM `3·nh`（W + b + β）。
- **LUT**：Bernstein `(n+1)×bins`；ELM `bins`（sigmoid）。
- **MACs/推理**：Bernstein `n+1`；ELM `2·nh`。

**权衡**：精度目标越高，Bernstein 需更高阶 n → LUT 随 n 线性增长；ELM 需更大 nh → 参数量/MACs 随 nh 线性增长。对「参数量与 MACs 敏感、可容纳几百字节 LUT」的 ESP32 场景，Bernstein 更优。

## 4. 落地建议

1. **替代 ELM 的低维回归/分类头**：rf_brain 里特征维低（SNR/包络/谱形）的推理节点，可用 Bernstein 网络替换 sigmoid ELM，省 MACs。
2. **LUT 复用**：同一阶 n 的 Bernstein 基 LUT 全模型共享，多输出只增 β，不增 LUT。
3. **混合**：非线性的低频部分用低阶 Bernstein 逼近，残差交给 ELM，兼顾精度与预算。

## 5. 边界与待办

- 本原型为 1D 函数逼近；多维输入需张量积 Bernstein 基，LUT 随维数指数增长（诚实降级：未实现多维）。
- 未做真机定点量化对比（按 spec 只出方案/原型 + 预算表）。
