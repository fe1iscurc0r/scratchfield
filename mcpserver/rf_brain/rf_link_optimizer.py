"""射频大脑 · 射频链路自动优化（R68）

授粉自 round3 digest-g4 扩散变异核 + 数字孪生（2608.27649 FGDDMKCPD + 2608.28437
LUCID）：扩散变异核把「生成」与「发现」分离——学习在可行域内的**变异算子**而非
直接生成候选，配合外部工程工具（数字孪生/仿真）做正确性判断；LUCID 的数字孪生
闭环（DITL + SimBridge）提供无线场景的仿真底座。

跨领域落地（rf_brain 协议配置自动探索）：
  - 配置空间 = 波形 pulse shaping（rect/rrc/gaussian）× 滚降系数 × 匹配滤波 ×
    纠错码（none/重复码/Hamming）
  - 数字孪生 = BPSK over AWGN 的 BER 解析仿真（Q 函数，配置 → 实现损耗 + 编码增益）
  - 扩散变异核 = 离散翻转 + 连续高斯扰动的变异引擎 + 选择循环

原型：配置变异引擎 + 仿真验证循环，自动探索优于基线 BER 的协议配置。
验收：探索到优于基线 BER 的配置 ≥1 组。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "config_loss",
    "ber_bpsk",
    "baseline_config",
    "mutate_config",
    "optimize_rf_link",
]


def qfunc(x: float) -> float:
    """Q(x) = 0.5·erfc(x/√2)。"""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def ber_bpsk(eb_n0_db: float, loss_db: float = 0.0, gain_db: float = 0.0) -> float:
    """BPSK over AWGN 的 BER：Q(√(2·10^((EbN0−loss+gain)/10)))。"""
    eff_db = eb_n0_db - loss_db + gain_db
    eff = 10.0 ** (eff_db / 10.0)
    return qfunc(math.sqrt(2.0 * eff))


_PULSE_LOSS = {"rect": 1.0, "rrc": 0.0, "gaussian": 0.6}
_CODE_GAIN = {"none": 0.0, "rep3": 2.0, "hamming": 2.8}


def config_loss(config: dict) -> tuple[float, float]:
    """配置 → (实现损耗 dB, 编码增益 dB)。"""
    loss = _PULSE_LOSS.get(config.get("pulse"), 1.0)
    if config.get("matched", False):
        loss -= 0.8                      # 匹配滤波回收脉冲成形损耗
    loss += 1.5 * abs(float(config.get("rolloff", 0.35)) - 0.35)  # 滚降偏离最优的代价
    gain = _CODE_GAIN.get(config.get("code"), 0.0)
    return loss, gain


def baseline_config() -> dict:
    """基线配置：矩形脉冲、无匹配滤波、滚降 1.0、无纠错（实现损耗最大）。"""
    return {"pulse": "rect", "rolloff": 1.0, "matched": False, "code": "none"}


def mutate_config(config: dict, rng: np.random.Generator) -> dict:
    """扩散变异核：离散字段随机翻转 + 连续字段高斯扰动（可行域内变异算子）。"""
    c = dict(config)
    if rng.random() < 0.4:
        c["pulse"] = rng.choice(list(_PULSE_LOSS.keys()))
    if rng.random() < 0.4:
        c["matched"] = bool(rng.integers(0, 2))
    if rng.random() < 0.4:
        c["code"] = rng.choice(list(_CODE_GAIN.keys()))
    if rng.random() < 0.5:
        c["rolloff"] = float(np.clip(c["rolloff"] + rng.normal(0.0, 0.15), 0.1, 1.0))
    return c


@dataclass
class OptimizationResult:
    """射频链路自动优化结果。"""
    best_config: dict
    best_ber: float
    baseline_ber: float
    improvement: float                  # 相对 BER 下降（基线/最优，>1 表示更优）
    explored: list[dict] = field(default_factory=list)


def optimize_rf_link(eb_n0_db: float = 5.0, *, iterations: int = 200, seed: int = 0) -> OptimizationResult:
    """配置变异 + 仿真验证循环：扩散变异 → 数字孪生 BER 评估 → 保留更优。"""
    rng = np.random.default_rng(seed)
    base_cfg = baseline_config()
    base_loss, base_gain = config_loss(base_cfg)
    base_ber = ber_bpsk(eb_n0_db, base_loss, base_gain)

    best_cfg, best_ber = base_cfg, base_ber
    log = []
    for _ in range(iterations):
        cand = mutate_config(best_cfg if rng.random() < 0.5 else base_cfg, rng)
        loss, gain = config_loss(cand)
        ber = ber_bpsk(eb_n0_db, loss, gain)
        log.append({"config": cand, "ber": ber})
        if ber < best_ber:
            best_cfg, best_ber = cand, ber

    return OptimizationResult(
        best_config=best_cfg,
        best_ber=best_ber,
        baseline_ber=base_ber,
        improvement=(base_ber / best_ber if best_ber > 0 else float("inf")),
        explored=log,
    )
