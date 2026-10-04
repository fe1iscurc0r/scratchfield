# K25 LLM 推理能耗特征→端侧预算 评估

> 来源：round3 digest-g7 2608.28044（LLM inference energy costs：请求/token 能耗特征）
> 交付：评估报告（本文档）。无真机实测，能耗参数为**代表性估计**（mock），需按目标硬件实测校准。

## 1. 能耗模型（请求/token 级）

一次推理请求的总能耗拆成三块：

```
E_request = E_idle + E_prefill + E_decode

E_prefill = P_prefill × (prompt_tokens / prefill_throughput)     # 预填充：并行吃 prompt
E_decode  = P_decode  × (output_tokens / decode_throughput)      # 解码：自回归逐 token

per-token 能耗（解码）≈ P_decode / decode_throughput [J/token]
```

关键观察：**解码是逐 token 串行**，能耗与输出长度线性；预填充受 prompt 长度影响但可并行，
单位 token 成本通常低于解码。能耗与 token 数近似线性，是"按 token 预算"的基础。

## 2. 关键参数（代表性估计，需实测校准）

| 参数 | GPU（云端/A100 级） | CPU 端侧（NEKO 本地） | 边缘（量化 INT8/INT4） |
|---|---|---|---|
| 功耗 P | ~300 W | ~40 W | ~5 W |
| 解码吞吐 | ~40 tok/s | ~8 tok/s | ~15 tok/s（量化提速） |
| 每 token 能耗 | ~7.5 J/token | ~5 J/token | ~0.3 J/token |
| 单请求（256 输出） | ~1.9 kJ | ~1.3 kJ | ~85 J |

> 注意：CPU 端侧吞吐低，但总功率低，每 token 能耗未必高于 GPU；边缘量化以更低压耗
> 换取吞吐，是 NEKO 端侧性价比关键。

## 3. NEKO 端侧适配

NEKO 本地/边缘推理的能耗预算应围绕**解码 token 数**而非请求数：

- **能耗 ≈ α·prompt_tokens + β·output_tokens**（α < β，解码更贵）。
- 端侧瓶颈是**总功耗 × 时长**，长时间多轮对话的能耗由累积输出 token 主导。

## 4. 预算建议

1. **设输出 token 上限**：对每请求/每会话设 output 预算（能耗与输出线性，砍输出最直接省能）。
2. **KV-cache 复用**：多轮会话复用前缀 KV，避免重复预填充（省 α·prompt 部分）。
3. **量化 + 端侧小模型**：INT8/INT4 或 4M 级 LoRA 微调小模型（对齐 K27），压降每 token 能耗。
4. **批处理/预填充合并**：可并行请求合并预填充，摊薄 α。
5. **能耗计量接入**：把"每请求 token 计数 → 估算能耗"打进 NEKO 计费/预算层，超预算降级（截断/换小模型）。

## 5. 结论

请求/token 能耗可建模为"预填充+解码"两段线性模型；NEKO 端侧预算应以**输出 token 数**
为第一控制变量，配 KV-cache 复用与量化，形成可计量的端侧推理能耗预算闭环。
