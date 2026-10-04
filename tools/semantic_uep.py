"""W58-03 语义 UEP 原型（信息驱动不等错误保护）

依据 docs/semantic-uep-勘察.md：语义重要性 → (编码速率, 重传次数, 功率偏置) 三元映射，
做成查表 + 可调函数。离线打分器输出重要性，查表得发射参数；不要求 MCU 在线算 MI 梯度。

纯 numpy/stdlib，无真机。
"""
from __future__ import annotations

import numpy as np

__all__ = ["uep_params", "protection_strength", "UEP_TABLE"]

# 语义等级 → (编码速率, 重传次数, 功率偏置 dB)。码率越低/重传越多/功率越高 = 保护越强。
UEP_TABLE: dict[int, dict] = {
    0: {"code_rate": 1 / 3, "retx": 2, "power_bias_db": 6.0},   # L0 关键（告警/心跳失联）
    1: {"code_rate": 1 / 2, "retx": 1, "power_bias_db": 3.0},   # L1 重要（事件/命令确认）
    2: {"code_rate": 4 / 5, "retx": 0, "power_bias_db": 0.0},   # L2 常规（遥测/日志）
}


def uep_params(
    importance: int,
    *,
    code_rate: float | None = None,
    retx: int | None = None,
    power_bias_db: float | None = None,
) -> dict:
    """语义重要性 → 三元发射参数（查表 + 可选覆盖）。"""
    if importance not in UEP_TABLE:
        raise ValueError(f"未知语义等级 {importance}，可选 {sorted(UEP_TABLE)}")
    base = UEP_TABLE[importance]
    return {
        "code_rate": base["code_rate"] if code_rate is None else float(code_rate),
        "retx": base["retx"] if retx is None else int(retx),
        "power_bias_db": base["power_bias_db"] if power_bias_db is None else float(power_bias_db),
    }


def protection_strength(params: dict) -> float:
    """保护强度单调度量 = (1/码率) × (1+重传) × 10^(功率偏置/10)。

    码率越低（冗余越多）、重传越多、功率越高 → 强度越大。
    """
    return (1.0 / params["code_rate"]) * (1.0 + params["retx"]) * (10.0 ** (params["power_bias_db"] / 10.0))
