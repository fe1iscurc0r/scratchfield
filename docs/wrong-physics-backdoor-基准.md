# S17 Wrong-Physics 后门基准

> 来源：digest-g1-2 2608.20439v1（Wrong-Physics Backdoor：神经 PDE 算子错误物理后门，标签一致性不足以检测）
> 原型：`tools/wrong_physics_detect.py` · 测试：`tools/test_wrong_physics_detect.py`（7 passed）
> 用途：仅构造评测样本用于检测研究，不含攻击工具。

## 1. 威胁模型

神经 PDE 算子（用于 rf_brain / 陆墨的物理建模）可被植入**错误物理后门**：

- 在**干净输入**上，后门模型输出与干净模型**逐点一致**（标签一致），因此基于标签/输出对拍的审计**无法发现**；
- 在含隐藏**触发分量**（秘密高频分量）的输入上，后门模型产出违反物理守恒的输出（如凭空注入能量）。

根因：物理神经方法的常见验证只做"数据一致性"（输出 vs 标签），不做"正确物理过程"验证。

## 2. 后门构造（评测样本）

以 1D 热扩散算子（周期边界，严格守恒 `sum` 不变）为可信物理模型：

- `clean_operator(u)`：热扩散一步，守恒。
- `backdoored_operator(u)`：内部检测输入是否含 `TRIGGER_FREQ=11` 的秘密高频分量；命中则在中心点注入 `INJECT_AMOUNT=10` 的非守恒能量；否则与 `clean_operator` 完全一致。

```python
from wrong_physics_detect import clean_operator, backdoored_operator, make_clean_input
u = make_clean_input()
assert (backdoored_operator(u) == clean_operator(u)).all()   # 标签一致，审计查不出
```

## 3. 检测方法（物理一致性校验，≥2 种）

| 方法 | 原理 | 触发样本 | 干净样本 |
|---|---|---|---|
| ① 守恒残差 | `|sum(out) − sum(in)|`，热扩散应守恒 | > 0（破坏守恒） | ≈ 0 |
| ② 参考偏差 | 相对可信参考（干净算子）的逐点最大偏差 | > 0（注入偏移） | = 0（逐点一致） |

`run_benchmark()` 跑 10 个触发 + 10 个干净样本：

- 两种方法都命中全部 10 个触发样本（`residual_detected=True`、`divergence_detected=True`）；
- 干净模型跑基准零误报（`n_flagged == 0`）；
- 干净输入上后门模型仍逐点一致（`clean_identical=True`），印证"标签一致检测不出"。

## 4. 结论与落点

标签一致性审计对错误物理后门**失效**；物理一致性校验（守恒残差 / 参考偏差）能有效检出。
落点建议：rf_brain 的物理模型上线前，强制跑一道"守恒/参考一致性"门控（对齐
`docs/neko-trust-memory-设计稿.md` 的写路径校验与 `mcpserver/trust_layer.py` 的评分思路）。
