"""射频大脑 · 参考解调器（Phase 3 · 玩具级）

numpy 实现 GFSK / FSK / OOK 简单解调，输出符号流 + BER 估计。
只为验证闭环，不做性能优化（SPEC 第七章明确）。
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.schemas import DemodFeedback


def demodulate_symbols(iq: np.ndarray, modulation: str, sample_rate: float, symbol_rate: float) -> np.ndarray:
    """解调 IQ 样本，返回 0/1 符号流（int ndarray）。

    demodulate() 与 pocsag.demodulate_and_decode() 共用此符号提取逻辑，
    使上层协议解码器（如 POCSAG）能拿到 bit 流而非仅统计反馈。
    """
    n = len(iq)
    mod = modulation.upper()

    if mod == "GFSK" or mod == "FSK":
        # 非相干鉴频：瞬时频率 = 相位差
        phase = np.unwrap(np.angle(iq))
        inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
        sps = max(1, int(sample_rate / symbol_rate))
        n_sym = len(inst_freq) // sps
        if n_sym == 0:
            return np.array([], dtype=int)
        return np.array([
            1 if np.mean(inst_freq[i * sps:(i + 1) * sps]) > 0 else 0
            for i in range(n_sym)
        ], dtype=int)
    elif mod == "OOK":
        # 幅度检测：包络阈值
        env = np.abs(iq)
        sps = max(1, int(sample_rate / symbol_rate))
        n_sym = len(env) // sps
        if n_sym == 0:
            return np.array([], dtype=int)
        thr = np.mean(env)
        return np.array([
            1 if np.mean(env[i * sps:(i + 1) * sps]) > thr else 0
            for i in range(n_sym)
        ], dtype=int)
    raise ValueError(f"不支持的调制: {modulation}")


def demodulate(iq: np.ndarray, modulation: str, sample_rate: float, symbol_rate: float) -> DemodFeedback:
    """解调 IQ 样本，返回反馈（含 BER 估计）。"""
    mod = modulation.upper()
    if mod not in ("GFSK", "FSK", "OOK"):
        return _fail(f"不支持的调制: {modulation}")

    symbols = demodulate_symbols(iq, modulation, sample_rate, symbol_rate)
    if len(symbols) < 2:
        return _fail("符号数不足")

    # BER 估计：符号流自一致性（简化的信号质量指标，非真实 BER）
    # 用符号跳变率 + 幅度稳定性近似；M1 仅需一个可用的 success 判定
    # 稳定信号应符号分布不极端（0/1 都有）且跳变合理
    ones_ratio = float(np.mean(symbols))
    ber_est = min(0.5, abs(ones_ratio - 0.5) * 0.3 + 0.02)  # 偏离 50% 越远越可疑
    success = 0.05 <= ones_ratio <= 0.95
    output_count = int(len(symbols))

    return DemodFeedback(
        status="ok" if success else "failed",
        demod_success=success,
        bit_error_rate_estimate=round(ber_est, 4),
        output_symbol_count=output_count,
        feedback=f"解调{'成功' if success else '失败'}，符号数 {output_count}，1占比 {ones_ratio:.2f}",
    )


def _fail(reason: str) -> DemodFeedback:
    return DemodFeedback(
        status="failed",
        demod_success=False,
        bit_error_rate_estimate=None,
        output_symbol_count=0,
        feedback=reason,
    )
