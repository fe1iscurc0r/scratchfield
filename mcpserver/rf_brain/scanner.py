"""射频大脑 · 频谱扫描调度器（Phase 5）

自主闭环的"眼睛"：把一片业余频段切成若干观测窗口（中心频点），
对每个窗口采集 IQ 快照 → 能量检测 → 超过噪声底判定为候选信号，
产出候选信号表（CandidateSignal）。

关键设计：
- 扫描器是"盲扫"的——能量检测只读 IQ 样本，不感知环境布点表 schedule。
  schedule 仅是模拟环境（sensor 合成）的布点配置；真机模式下由
  device/ 输入抽象提供真实 IQ/音频，扫描器逻辑不变。
- 所有中心频点必须落在业余频段白名单内（assert_allowed_freq，与
  rsba1_adapter 对齐），越界频点直接抛 ValueError——安全约束前置拦截。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mcpserver.rf_brain.amateur_bands import assert_allowed_freq
from mcpserver.rf_brain.sensor import generate_iq, noise_only


@dataclass
class CandidateSignal:
    """候选信号表条目。"""
    center_freq_hz: float       # 观测窗口中心频（白名单内）
    iq: np.ndarray              # IQ 快照
    energy_db: float            # 能量检测值（峰值相对噪声底，dB）
    detected: bool              # 是否判为候选信号（energy_db >= 阈值）
    ground_truth: str | None = None  # 仅测试台：真实调制 / None=噪声


@dataclass
class ScanConfig:
    """扫描调度配置。

    schedule 为模拟环境的布点表（每项：freq / modulation / snr_db / present），
    扫描器按它合成观测，但能量检测不读它——保证盲扫语义。
    """
    sample_rate: float = 2_000_000.0
    duration: float = 0.002                 # 每窗口观测时长（2ms → 4096 样本）
    energy_threshold_db: float = 12.0       # 检出阈值（相对噪声底）
    seed: int = 42
    schedule: list[dict] = field(default_factory=list)


@dataclass
class ScanResult:
    """整轮扫描结果。"""
    candidates: list[CandidateSignal]
    n_windows: int
    n_detected: int


def energy_detect(iq: np.ndarray, sample_rate: float = 2_000_000.0) -> float:
    """能量检测：峰值功率相对噪声底（dB）。

    与 feature_extractor 的 SNR 口径一致（平滑功率谱 → 20% 分位数噪声底
    → 峰值差），此处只做"有无信号"二值判定，不做调制分类。
    """
    n = len(iq)
    window = np.hanning(n)
    power = np.abs(np.fft.fftshift(np.fft.fft(iq * window))) ** 2
    db = 10 * np.log10(power + 1e-12)
    if len(db) >= 11:
        kernel = np.ones(11) / 11
        db = np.convolve(db, kernel, mode="same")
    noise_floor = float(np.percentile(db, 20))
    peak = float(np.max(db))
    return peak - noise_floor


def _synthesize_observation(item: dict, config: ScanConfig, seed: int) -> np.ndarray:
    """按布点表合成观测 IQ（仅模拟环境；真机由 device/ 输入替代）。"""
    if item.get("present", True):
        return generate_iq(
            modulation=item["modulation"],
            sample_rate=config.sample_rate,
            center_freq=item["freq"],
            duration=config.duration,
            snr_db=item.get("snr_db", 20.0),
            seed=seed,
        )
    return noise_only(sample_rate=config.sample_rate, duration=config.duration, seed=seed)


def scan_spectrum(config: ScanConfig) -> ScanResult:
    """扫描调度：遍历布点频点 → 能量检测 → 候选信号表。

    白名单校验前置：任一中心频越界即抛 ValueError，不产生半截结果。
    """
    cands: list[CandidateSignal] = []
    for i, item in enumerate(config.schedule):
        freq = int(item["freq"])
        assert_allowed_freq(freq)          # 安全约束：业余频段白名单
        iq = _synthesize_observation(item, config, seed=config.seed + i)
        energy = energy_detect(iq, config.sample_rate)
        detected = energy >= config.energy_threshold_db
        cands.append(CandidateSignal(
            center_freq_hz=freq,
            iq=iq,
            energy_db=round(energy, 2),
            detected=detected,
            ground_truth=item.get("modulation") if item.get("present", True) else None,
        ))
    return ScanResult(
        candidates=cands,
        n_windows=len(cands),
        n_detected=sum(1 for c in cands if c.detected),
    )
