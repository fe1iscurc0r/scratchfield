"""W71-05 · 卫星链路预算 / 多普勒 / 路径损耗原型（吞入自 SatNOGS/gr-leo 思路）。

gr-leo 的核心：卫星-地面站信道的多普勒频移、自由空间路径损耗、链路预算。
本原型用纯 Python 实现这三段，供 radio_brain 的「卫星过境 + 链路预算」模块预演。

公式：
  多普勒 f_d = f_c · v_rel / c（逼近为正，远离为负）
  自由空间损耗 L(dB) = 20·log10(4π d f / c)
  接收功率 P_r = P_t + G_t + G_r - L
  信噪比 SNR = P_r - P_noise（dB 域）
纯标准库。
"""
from __future__ import annotations

import math

C = 3e8  # 光速 m/s


def doppler_shift(f_carrier: float, v_rel: float) -> float:
    """多普勒频移（Hz）：v_rel 为相对速度（m/s，逼近为正）。"""
    return f_carrier * v_rel / C


def free_space_loss(distance_m: float, freq_hz: float) -> float:
    """自由空间路径损耗（dB）。"""
    return 20.0 * math.log10(4.0 * math.pi * distance_m * freq_hz / C)


def received_power(tx_dbm: float, tx_gain_db: float, rx_gain_db: float,
                   distance_m: float, freq_hz: float) -> float:
    """接收功率（dBm）：P_r = P_t + G_t + G_r - L。"""
    return tx_dbm + tx_gain_db + rx_gain_db - free_space_loss(distance_m, freq_hz)


def snr_db(rx_dbm: float, noise_floor_dbm: float) -> float:
    """信噪比（dB）。"""
    return rx_dbm - noise_floor_dbm


def run_demo() -> None:
    f = 137.5e6        # NOAA APT 137.5 MHz
    v = 7500.0         # 近地卫星相对速度 ~7.5 km/s
    d = 800e3          # 过顶距离 ~800 km
    fd = doppler_shift(f, v)
    rx = received_power(tx_dbm=5, tx_gain_db=2, rx_gain_db=10, distance_m=d, freq_hz=f)
    print(f"[W71-05] 多普勒频移: {fd/1e3:.2f} kHz（f={f/1e6}MHz v={v/1e3}km/s）")
    print(f"[W71-05] 路径损耗: {free_space_loss(d, f):.1f} dB")
    print(f"[W71-05] 接收功率: {rx:.1f} dBm ｜ SNR: {snr_db(rx, -120):.1f} dB")


if __name__ == "__main__":
    run_demo()
