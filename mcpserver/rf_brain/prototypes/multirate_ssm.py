"""R67 · 多速率 SSM 处理脉冲密度调制（最小原型）

授粉自 round3 digest-g7 Multirate SSM PDM（2608.28472）：多速率状态空间模型
端到端处理脉冲密度调制（PDM）信号——PDM 是 1-bit 高采样率的 Σ-Δ 调制比特流
（MEMS 麦克风/传感器常用），用 SSM 在比特流上直接做「滤波 + 抽取」，替代传统
CIC 抽取链，参数更少、端到端可训。

本原型（纯 numpy）：
  - pdm_modulate         连续信号 → 1-bit PDM 比特流（Σ-Δ 调制）
  - MultirateSSM         多速率状态空间模型：快状态跟踪 PDM 位、慢状态抽取输出
  - naive_decimate       boxcar 平均抽取（基线对照）
  - demo                 重建 SNR 对比（SSM vs 朴素抽取）

这是最小原型（评估可行性），参数/精度/内存预算见 docs/multirate-ssm-esp32-评估.md。
"""
from __future__ import annotations

import numpy as np

__all__ = ["pdm_modulate", "naive_decimate", "MultirateSSM", "recon_snr_db"]


def pdm_modulate(x: np.ndarray, *, seed: int = 0) -> np.ndarray:
    """一阶 Σ-Δ 调制：连续信号 → 1-bit PDM 比特流（±1）。"""
    x = np.asarray(x, dtype=float)
    acc = 0.0
    out = np.empty(x.size, dtype=np.int8)
    for i, v in enumerate(x):
        acc += v
        b = 1 if acc >= 0.0 else -1
        out[i] = b
        acc -= b
    return out


def naive_decimate(bits: np.ndarray, ratio: int) -> np.ndarray:
    """朴素 boxcar 平均抽取（基线）：每 ratio 个 PDM 位取均值。"""
    b = np.asarray(bits, dtype=float)
    n = b.size // ratio
    return b[: n * ratio].reshape(n, ratio).mean(axis=1)


class MultirateSSM:
    """一阶状态空间模型做 PDM 滤波 + 抽取（多速率：输入高速、输出降采样）。

    状态方程 x_{t+1} = a·x_t + b·u_t，输出 y_t = c·x_t（u_t 为 ±1 PDM 位）——
    这是一阶低通 IIR（指数滑动平均）的 SSM 形式，每 ratio 步采样一次慢速输出。
    参数量 = a+b+c = 3（极轻量），每步 1 次乘加（定点下为移位+加法）。
    """

    def __init__(self, ratio: int = 16, *, f_c: float | None = None) -> None:
        if ratio < 1:
            raise ValueError("ratio 必须 >= 1")
        self.ratio = int(ratio)
        # 一阶低通系数：α=1/ratio 使时间常数 ≈ 抽取窗长（截止 ≈ 抽取后 Nyquist 内）
        alpha = float(f_c) if f_c is not None else 1.0 / ratio
        self.a = 1.0 - alpha
        self.b = alpha
        self.c = 1.0

    def process(self, bits: np.ndarray) -> np.ndarray:
        """PDM 比特流 → 降采样 PCM（每 ratio 步输出一次）。"""
        b = np.asarray(bits, dtype=float)
        x = 0.0
        outs = []
        for i, u in enumerate(b):
            x = self.a * x + self.b * u
            if (i + 1) % self.ratio == 0:
                outs.append(float(self.c * x))
        return np.array(outs)


def recon_snr_db(recon: np.ndarray, ref: np.ndarray) -> float:
    """重建 SNR（dB）：P(ref)/P(残差)。"""
    r = np.asarray(recon, dtype=float)
    t = np.asarray(ref, dtype=float)
    m = min(r.size, t.size)
    sp = float(np.mean(t[:m] ** 2))
    rp = float(np.mean((r[:m] - t[:m]) ** 2))
    return 10.0 * np.log10(sp / rp + 1e-12)


def demo() -> None:
    n, ratio = 4096, 16
    t = np.arange(n) / n
    sig = 0.5 * np.sin(2.0 * np.pi * 0.02 * np.arange(n))
    bits = pdm_modulate(sig, seed=0)
    naive = naive_decimate(bits, ratio)
    ssm = MultirateSSM(ratio=ratio).process(bits)
    ref = sig[: len(naive) * ratio: ratio]
    print(f"naive 抽取 SNR = {recon_snr_db(naive, ref):.1f} dB")
    print(f"multirate SSM SNR = {recon_snr_db(ssm, ref):.1f} dB")


if __name__ == "__main__":
    demo()
