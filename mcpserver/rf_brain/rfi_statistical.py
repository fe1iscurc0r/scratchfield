"""R48 STRIPE 式统计滤波干扰识别（子带阈值 + 时域累积去毛刺 → 干扰频段/时段标记）

来源授粉点：STRIPE——子带能量阈值 + 时域累积的自动干扰识别，FPGA 2377 LUT
约束映射嵌入式可行。迁移到 rf_brain：把 时-频功率矩阵 切成子带，按统计阈值
（中位数 + k·MAD，稳健抗离群）逐子带判超限，再用时域累积（连续 M 帧确认）
去掉单帧毛刺，输出「干扰频段 × 时段」二值标记。

资源约束（ESP32 级）：状态仅需 O(子带数 × 持久帧数) 字节，逐帧计算量 O(子带数)，
见 estimate_resources()。无硬件依赖，可离线单元测试。

验收口径：合成干扰场景识别率 ≥85%，误报率 ≤5%。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_MAD_TO_STD = 1.4826  # 高斯下 MAD → 标准差的比例因子


def _subband_energy_matrix(lin: np.ndarray, n_subbands: int) -> np.ndarray:
    """(T, F) 线性功率 → (T, B) 子带平均能量（向量化）。

    子带按等宽划分，尾部不足一个子带的 bin 被丢弃。
    """
    T, F = lin.shape
    B = int(n_subbands)
    per = F // B
    if per < 1:
        raise ValueError(f"频谱长度 {F} 小于子带数 {B}，无法划分子带")
    return lin[:, : B * per].reshape(T, B, per).mean(axis=2)


def _frame_energy(frame_lin: np.ndarray, n_subbands: int) -> np.ndarray:
    """(F,) 线性功率 → (B,) 子带平均能量（单帧）。"""
    return _subband_energy_matrix(np.asarray(frame_lin)[None, :], n_subbands)[0]


@dataclass
class ResourceEstimate:
    """嵌入式资源估算（ESP32 级约束核对）。"""

    n_subbands: int
    persistence: int
    state_bytes: int
    ops_per_frame: int

    @property
    def esp32_compatible(self) -> bool:
        # ESP32 经典款 ~320 KB 片上 RAM；预留 1 KB 级状态即视为可嵌入式
        return self.state_bytes < 4096


class StatisticalRFIDetector:
    """子带统计滤波 + 时域累积的干扰识别器。

    检测流程：
      1. 时-频功率矩阵 (T, F) → 切成 B 个子带，逐子带取平均能量（线性功率）
      2. 逐子带稳健噪声底 = 帧间中位数；阈值 = 噪声底 + sigma · MAD
      3. 能量超阈值 → 候选；连续 `persistence` 帧确认 → 判为干扰（去毛刺）
    """

    def __init__(self, n_subbands: int, *, sigma: float = 4.0, persistence: int = 3) -> None:
        if n_subbands < 2:
            raise ValueError(f"n_subbands 过小: {n_subbands}（需 >= 2）")
        if persistence < 1:
            raise ValueError(f"persistence 需 >= 1，实际 {persistence}")
        self.n_subbands = int(n_subbands)
        self.sigma = float(sigma)
        self.persistence = int(persistence)

    # ---------- 子带能量 ----------

    def _subband_energy(self, t_f_db: np.ndarray) -> np.ndarray:
        """(T, F) dB 矩阵 → (T, B) 子带平均能量（线性功率，非负）。"""
        x = np.asarray(t_f_db, dtype=float)
        if x.ndim == 1:
            x = x[None, :]
        if x.ndim != 2:
            raise ValueError(f"输入必须为 1D/2D，实际 ndim={x.ndim}")
        return _subband_energy_matrix(10.0 ** (x / 10.0), self.n_subbands)

    def _thresholds(self, energy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """返回每子带 (噪声底, 阈值)。稳健估计，抗干扰帧抬高均值。"""
        noise_floor = np.median(energy, axis=0)
        mad = np.median(np.abs(energy - noise_floor), axis=0)
        thr = noise_floor + self.sigma * _MAD_TO_STD * mad
        return noise_floor, thr

    # ---------- 检测 ----------

    def detect(self, t_f_db: np.ndarray) -> np.ndarray:
        """返回 (T, B) 干扰标记（bool）。T=1 时返回 (B,)。"""
        energy = self._subband_energy(t_f_db)
        _, thr = self._thresholds(energy)
        exceed = energy > thr[None, :]
        confirmed = self._persist(exceed)
        single = np.asarray(t_f_db).ndim == 1
        return confirmed[0] if single else confirmed

    def _persist(self, exceed: np.ndarray) -> np.ndarray:
        """连续 `persistence` 帧超限才确认（时域累积去毛刺）。"""
        T, B = exceed.shape
        out = np.zeros_like(exceed, dtype=bool)
        run = np.zeros(B, dtype=int)
        for t in range(T):
            run = np.where(exceed[t], run + 1, 0)
            out[t] = run >= self.persistence
        return out

    # ---------- 对比基线（CA-CFAR 风格，无时域累积） ----------

    def detect_no_persistence(self, t_f_db: np.ndarray) -> np.ndarray:
        """仅统计阈值、不做时域累积的基线（用于与累积版对比毛刺抑制）。"""
        energy = self._subband_energy(t_f_db)
        _, thr = self._thresholds(energy)
        exceed = energy > thr[None, :]
        single = np.asarray(t_f_db).ndim == 1
        return exceed[0] if single else exceed

    # ---------- 资源估算 ----------

    def estimate_resources(self) -> ResourceEstimate:
        B = self.n_subbands
        # 噪声底 + MAD + 能量缓存（float64 各 B 个）+ 连续计数（int8 B×persistence）
        state_bytes = B * 8 * 3 + B * self.persistence
        ops_per_frame = B * (1 + self.persistence)  # 阈值比较 + 连续帧更新
        return ResourceEstimate(
            n_subbands=B,
            persistence=self.persistence,
            state_bytes=state_bytes,
            ops_per_frame=ops_per_frame,
        )


class StreamingRFIDetector:
    """逐帧流式干扰识别（O(B·history) 状态，适配 ESP32 实时管线）。

    与 StatisticalRFIDetector 共用同一套「子带阈值 + 时域累积」逻辑，区别在于：
      - 噪声底用滑动窗口在线估计，整批 (T,F) 矩阵无需驻留内存；
      - 只把「未确认干扰」的子带能量回填噪声底统计（反馈），因此长干扰突发
        不会污染噪声底、不会中途丢检。

    缓冲用 float32 / int32，状态量压到百字节级（见 estimate_resources）。
    """

    def __init__(
        self,
        n_subbands: int,
        *,
        sigma: float = 4.0,
        persistence: int = 3,
        history: int = 32,
    ) -> None:
        if n_subbands < 2:
            raise ValueError(f"n_subbands 过小: {n_subbands}（需 >= 2）")
        if persistence < 1 or history < persistence:
            raise ValueError("需 persistence >= 1 且 history >= persistence")
        self.n_subbands = int(n_subbands)
        self.sigma = float(sigma)
        self.persistence = int(persistence)
        self.history = int(history)
        self._buf = np.full((self.n_subbands, self.history), np.nan, dtype=np.float32)
        self._cnt = np.zeros(self.n_subbands, dtype=np.int32)  # 每子带已写入样本数
        self._run = np.zeros(self.n_subbands, dtype=np.int32)  # 连续超限帧计数

    def update(self, frame_db: np.ndarray) -> np.ndarray:
        """处理一帧 (F,) dB 频谱，返回 (B,) 干扰标记（bool）。"""
        frame = np.asarray(frame_db, dtype=float)
        if frame.ndim != 1:
            raise ValueError(f"update 需一维频谱帧，实际 ndim={frame.ndim}")
        energy = _frame_energy(10.0 ** (frame / 10.0), self.n_subbands)

        # 首帧无历史：先播种噪声底，本帧不做判决
        if self._cnt.min() < 1:
            self._buf[:, 0] = energy.astype(np.float32)
            self._cnt[:] = 1
            return np.zeros(self.n_subbands, dtype=bool)

        noise = np.nanmedian(self._buf, axis=1)
        mad = np.nanmedian(np.abs(self._buf - noise[:, None]), axis=1)
        thr = noise + self.sigma * _MAD_TO_STD * mad

        exceed = energy > thr
        self._run = np.where(exceed, self._run + 1, 0)
        confirmed = self._run >= self.persistence

        # 反馈：暖机期无条件累积；之后只回填「未确认干扰」的子带能量
        warmup = self._cnt < self.history
        update_mask = (~confirmed) | warmup
        b_idx = np.flatnonzero(update_mask)
        if b_idx.size:
            col = self._cnt[b_idx] % self.history
            self._buf[b_idx, col] = energy[b_idx].astype(np.float32)
            self._cnt[b_idx] += 1
        return confirmed

    def estimate_resources(self) -> ResourceEstimate:
        B = self.n_subbands
        state_bytes = B * self.history * 4 + B * 8  # float32 缓冲 + int32 计数/运行
        ops_per_frame = B * (2 * self.history + 2)  # 中位数/MAD + 阈值 + 累积
        return ResourceEstimate(
            n_subbands=B,
            persistence=self.persistence,
            state_bytes=state_bytes,
            ops_per_frame=ops_per_frame,
        )
