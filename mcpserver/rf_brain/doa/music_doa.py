"""MUSIC DOA — 迁入自 /tmp/music_doa.py（HW-02 Tier 2 储备）

MUSIC (MUltiple SIgnal Classification), Schmidt 1986
阵列信号 DOA 估计：协方差特征分解 → 信号/噪声子空间 → 空间谱扫描

边界约束：
- 均匀线阵（ULA），远场窄带信号，各源统计独立（不相干）
- 阵元数 M ≥ 4：数学重硬件苛，单通道（1-2 阵元）实际不实用
- 信号源数 D < M（调用方负责估计或指定）
- 阵元间距 d ≤ λ/2（默认半波长，防栅瓣）

核心接口：
- MusicDOA              : MUSIC 谱估计器（ULA）
- simulate_signals()    : 多源 ULA 接收信号仿真
"""

import numpy as np


class MusicDOA:
    """均匀线阵（ULA）MUSIC 测向器。

    参数：
    - n_elements: 阵元数 M（≥4 才实用；M=1-2 理论可跑但估计质量极差）
    - spacing_ratio: 阵元间距/波长（默认 0.5 = 半波长，防栅瓣）
    - fs: 采样率（归一化，默认 1.0）
    """

    def __init__(self, n_elements=4, spacing_ratio=0.5, fs=1.0):
        if n_elements < 4:
            raise ValueError(
                f"MUSIC 苛数学硬件：n_elements={n_elements} < 4，"
                "单/双阵元测向质量不可用，请使用 ≥4 阵元。"
            )
        self.M = n_elements
        self.d = spacing_ratio  # 以波长为单位
        self.fs = fs
        self.c = 1.0  # 归一化波速（波长单位）

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def steering_vector(self, theta_deg, freq=1.0):
        """导向矢量 a(theta)：均匀线阵相位差 exp(-j*2π*d*sinθ*f/c)。

        返回 M×1 复数列向量。
        """
        theta = np.deg2rad(theta_deg)
        k = 2 * np.pi * self.d * np.sin(theta)  # 波长归一相位差
        return np.exp(-1j * k * np.arange(self.M))

    # ------------------------------------------------------------------ #
    # 核心 API
    # ------------------------------------------------------------------ #
    def estimate(self, X, n_sources=1, theta_range=(-90, 90), n_points=721):
        """MUSIC 空间谱扫描。

        参数：
        - X: 接收信号 M×N 复数快拍矩阵（M 阵元，N 快拍）
        - n_sources: 信号源数 D（必须 < M）
        - theta_range: 扫描角度范围（度）
        - n_points: 扫描网格点数

        返回：(theta_grid, spectrum) — 角度网格 + 空间谱（线性尺度）
        """
        M, N = X.shape
        if n_sources >= M:
            raise ValueError(f"n_sources={n_sources} 必须小于阵元数 M={M}")

        # 1. 样本协方差 R = XX^H / N
        R = X @ X.conj().T / N

        # 2. 特征分解（升序特征值）
        eigvals, eigvecs = np.linalg.eigh(R)

        # 3. 噪声子空间 = 最小的 (M - n_sources) 个特征向量
        noise = eigvecs[:, : M - n_sources]

        # 4. 空间谱扫描 P(θ) = 1 / (a^H En En^H a)
        grid = np.linspace(theta_range[0], theta_range[1], n_points)
        spectrum = np.zeros(n_points, dtype=float)
        for i, th in enumerate(grid):
            a = self.steering_vector(th)
            # MUSIC 伪谱（分母有保护项避免奇点）
            denom = np.abs(a.conj() @ noise @ noise.conj().T @ a) + 1e-12
            spectrum[i] = 1.0 / denom

        return grid, spectrum

    def doa(self, X, n_sources=1, theta_range=(-90, 90)):
        """返回估计方向角度列表（度）。

        流程：estimate() → 找 top-k 谱峰 → 抛物线插值细化。
        """
        grid, spec = self.estimate(X, n_sources, theta_range)

        # 找前 n_sources*3 个候选峰（宽松海选）
        idx = np.argsort(spec)[::-1][: n_sources * 3]

        # 去重：相邻 2° 内只保留最强峰
        peaks = []
        for i in sorted(idx, key=lambda i: -spec[i]):
            if all(abs(grid[i] - p) > 2.0 for p in peaks):
                peaks.append(grid[i])
            if len(peaks) >= n_sources:
                break

        # 抛物线插值细化（网格量化突破）
        # 先把角度值转为网格索引，再传给 _parabolic_refine
        peak_bin_indices = [int(np.searchsorted(grid, p)) for p in peaks]
        refined = self._parabolic_refine(spec, grid, peak_bin_indices)
        return refined

    def _parabolic_refine(self, spectrum, grid, peak_bin_indices):
        """对每个峰做抛物线插值细化，返回细化后角度（度）。

        peak_bin_indices: 整数索引列表，指向 spectrum/grid 中的峰位置。
        """
        h = float(grid[1] - grid[0]) if len(grid) > 1 else 0.0
        n = len(spectrum)
        refined = []
        for i in peak_bin_indices:
            i = int(i)
            if h <= 0 or i <= 0 or i >= n - 1:
                refined.append(float(grid[i]) if i < n else 0.0)
                continue
            y0, y1, y2 = float(spectrum[i - 1]), float(spectrum[i]), float(spectrum[i + 1])
            denom = y0 - 2.0 * y1 + y2
            if abs(denom) < 1e-30:
                refined.append(float(grid[i]))
                continue
            delta = np.clip(0.5 * (y0 - y2) / denom, -0.5, 0.5)
            refined.append(float(grid[i]) + delta * h)
        return refined


# --------------------------------------------------------------------------- #
# 信号仿真（测试/评估用）
# --------------------------------------------------------------------------- #
def simulate_signals(true_doas_deg, M=4, N=256, snr_db=20, seed=42):
    """生成多信源 ULA 接收信号。

    模型：X = Σ a(θ_i)·s_i + N
    - a(θ): 导向矢量（M×1）
    - s_i: 第 i 源复圆对称高斯（单位功率）
    - N: 加性复高斯噪声（功率按 snr_db 缩放）

    参数：
    - true_doas_deg: 信源方向列表（度）
    - M: 阵元数（默认 4）
    - N: 快拍数（默认 256）
    - snr_db: 信噪比（dB，默认 20）
    - seed: 随机种子

    返回：M×N 复数快拍矩阵
    """
    rng = np.random.default_rng(seed)
    doa = MusicDOA(n_elements=M)
    X = np.zeros((M, N), dtype=complex)

    for th in true_doas_deg:
        a = doa.steering_vector(th)
        s = (rng.standard_normal(N) + 1j * rng.standard_normal(N)) / np.sqrt(2)
        X += np.outer(a, s)

    # 加噪声
    noise_pwr = 10.0 ** (-snr_db / 10.0)
    X += np.sqrt(noise_pwr / 2) * (
        rng.standard_normal((M, N)) + 1j * rng.standard_normal((M, N))
    )
    return X


# --------------------------------------------------------------------------- #
# 自测入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    doa = MusicDOA(n_elements=4)
    for case in ([10.0], [-30.0, 25.0]):
        X = simulate_signals(case, M=4)
        est = doa.doa(X, n_sources=len(case))
        print(f"真实: {case}° → 估计: {[round(e, 1) for e in est]}°")
        errs = [abs(e - t) for e, t in zip(sorted(est), sorted(case))]
        assert max(errs) < 2.0, f"误差过大 {errs}"
    print("PASS: 单源/双源测向误差 < 2°")
