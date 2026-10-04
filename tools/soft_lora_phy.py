"""W71-08/02 · 软 LoRa PHY 原型（吞入自 gr-lora_sdr / meshtastic_sdr 思路）。

LoRa 调制：一个符号 = 一条线性调频 chirp，起始频率编码符号值 S∈[0,2^SF)。
  基 up-chirp 瞬时频率从 -BW/2 线性扫到 +BW/2；符号 S 的 chirp = 基 chirp 循环移位 S 个采样。
  解调 = 乘基 down-chirp（dechirp）→ 得单频 tone → FFT 峰值 bin 即符号值。

本原型自研实现 LoRa chirp 生成/解调（软 PHY，可作 LoRaCanary 硬件行为的对照验证台）。
纯 numpy。
"""
from __future__ import annotations

import numpy as np


def generate_symbol(symbol: int, sf: int, bw: float) -> np.ndarray:
    """生成符号 symbol 的 chirp（n=2^SF 个复数采样）。"""
    n = 2 ** sf
    t = np.arange(n) / bw                       # 采样时刻，符号时长 T = n/bw
    k = bw / (n / bw)                           # chirp rate = BW²/2^SF (Hz/s)
    phase = 2.0 * np.pi * (-bw / 2.0 * t + k / 2.0 * t ** 2)
    base = np.exp(1j * phase)                   # 基 up-chirp
    return np.roll(base, symbol)                # 符号 S = 循环移位


def demodulate(sig: np.ndarray, sf: int, bw: float) -> int:
    """解调：dechirp + FFT 峰值 → 符号值。"""
    n = 2 ** sf
    t = np.arange(n) / bw
    k = bw / (n / bw)
    phase = 2.0 * np.pi * (-bw / 2.0 * t + k / 2.0 * t ** 2)
    base_down = np.exp(-1j * phase)             # 基 down-chirp（up-chirp 共轭）
    dechirped = sig * base_down
    spec = np.abs(np.fft.fft(dechirped))
    # 前向循环移位使 dechirp 后为负频率 tone（峰在 N-S），取 (N-peak)%N 还原符号
    return int((n - np.argmax(spec)) % n)


def run_demo() -> None:
    sf, bw = 7, 125e3
    for s in [0, 1, 37, 127]:
        sig = generate_symbol(s, sf, bw)
        got = demodulate(sig, sf, bw)
        print(f"[W71-08] 符号 {s:3d} → 解调 {got:3d}  {'✓' if s == got else '✗'}")


if __name__ == "__main__":
    run_demo()
