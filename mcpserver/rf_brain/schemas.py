"""射频大脑 · 接口协议 schema（Phase 0）

协议无关抽象层的基石：决策层只认 FeatureVector（输入）和 Decision（输出），
底层是 LoRa/BLE/仿真数据都不关心，协议细节封在适配器里。

三个 schema 字段必须与 SPEC 3.x 完全一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeatureVector:
    """感知层 → 决策层的特征向量。

    字段与 SPEC 3.1 完全一致。
    """
    timestamp: str
    center_freq_hz: float
    sample_rate_hz: float
    n_samples: int
    # 核心特征（rule_engine 和 decision_layer 都从这里读）
    peak_freq_hz: Optional[float]          # 频谱主峰频率（相对中心频的偏移 + 中心频）
    bandwidth_hz: Optional[float]          # 信号带宽（-3dB 或等效）
    snr_db: float                          # 信噪比估计
    spectral_flatness: float               # 0~1，越接近 1 越平坦（噪声）
    symbol_rate_estimate_hz: Optional[float]  # 符号率估计
    n_peaks: int                           # 谱峰数量（FSK 类双峰）
    peak_separation_hz: Optional[float]    # 双峰间距（单峰为 None）
    envelope_cv: float = 0.0               # 包络变异系数：OOK 幅度键控→高(~0.8)，FSK/GFSK 恒定包络→低(~0.07)
    freq_transition_slope: Optional[float] = None  # Phase 4：瞬时频率轨迹每样本斜率×符号周期，FSK 硬切换→高(~2×dev)，GFSK 高斯平滑→低
    modulation_candidates: list[str] = field(default_factory=list)  # rule_engine 预筛

    def is_valid_signal(self, snr_threshold_db: float = 5.0, flatness_threshold: float = 0.5) -> bool:
        """有效信号判定：SNR 够高 且 频谱足够集中（flatness 低）。

        噪声频谱平坦（flatness→1），调制信号频谱集中（flatness→0）。
        纯靠 SNR 会误判——噪声峰值天然比中位数高 ~10dB。
        """
        return self.snr_db >= snr_threshold_db and self.spectral_flatness <= flatness_threshold


@dataclass
class Decision:
    """决策层 → 回写层的解调决策。

    字段与 SPEC 3.2 完全一致。
    """
    decision: str                          # 固定 "demodulate"
    modulation: str                        # 选定的调制方式（如 GFSK/FSK/OOK）
    demod_params: dict
    confidence: float
    reasoning: str
    alternatives: list[dict] = field(default_factory=list)  # 候选 + 置信度


@dataclass
class DemodFeedback:
    """回写层 → 决策层的解调结果反馈。

    字段与 SPEC 3.3 完全一致。
    """
    status: str                            # "ok" / "no_signal" / "failed"
    demod_success: bool
    bit_error_rate_estimate: Optional[float] = None
    output_symbol_count: int = 0
    feedback: str = ""
