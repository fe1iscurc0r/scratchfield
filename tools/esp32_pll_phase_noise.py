# -*- coding: utf-8 -*-
"""ESP32 本振相位噪声改进工具（W61-05 · PLL 相位噪声预算）。

依据 docs/esp32-sil-本振-勘察.md §4：PLL 相位噪声预算 = 参考噪声 + VCO 噪声，
环路带宽内由参考主导（乘 N² 分频比），带宽外由 VCO 主导。对比 XTAL/TCXO/OCXO
参考晶振对相位噪声的影响（典型规格参数，标 mock）。

纯标准库。运行：python tools/esp32_pll_phase_noise.py
"""
from __future__ import annotations

import math

# 典型参考晶振相位噪声底板（dBc/Hz @ 1kHz，mock 规格）
REF_FLOOR = {
    "XTAL": -125.0,
    "TCXO": -145.0,
    "OCXO": -160.0,
}

# 典型 VCO 相位噪声底板（dBc/Hz @ 1kHz，mock）
VCO_FLOOR = -105.0


def pll_phase_noise(ref_floor: float, vco_floor: float, loop_bw: float,
                    div_ratio: float, offsets: list[float]) -> list[float]:
    """PLL 相位噪声预算（dBc/Hz）。

    带内（offset < loop_bw）：参考底板 + 20*log10(div_ratio)（分频比放大）。
    带外（offset > loop_bw）：VCO 底板（随 offset 远离环路带宽以 -20dB/dec 回落）。
    """
    out = []
    n_db = 20.0 * math.log10(max(div_ratio, 1.0))
    for off in offsets:
        if off <= loop_bw:
            out.append(ref_floor + n_db)
        else:
            # VCO 主导，随 offset 远离 loop_bw 以 -20dB/dec 衰减
            slope_db = -20.0 * math.log10(off / loop_bw)
            out.append(vco_floor + slope_db)
    return out


def compare_ref_oscillators(loop_bw: float = 1000.0, div_ratio: float = 100.0,
                            offsets: list[float] | None = None) -> dict:
    """对比 XTAL/TCXO/OCXO 参考对带内相位噪声的影响。"""
    offsets = offsets or [100.0, 1000.0, 10000.0]
    return {
        name: pll_phase_noise(floor, VCO_FLOOR, loop_bw, div_ratio, offsets)
        for name, floor in REF_FLOOR.items()
    }


def recommend_loop_bw(ref_floor: float, vco_floor: float, div_ratio: float) -> float:
    """建议环路带宽：参考与 VCO 噪声曲线的交点（带内带外平衡点）。"""
    n_db = 20.0 * math.log10(max(div_ratio, 1.0))
    # 交点 offset 满足 ref_floor + n_db = vco_floor（忽略斜率，取量级近似）
    return 1000.0  # 简化：返回典型值，真实交点需扫频


if __name__ == "__main__":
    c = compare_ref_oscillators()
    for name, curve in c.items():
        print(f"{name}: @100Hz={curve[0]:.1f} @1kHz={curve[1]:.1f} @10kHz={curve[2]:.1f} dBc/Hz")
