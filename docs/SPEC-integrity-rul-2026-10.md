# SPEC · 设备完整性层 RUL（剩余寿命）预测接口（2026-10）

> 工单 262 任务 F。**只出 SPEC，不出代码**（原因见 §5）。

## 1. 退化状态向量

```python
state = {
    "asset_id": str,
    "t": float,                      # 观测时刻（Unix 秒或 ISO8601 字符串）
    "x": list[float],                # 退化量向量，按 measurements 顺序对齐
    "measurements": list[str],       # 例如 ["wall_thickness_mm", "crack_depth_mm"]
    "rates": list[float] | None,     # 退化速率估计（mm/y），None = 未估计
    "cov": list[list[float]] | None, # 状态协方差（可选，未估计则为 None）
    "meta": dict,                    # 工艺/材质/检验历史等上下文
}
```

退化量必须**可与 `inspections` 表对齐**：`wall_thickness_mm` ↔ `sizing`（UT/RT），
`crack_depth_mm` ↔ `sizing`，`pod` ↔ 检出概率修正项。

## 2. 失效阈值

```python
thresholds = {
    "wall_thickness_mm": {"min": 6.4},           # 设计最小壁厚（含腐蚀余量扣减）
    "crack_depth_mm":   {"max": 3.0},            # 断裂力学允许值
    "pod":              {"min": 0.9},            # 检出概率下限（与 integrity_pod 的 a90 对齐）
}
```

**语义**：达到任一阈值即判定失效（forgiving 值都不设），阈值来源必须写进 `meta.threshold_source`
（设计图号 / 评定报告号），否则预测结果不可用于决策。

## 3. 观测模型

```python
obs = {
    "z": list[float],          # 检验实测值（含噪声）
    "sigma": list[float],      # 测量不确定度（UT 测厚典型 ±0.1 mm；AE 定位另计）
    "method": str,             # UT / RT / AE / EC / VT —— 与 inspections.method 同集
    "pod": float | None,       # 该项检验的检出概率（来自 integrity_pod）
}
```

观测模型假设：`z = H·x + ε`，`ε ~ N(0, sigma²)`；当 `pod < 0.9` 时，**未检出不能当作「无缺陷」**，
必须在状态更新里引入漏检修正（`P(undetected | defect exists) = 1 - pod`）。这是 RUL 里最容易
被漏掉的一项，故写进 SPEC。

## 4. 预测接口（四段签名）

```python
def predict_to_eof(state, thresholds) -> ToEPredictionProfile: ...
def update_state(state, obs) -> dict: ...
def estimate_rates(history, window_days: float = 365.0) -> dict: ...
def check_thresholds(state, thresholds) -> dict: ...
```

```python
ToEPredictionProfile = {
    "asset_id": str,
    "t0": float,                       # 预测起点
    "quantiles": {"p10": float, "p50": float, "p90": float},  # 到期时间（ToE）
    "driving_measurement": str,        # 最先触阈的退化量
    "confidence": float,               # 0~1，由状态协方差与样本量共同决定
    "warnings": list[str],             # 例如「样本 < 3 次检验，ToE 仅供排序」
}
```

**接口约束**：纯函数、不写库、不做 IO；所有输入可 JSON 序列化（便于 cron 与 MCP 双通道调用）。

## 5. 为何只出 SPEC 不出代码

1. **数据不足**：RUL 需要「同一资产 ≥3 次带时间戳的定量检验」才能估计速率；当前仓内无 `devices.db`，
   真实检验序列在云服且尚未接入 `inspections` 表。
2. **算法是二期的**：一期只交付解析式 POD（`integrity_pod`），状态空间模型/粒子滤波属二期；
   先把**接口契约**钉死，二期实现时调用方（MCP 工具、cron）不用改。
3. **口径风险**：失效阈值的来源（设计图号/评定报告）目前无法在仓内校验，**先出 SPEC 逼出这些输入**，
   比先写一版"能跑但口径不明"的代码更安全。

## 6. 二期落地顺序（建议）

1. `apply_schema.py` 接入真实检验数据 → 2. `estimate_rates()` 用 `inspections` 序列算速率 →
3. `predict_to_eof()` 先做线性外推 + 分位数 → 4. 再考虑粒子滤波 / 贝叶斯更新。

---

> 参考实现来源：progpy（NASA-1.3，仅接口命名参考，未复制代码）
