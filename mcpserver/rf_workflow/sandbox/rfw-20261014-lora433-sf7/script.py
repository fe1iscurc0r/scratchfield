#!/usr/bin/env python3
"""LoRa chirp 发射功率估算器（符号时长 / ToA / 能量 / 链路预算 / 频谱占用）（rf_lib=stdlib）

由 mcpserver.rf_workflow.prompt_to_script 生成（工单242）—— **自动生成，勿手改**。
goal   : 设计一个 LoRa chirp 在 433 MHz 的发射功率估算器，给定扩频因子 7，输出功率 14 dBm
rf_lib : stdlib
真值源 : lora_phy.py（同目录 vendored 副本，字节等同 mcpserver/rf_workflow/lora_phy.py）

产物：result.json（规格 + 指标 + 频谱摘要）；stdout 末尾 __RF_METRICS__ 行供 sim_runner 解析。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPEC = {
    'bw_hz': 125000.0,
    'cable_loss_db': 0.0,
    'channel_spacing_hz': None,
    'cr': 1,
    'crc': 1,
    'freq_hz': 433000000.0,
    'implicit_header': False,
    'kind': 'lora_chirp_power_estimator',
    'low_data_rate_optimize': None,
    'payload_bytes': 16,
    'preamble_symbols': 8,
    'rx_antenna_gain_dbi': 0.0,
    'sample_rate_hz': 250000.0,
    'sf': 7,
    'spectrum_symbols': 1,
    'target_distance_m': 1000.0,
    'tx_antenna_gain_dbi': 0.0,
    'tx_period_s': 60.0,
    'tx_power_dbm': 14.0,
}
RF_LIB = "stdlib"
RESULT_FILENAME = "result.json"

from lora_phy import compute_metrics, occupied_bandwidth_hz, spectrum_db, synth_chirp_iq


def numpy_spectrum_cross_check(metrics):
    """rf_lib=numpy 时用 numpy.fft 独立复算 -6 dB 带宽，与标准库 FFT 结果对拍。"""
    if RF_LIB != "numpy":
        return {"backend": "stdlib", "note": "rf_lib=stdlib，仅用标准库 FFT"}
    try:
        import numpy as np
    except Exception as exc:  # numpy 缺失 → 显式降级，不静默
        return {"backend": "stdlib(FALLBACK)", "note": "numpy 不可用：%s" % exc}
    samples = synth_chirp_iq(int(SPEC["sf"]), float(SPEC["bw_hz"]),
                             float(SPEC["sample_rate_hz"]),
                             symbols=int(SPEC.get("spectrum_symbols", 1)))
    data = np.asarray(samples, dtype=np.complex128)
    n = 1
    while n < len(data) * 4:
        n <<= 1
    spec = np.fft.fftshift(np.fft.fft(data, n))
    mag = 20.0 * np.log10(np.maximum(np.abs(spec), 1e-12) / float(np.max(np.abs(spec))))
    freqs = (np.arange(n) - n // 2) * float(SPEC["sample_rate_hz"]) / n
    inside = freqs[mag >= float(np.max(mag)) - 6.0]
    obw6 = float(inside.max() - inside.min())
    reference = float(metrics["occupied_bw_6db_hz"])
    return {"backend": "numpy", "bins": int(n),
            "occupied_bw_6db_hz": round(obw6, 1),
            "delta_vs_stdlib_hz": round(obw6 - reference, 1),
            "agrees_within_5pct": abs(obw6 - reference) <= 0.05 * reference}


def main():
    metrics = compute_metrics(SPEC)
    samples = synth_chirp_iq(int(SPEC["sf"]), float(SPEC["bw_hz"]),
                             float(SPEC["sample_rate_hz"]),
                             symbols=int(SPEC.get("spectrum_symbols", 1)))
    freqs, mags = spectrum_db(samples, float(SPEC["sample_rate_hz"]))
    peak_index = max(range(len(mags)), key=lambda i: mags[i])

    payload = {
        "spec": SPEC,
        "rf_lib": RF_LIB,
        "metrics": metrics,
        "spectrum": {
            "bins": len(freqs),
            "peak_freq_hz": round(freqs[peak_index], 1),
            "peak_freq_relative_to_bw": round(freqs[peak_index] / float(SPEC["bw_hz"]), 4),
            "occupied_bw_6db_hz": round(occupied_bandwidth_hz(freqs, mags, drop_db=-6.0), 1),
            "occupied_bw_99pct_hz": round(
                occupied_bandwidth_hz(freqs, mags, energy_fraction=0.99), 1),
        },
        "numpy_cross_check": numpy_spectrum_cross_check(metrics),
    }
    Path(RESULT_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8", newline="\n")

    print("=== LoRa chirp 发射功率估算器（工单242 PoC）===")
    print("频率            : %s MHz" % metrics["freq_mhz"])
    print("SF / BW / CR    : SF%s / %s kHz / %s" % (metrics["sf"], metrics["bw_khz"],
                                                    metrics["cr_ratio"]))
    print("发射功率        : %s dBm (%s mW)" % (metrics["tx_power_dbm"],
                                                metrics["tx_power_mw"]))
    print("符号时长 / chirp: %s ms / %s MHz/s" % (metrics["symbol_duration_ms"],
                                                  metrics["chirp_rate_mhz_s"]))
    print("空中时间 ToA    : %s ms（前导 %s + 载荷 %s）" % (
        metrics["time_on_air_ms"], metrics["preamble_duration_ms"],
        metrics["payload_duration_ms"]))
    print("标称 / 有效速率 : %s / %s bps" % (metrics["nominal_bitrate_bps"],
                                              metrics["airtime_bitrate_bps"]))
    print("每比特能量      : %s uJ" % metrics["energy_per_bit_uj"])
    print("灵敏度 / 余量   : %s dBm / %s dB（@%s m）" % (
        metrics["sensitivity_dbm"], metrics["link_margin_db"], metrics["distance_m"]))
    print("占用带宽 -6dB   : %s Hz（%.1f%% of BW）" % (
        metrics["occupied_bw_6db_hz"], metrics["bandwidth_utilisation_pct"]))
    print("占空比          : %s%%（限值 %s%%）" % (metrics["duty_cycle_pct"],
                                                  metrics["duty_cycle_limit_pct"]))
    print("结果文件        : %s" % RESULT_FILENAME)
    print("__RF_METRICS__ " + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
