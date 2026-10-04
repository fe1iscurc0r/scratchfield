"""A46 · AgenticTwin 数字孪生异常检测管道原型（来源 2608.11679）

论文核心：LLM 推理 + 数字孪生异常检测管道，支持自然语言查询，
人工评测诊断质量提升。

原型（mock，显式标注）：
  - 数字孪生遥测：慢漂移温度 + 噪声，注入尖峰异常（无真实数据）
  - 检测器：EWMA 基线 + z 分数门限（numpy，替代论文的专用异常检测模型）
  - 自然语言查询：规则解析器（关键词→指标），输出中文诊断文本
评估：检测 F1 ≥ 阈值；查询解析命中正确指标。

运行：python -m mcpserver.agent_lab.prototypes.agentic_twin
"""
from __future__ import annotations

import numpy as np


def synthesize_telemetry(n: int = 600, seed: int = 5, n_anom: int = 8
                         ) -> tuple[np.ndarray, np.ndarray]:
    """mock 遥测：慢漂移温度 + 高斯噪声，随机注入 n_anom 个尖峰；返回 (序列, 真值)"""
    rng = np.random.default_rng(seed)
    x = 25.0 + 0.005 * np.arange(n) + 0.3 * rng.standard_normal(n)
    truth = np.zeros(n, dtype=bool)
    pos = rng.choice(np.arange(50, n), size=n_anom, replace=False)
    x[pos] += rng.uniform(4.0, 8.0, size=n_anom)
    truth[pos] = True
    return x, truth


def ewma_detect(x: np.ndarray, span: int = 20, z_thr: float = 4.0) -> np.ndarray:
    """EWMA 基线 + 自适应方差，z 分数超阈值判异常（单遍在线算法）"""
    alpha = 2.0 / (span + 1)
    mu = np.empty_like(x)
    var = np.empty_like(x)
    mu[0] = x[0]
    var[0] = 1.0
    for i in range(1, len(x)):
        mu[i] = alpha * x[i - 1] + (1 - alpha) * mu[i - 1]
        var[i] = alpha * (x[i - 1] - mu[i]) ** 2 + (1 - alpha) * var[i - 1]
    z = (x - mu) / np.maximum(np.sqrt(var), 1e-6)
    return z > z_thr


def f1(pred: np.ndarray, truth: np.ndarray) -> float:
    tp = float((pred & truth).sum())
    fp = float((pred & ~truth).sum())
    fn = float((~pred & truth).sum())
    if tp == 0:
        return 0.0
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    return 2 * prec * rec / (prec + rec)


def answer_query(x: np.ndarray, flags: np.ndarray, query: str) -> str:
    """自然语言查询（规则解析替代 LLM 推理）：关键词 → 指标诊断文本"""
    q = query.lower()
    if "温度" in query or "temp" in q:
        return f"当前温度 {x[-1]:.2f}°C，峰值 {x.max():.2f}°C"
    if "异常" in query or "anomal" in q:
        return f"共检出 {int(flags.sum())} 次异常"
    return "不支持的查询指标"


def evaluate(n: int = 600, seed: int = 5) -> dict:
    """端到端：生成遥测 → 检测 → 自然语言查询，返回 F1 与查询结果"""
    x, truth = synthesize_telemetry(n=n, seed=seed)
    flags = ewma_detect(x)
    return dict(
        f1=f1(flags, truth),
        n_true=int(truth.sum()),
        n_pred=int(flags.sum()),
        q_temp=answer_query(x, flags, "当前温度是多少"),
        q_anom=answer_query(x, flags, "最近有多少异常？"),
    )


if __name__ == "__main__":
    r = evaluate()
    print(f"AgenticTwin：检测 F1={r['f1']:.3f}（真异常 {r['n_true']}，检出 {r['n_pred']}）")
    print("查询示例 →", r["q_temp"], "|", r["q_anom"])
