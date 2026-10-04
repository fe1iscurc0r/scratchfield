"""射频大脑 · 腕带 FMCW 雷达 + IMU 融合前端（R75）

授粉自 2608.16542v1（Wristband Radar+IMU）：腕带 FMCW 雷达 + 惯性测量单元
（IMU）融合前端，110K MAC/帧，47% 分类器调用能耗降低。核心：融合前端在
「低活动」帧门控跳过分类器，只对检测到活动的帧调用分类器——事件驱动的能耗节约。

原型（纯 numpy）：
  - fmcw_range_doppler  FMCW 雷达 chirp → 距离-多普勒图（2D FFT）
  - imu_features        加速度幅度/方差特征
  - fusion_gate         雷达能量 + IMU 活动 → 是否调用分类器
  - mac_budget          每帧 MAC 估算（≤110K 验收）
  - classifier_energy   门控前后分类器调用能耗对比（≥47% 降低验收）

验收口径：MAC/帧 ≤110K；稀疏活动流上分类器调用能耗较「逐帧分类」降 ≥47%。
"""
from __future__ import annotations

import numpy as np

__all__ = ["fmcw_range_doppler", "imu_features", "fusion_gate", "mac_budget", "classifier_energy"]


def fmcw_range_doppler(chirps: np.ndarray, n_range_fft: int = 64) -> np.ndarray:
    """FMCW 距离-多普勒：每个 chirp 距离 FFT → 慢时维 FFT。输入 (N_chirp, M)。"""
    c = np.asarray(chirps, dtype=float)
    rng = np.fft.fft(c, n=n_range_fft, axis=1)             # 距离维 FFT
    rd = np.fft.fftshift(np.fft.fft(rng, axis=0), axes=0)  # 多普勒维 FFT
    return np.abs(rd) ** 2


def imu_features(accel: np.ndarray) -> np.ndarray:
    """IMU 加速度 → 幅度 + 方差特征（3 轴 → 标量幅度序列的统计量）。"""
    a = np.asarray(accel, dtype=float)
    mag = np.linalg.norm(a, axis=1)
    return np.array([float(np.mean(mag)), float(np.var(mag))])


def fusion_gate(rd_map: np.ndarray, imu: np.ndarray, *, radar_thresh: float = 30.0,
                imu_thresh: float = 0.5) -> bool:
    """融合门控：雷达峰值/底噪比 或 IMU 活动超阈值 → 调用分类器，否则跳过（节能）。

    用峰值(99 分位)/中位数做 SNR 口径，对绝对增益鲁棒（噪声下 SNR 低、有目标时高）。
    """
    med = float(np.median(rd_map)) + 1e-12
    radar_snr = float(np.percentile(rd_map, 99)) / med
    imu_activity = float(imu[1])
    return radar_snr > radar_thresh or imu_activity > imu_thresh


def mac_budget(n_chirps: int, m_samples: int, n_range_fft: int) -> int:
    """每帧 MAC 估算：距离 FFT（n_chirps×M·log2M）+ 多普勒 FFT（n_fft×n_chirps·log2n_chirps）。"""
    rd = n_chirps * m_samples * int(np.log2(m_samples))
    dop = n_range_fft * n_chirps * int(np.log2(n_chirps))
    return int(rd + dop)


def classifier_energy(activity: np.ndarray, *, per_call_energy: float = 1.0) -> dict:
    """门控 vs 逐帧分类的分类器调用能耗对比。

    activity: bool 数组，True=该帧有活动（需分类）。逐帧 = 全调用；
    门控 = 只在 activity 帧调用。返回 {always, gated, reduction}。
    """
    act = np.asarray(activity, dtype=bool)
    always = act.size * per_call_energy
    gated = int(act.sum()) * per_call_energy
    return {"always": always, "gated": gated, "reduction": (always - gated) / always if always else 0.0}
