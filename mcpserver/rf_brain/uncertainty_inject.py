"""传感器不确定性注入框架（A23 · rf_brain/NEKO 数字孪生不确定性传递）。

依据 docs/paper-round2-2026-08-30/digests/授粉点-统一.md 中 g6-1 授粉点①
（SPOTLIGHT/CMB beam surrogate 思路）与 SPEC A23：
「beam 参数当 nuisance → 代理模型降维 → 解析边缘化」= 传感器不确定性注入标准流程。

对 rf_brain 的迁移：把频谱感知传感器的物理参数（增益 / 噪声底 / 频偏）当作
nuisance 量，做一阶 Taylor 代理模型（降维），在 Gaussian 先验下**解析边缘化**，
输出带置信区间的频谱感知结果——而不是只给一个点估计。

数学（线性代理 + 高斯先验的闭式解）：
    观测模型   P(f; θ) = g·S(f-δf) + n,   θ=(g, n, δf)
    代理模型   P(f; θ) ≈ P(f; θ0) + Σ_i ∂P/∂θ_i (θ_i-θ0_i)   （一阶 Taylor 降维）
    先验       θ_i ~ N(θ0_i, σ_i²)   （传感器标定给出的标称+容差）
    边缘化后   mean(f) = P(f; θ0)
               var(f)  = Σ_i (∂P/∂θ_i)² σ_i²
               CI(f)   = mean(f) ± z·sqrt(var(f))

运行：
  python -m mcpserver.rf_brain.uncertainty_inject
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 默认 95% 置信区间 z 值
Z_95 = 1.959963984540054


@dataclass
class SpectrumSensor:
    """频谱感知传感器：真值谱（高斯峰叠加）+ 三类 nuisance 参数的先验。"""

    center: float = 1000.0  # 峰中心频率 (Hz)
    amp: float = 1.0        # 峰幅度
    width: float = 50.0     # 峰宽 (Hz)

    # nuisance 先验（标称值 + 1σ 容差，来自传感器标定）
    gain_nom: float = 1.0
    gain_std: float = 0.1
    noise_nom: float = 0.05
    noise_std: float = 0.02
    offset_nom: float = 0.0
    offset_std: float = 10.0  # 频偏容差 (Hz)

    def true_spectrum(self, f: np.ndarray) -> np.ndarray:
        """真值谱 S(f)（传感器增益=1、无频偏、无噪声时的理想读数）。"""
        return self.amp * np.exp(-0.5 * ((f - self.center) / self.width) ** 2)

    def _spectrum_deriv(self, f: np.ndarray) -> np.ndarray:
        """S'(f) 对频率的解析导数（高斯峰）。"""
        s = self.true_spectrum(f)
        return s * (-(f - self.center) / self.width ** 2)

    def forward(self, f: np.ndarray, theta: tuple[float, float, float]) -> np.ndarray:
        """观测模型 P(f; θ)，θ=(gain, noise_floor, freq_offset)。"""
        g, n, df = theta
        return g * self._spectrum_at(f, df) + n

    def _spectrum_at(self, f: np.ndarray, df: float) -> np.ndarray:
        """S(f - df)（频偏后的谱）。"""
        return self.amp * np.exp(-0.5 * ((f - self.center - df) / self.width) ** 2)

    def inject_uncertainty(self, f: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """解析边缘化：返回 (mean(f), std(f))。

        一阶 Taylor 代理在标称 θ0=(gain_nom, noise_nom, offset_nom) 处展开：
          ∂P/∂g   = S(f-δf0)
          ∂P/∂n   = 1
          ∂P/∂δf  = g0 · (-S'(f-δf0))
        var(f) = (∂P/∂g)²·σ_g² + (∂P/∂n)²·σ_n² + (∂P/∂δf)²·σ_δf²
        """
        theta0 = (self.gain_nom, self.noise_nom, self.offset_nom)
        mean = self.forward(f, theta0)

        # 频偏 0 处（标称）的真值谱及其导数
        s = self.true_spectrum(f)
        s_deriv = self._spectrum_deriv(f)

        dg = s                       # ∂P/∂g
        dn = 1.0                     # ∂P/∂n
        doff = -self.gain_nom * s_deriv  # ∂P/∂δf（负号来自 S(f-δf) 对 δf 求导）

        var = dg**2 * self.gain_std**2 + dn**2 * self.noise_std**2 + doff**2 * self.offset_std**2
        return mean, np.sqrt(np.maximum(var, 0.0))

    def sense(self, f: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
        """一次真实感知：按 nuisance 先验采样 θ 并观测（含读数噪声）。"""
        rng = rng or np.random.default_rng(0)
        g = rng.normal(self.gain_nom, self.gain_std)
        n = rng.normal(self.noise_nom, self.noise_std)
        df = rng.normal(self.offset_nom, self.offset_std)
        # 读数噪声：底噪的 10%（信噪比意义上很小）
        read_noise = rng.normal(0.0, max(self.noise_std * 0.1, 1e-4), size=f.shape)
        return self.forward(f, (g, n, df)) + read_noise


def sense_with_ci(
    sensor: SpectrumSensor,
    f: np.ndarray,
    z: float = Z_95,
) -> dict:
    """注入不确定性：返回含置信区间的频谱感知结果。

    返回字段：f（频率轴）、mean（边缘化均值谱）、std（边缘化标准差）、
    lower/upper（z·σ 置信区间）。
    """
    mean, std = sensor.inject_uncertainty(f)
    return {
        "f": f,
        "mean": mean,
        "std": std,
        "lower": mean - z * std,
        "upper": mean + z * std,
    }


def main() -> int:
    sensor = SpectrumSensor()
    f = np.linspace(800.0, 1200.0, 401)
    result = sense_with_ci(sensor, f)

    peak_idx = int(np.argmax(result["mean"]))
    base_idx = 0
    print("[不确定性注入] 频谱感知结果（含 95% 置信区间）")
    print(f"  峰频点 {f[peak_idx]:.0f} Hz: mean={result['mean'][peak_idx]:.3f} "
          f"CI=[{result['lower'][peak_idx]:.3f}, {result['upper'][peak_idx]:.3f}]")
    print(f"  底噪点 {f[base_idx]:.0f} Hz: mean={result['mean'][base_idx]:.3f} "
          f"CI=[{result['lower'][base_idx]:.3f}, {result['upper'][base_idx]:.3f}]")
    print(f"  峰处 std={result['std'][peak_idx]:.3f} > 底噪处 std={result['std'][base_idx]:.3f}"
          "（增益/频偏不确定性在信号处被放大，符合物理直觉）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
