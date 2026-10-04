"""R43 信息熵频谱压缩采样（KATok 授粉 · 自适应 token 选择器 → SDR 频谱压缩感知）

来源授粉点：2608.24293v1（KATok）——评估内容"丰富度"决定保留/丢弃，位置预测
保证空间对齐。迁移到 ESP32/SDR 的压缩采样：边缘侧评估各频段"信息熵"，动态丢弃
低信息量（噪声般平坦）的频段，仅上传高价值频谱片段。

纯 numpy 实现，无硬件依赖，可离线单元测试。核心指标：

  - band_info_scores  按频段算"信息量"分数（功率谱平坦度近似熵：越平坦→越像噪声→信息越少）
  - adaptive_keep     保留 top-k 或超过阈值的频段
  - compress          输入完整频谱 → 输出保留频段 + 压缩率 + 逐段分数
  - retention_curve   扫描保留比例，输出「压缩率 vs 关键信号保留率」曲线（验收用）

验收口径：合成频谱压缩 ≥5× 时关键信号特征完整（检测率 ≥90%）。
真机侧仅需把本模块的"保留频段掩码"下发到采样逻辑，跳过被丢弃频段的采样/上传。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

_EPS = 1e-12


def _as_lin(psd: np.ndarray) -> np.ndarray:
    """把 dB 或线性功率统一转成线性功率（非负）。"""
    x = np.asarray(psd, dtype=float)
    if x.size == 0:
        raise ValueError("空频谱，无法评估信息熵")
    if x.ndim != 1:
        raise ValueError(f"频谱必须为一维，实际 ndim={x.ndim}")
    if np.any(x < 0):
        # 出现负值 => 视为 dB 域，转线性
        return 10.0 ** (x / 10.0)
    return x


def band_info_scores(psd: np.ndarray, band_size: int) -> np.ndarray:
    """把频谱切成等宽频段，返回每段的信息量分数（0~1，越大越值得保留）。

    信息量 = 1 - 功率谱平坦度（平坦度越高越像噪声 → 信息越少）。
    全程向量化（reshape 后按轴聚合，无逐段 Python 循环），适配边缘侧大频谱实时评估。
    """
    band_size = int(band_size)
    if band_size < 2:
        raise ValueError(f"band_size 过小: {band_size}（需 >= 2）")
    lin = _as_lin(psd)
    n_bands = lin.size // band_size
    if n_bands == 0:
        raise ValueError(f"频谱长度 {lin.size} 小于 band_size {band_size}")
    bands = lin[: n_bands * band_size].reshape(n_bands, band_size)
    am = bands.mean(axis=1)                          # 算术均值（线性功率）
    gm = np.exp(np.log(bands + _EPS).mean(axis=1))   # 几何均值
    flatness = np.where(am > _EPS, gm / np.maximum(am, _EPS), 0.0)
    return 1.0 - np.clip(flatness, 0.0, 1.0)


def adaptive_keep(
    psd: np.ndarray,
    band_size: int,
    *,
    keep_ratio: float | None = None,
    threshold: float | None = None,
) -> np.ndarray:
    """返回每个频段的保留掩码（bool）。

    - keep_ratio：保留信息量最高的前 keep_ratio 比例频段（0<r<=1）。
    - threshold：保留信息量 >= threshold 的频段。
    两者互斥；都缺省时抛错。
    """
    if (keep_ratio is None) == (threshold is None):
        raise ValueError("keep_ratio 与 threshold 必须且只能指定一个")
    scores = band_info_scores(psd, band_size)
    n_bands = scores.size
    if keep_ratio is not None:
        if not 0.0 < keep_ratio <= 1.0:
            raise ValueError(f"keep_ratio 需在 (0,1]，实际 {keep_ratio}")
        # 直接取 top-k 而不是阈值切分：避免大量频段在阈值处并列导致过量保留
        k = min(n_bands, max(1, int(round(n_bands * keep_ratio))))
        order = np.argsort(-scores, kind="stable")  # 降序、并列时按原序稳定
        mask = np.zeros(n_bands, dtype=bool)
        mask[order[:k]] = True
        return mask
    # threshold 分支
    return scores >= float(threshold)


@dataclass
class CompressedSpectrum:
    """压缩采样结果。"""

    band_size: int
    n_bands: int
    keep_mask: np.ndarray          # (n_bands,) bool
    info_scores: np.ndarray        # (n_bands,) float 信息量分数
    kept_freqs: list[np.ndarray]   # 每个保留频段对应的频率片段
    kept_psd: list[np.ndarray]     # 每个保留频段对应的频谱片段（dB 域，原样）
    kept_band_indices: np.ndarray  # 保留频段的序号
    compression_ratio: float       # 原始频点数 / 保留频点数


def compress(
    freqs: np.ndarray,
    psd_db: np.ndarray,
    band_size: int,
    *,
    keep_ratio: float | None = None,
    threshold: float | None = None,
) -> CompressedSpectrum:
    """对一整帧频谱做压缩采样。

    freqs / psd_db 等长；不足一个 band 的尾部会被裁剪（位置对齐，KATok 空间对齐）。
    """
    freqs = np.asarray(freqs, dtype=float)
    psd_db = np.asarray(psd_db, dtype=float)
    if freqs.shape != psd_db.shape:
        raise ValueError(f"freqs 与 psd_db 长度不一致: {freqs.shape} vs {psd_db.shape}")
    band_size = int(band_size)
    n_bands = freqs.size // band_size
    if n_bands == 0:
        raise ValueError(f"频谱长度 {freqs.size} 小于 band_size {band_size}")
    used = n_bands * band_size
    freqs = freqs[:used]
    psd_db = psd_db[:used]

    keep_mask = adaptive_keep(psd_db, band_size, keep_ratio=keep_ratio, threshold=threshold)
    scores = band_info_scores(psd_db, band_size)

    kept_freqs: list[np.ndarray] = []
    kept_psd: list[np.ndarray] = []
    kept_idx: list[int] = []
    for b in range(n_bands):
        if keep_mask[b]:
            s = b * band_size
            kept_freqs.append(freqs[s : s + band_size])
            kept_psd.append(psd_db[s : s + band_size])
            kept_idx.append(b)

    kept_bins = sum(len(x) for x in kept_freqs)
    ratio = float(used) / float(kept_bins) if kept_bins else float("inf")
    return CompressedSpectrum(
        band_size=band_size,
        n_bands=n_bands,
        keep_mask=keep_mask,
        info_scores=scores,
        kept_freqs=kept_freqs,
        kept_psd=kept_psd,
        kept_band_indices=np.asarray(kept_idx, dtype=int),
        compression_ratio=ratio,
    )


def evaluate(
    psd_db: np.ndarray,
    band_size: int,
    signal_band_indices: Sequence[int],
    keep_mask: np.ndarray,
) -> tuple[float, float]:
    """给定保留掩码，返回 (压缩率, 关键信号检测率)。

    detection = 保留频段里命中到的关键信号频段比例。
    """
    psd_db = np.asarray(psd_db, dtype=float)
    band_size = int(band_size)
    n_bands = psd_db.size // band_size
    keep_mask = np.asarray(keep_mask, dtype=bool)
    kept = int(np.count_nonzero(keep_mask))
    ratio = float(n_bands) / float(kept) if kept else float("inf")

    signals = {int(i) for i in signal_band_indices if 0 <= int(i) < n_bands}
    if not signals:
        return ratio, 1.0
    hit = sum(1 for i in signals if keep_mask[i])
    return ratio, float(hit) / float(len(signals))


def retention_curve(
    psd_db: np.ndarray,
    band_size: int,
    signal_band_indices: Sequence[int],
    keep_ratios: Iterable[float] = (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 1.0),
) -> tuple[np.ndarray, np.ndarray]:
    """扫描保留比例 → 输出「压缩率 vs 关键信号保留率」曲线（验收图数据）。"""
    ratios: list[float] = []
    rets: list[float] = []
    for r in keep_ratios:
        mask = adaptive_keep(psd_db, band_size, keep_ratio=r)
        comp, det = evaluate(psd_db, band_size, signal_band_indices, mask)
        ratios.append(comp)
        rets.append(det)
    return np.asarray(ratios, dtype=float), np.asarray(rets, dtype=float)
