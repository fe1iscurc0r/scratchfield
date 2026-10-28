"""LoRa 物理层数值（工单242）—— **纯标准库**，脚本与解释器的唯一真值源。

本模块是三件事的交汇点：

1. **公式**：Semtech AN1200.13 的 payload 符号数/空中时间（ToA）公式、符号时长、
   chirp 速率、码片速率、能量、链路预算（自由空间）；
2. **数值口径**：灵敏度/SNR 极限取 SX1276/77/78 数据手册 BW=125 kHz 典型值；
   占空比与 ERP 限值取 ISM 频段法规上限（**需按部署地复核**，见 README）；
3. **可执行**：``python -m mcpserver.rf_workflow.lora_phy --sf 7 --power-dbm 14``
   直接打印 JSON 指标；沙箱脚本按字节**原样 vendor 本文件**，故不存在公式漂移
   （``tests/test_rf_workflow.py::test_generate_writes_self_contained_sandbox`` 与
   ``::test_full_workflow_poc_produces_four_artifacts`` 断言副本与真值源字节相同）。

关于「LoRa 到底是仿真还是算公式」：本模块不假装做电磁仿真——它做的是**链路预算与
位级能量核算**（LoRa PHY 的标准工程算法），并用一段真实合成的 chirp 复数序列做
FFT 得到**占用带宽**。凡是不能真算的量（例如某地实测路损、天线增益）一律不编造，
改为显式输入参数或标注「需实测」。
"""
from __future__ import annotations

import argparse
import cmath
import json
import math
from typing import Any

SPEED_OF_LIGHT_M_S = 299_792_458.0

# ---- 取值域 ----
SF_MIN, SF_MAX = 6, 12
CR_CHOICES = (1, 2, 3, 4)          # CR = 4/(4+cr) → 4/5, 4/6, 4/7, 4/8

# ---- Semtech AN1200.13 payload 符号数公式里的常数 ----
HEADER_BITS = 28                   # 显式包头 28 bit
CRC_BITS = 16
IMPLICIT_HEADER_BITS = 20          # 隐式头时公式里 -20*IH
PREAMBLE_SYMBOLS_DEFAULT = 8
PREAMBLE_OVERHEAD_SYMBOLS = 4.25   # ToA = (n_preamble + 4.25) * Tsym
DEFAULT_PAYLOAD_BYTES = 16

# ---- SX1276/77/78 数据手册典型值（BW = 125 kHz，Table 20/21）----
SENSITIVITY_DBM_BW125: dict[int, float] = {
    6: -118.0, 7: -123.0, 8: -126.0, 9: -129.0,
    10: -132.0, 11: -134.5, 12: -137.0,
}
SNR_LIMIT_DB_BW125: dict[int, float] = {
    6: -5.0, 7: -7.5, 8: -10.0, 9: -12.5,
    10: -15.0, 11: -17.5, 12: -20.0,
}
SENSITIVITY_REF_BW_KHZ = 125.0

# ---- 法规/工程口径（**需按部署地复核**）----
ISM_433_RANGE_HZ = (433.05e6, 434.79e6)   # 433 ISM 子带（固件 dcp_lora 取中心 433.92 MHz）
DUTY_CYCLE_LIMIT_PCT = 10.0        # ERC/REC 70-03 Annex 1（433.05–434.79 MHz）≤10%
ERP_LIMIT_DBM = 10.0               # MIIT 微功率短距离：433.05–434.79 MHz ≤10 mW ERP
DIPOLE_TO_ISOTROPIC_DB = 2.15      # ERP(dipole) = EIRP(isotropic) − 2.15 dB
REGULATORY_NOTE = (
    "限值按 433.05–434.79 MHz ISM 子带（ERC/REC 70-03 Annex 1 / MIIT 微功率短距离目录）"
    "填写，部署前须按实际落地地区与天线型式复核。"
)

DEFAULT_SPEC: dict[str, Any] = {
    "kind": "lora_chirp_power_estimator",
    "freq_hz": 433.92e6,
    "bw_hz": 125e3,
    "sf": 7,
    "cr": 1,                       # 4/5
    "tx_power_dbm": 14.0,
    "payload_bytes": DEFAULT_PAYLOAD_BYTES,
    "crc": 1,
    "implicit_header": False,
    "preamble_symbols": PREAMBLE_SYMBOLS_DEFAULT,
    "low_data_rate_optimize": None,   # None = 按 Semtech 建议自动（SF11/12 且 BW125 → 开）
    "channel_spacing_hz": None,       # None = 等于 bw_hz
    "tx_period_s": 60.0,
    "target_distance_m": 1000.0,
    "tx_antenna_gain_dbi": 0.0,
    "rx_antenna_gain_dbi": 0.0,
    "cable_loss_db": 0.0,
    "sample_rate_hz": 250e3,
    "spectrum_symbols": 1,
}


# ---------------------------------------------------------------------------
# 基础换算
# ---------------------------------------------------------------------------
def dbm_to_mw(power_dbm: float) -> float:
    """dBm → mW（``P_mW = 10 ** (P_dBm / 10)``）。"""
    return float(10.0 ** (float(power_dbm) / 10.0))


def mw_to_dbm(power_mw: float) -> float:
    """mW → dBm；非正值抛 ``ValueError``（对数域无定义，不返回 ``-inf`` 糊弄）。"""
    value = float(power_mw)
    if value <= 0:
        raise ValueError(f"功率必须为正数（mW），收到 {power_mw!r}")
    return 10.0 * math.log10(value)


# ---------------------------------------------------------------------------
# 时间 / 速率
# ---------------------------------------------------------------------------
def symbol_duration_s(sf: int, bw_hz: float) -> float:
    """符号时长 ``Tsym = 2**SF / BW``（秒）。SF7/BW125k → 1.024 ms。"""
    return (2 ** int(sf)) / float(bw_hz)


def symbol_rate_symbols_per_s(sf: int, bw_hz: float) -> float:
    """符号率 ``Rs = BW / 2**SF``。"""
    return float(bw_hz) / (2 ** int(sf))


def chip_rate_chips_per_s(bw_hz: float) -> float:
    """LoRa 码片率 = 调制带宽（1 chip = 1 Hz 的扫频）。"""
    return float(bw_hz)


def chirp_rate_hz_per_s(sf: int, bw_hz: float) -> float:
    """chirp 扫频斜率 ``k = BW / Tsym = BW**2 / 2**SF``（Hz/s）。"""
    return float(bw_hz) / symbol_duration_s(sf, bw_hz)


def low_data_rate_optimize(sf: int, bw_hz: float) -> int:
    """Semtech 建议：SF11/SF12 且 BW ≤ 125 kHz 时开低速率优化（DE=1）。"""
    return 1 if (int(sf) >= 11 and float(bw_hz) <= SENSITIVITY_REF_BW_KHZ * 1000) else 0


def payload_symbol_count(sf: int, payload_bytes: int, *, cr: int = 1, crc: int = 1,
                         implicit_header: bool = False, de: int = 0) -> int:
    """Semtech AN1200.13：``8 + max(ceil((8*PL - 4*SF + 28 + 16*CRC - 20*IH) / (4*(SF-2*DE))) * (CR+4), 0)``。"""
    denominator = 4 * (int(sf) - 2 * int(de))
    if denominator <= 0:
        raise ValueError(f"非法 SF/DE 组合: sf={sf} de={de}")
    numerator = (8 * int(payload_bytes) - 4 * int(sf) + HEADER_BITS
                 + CRC_BITS * int(crc) - IMPLICIT_HEADER_BITS * (1 if implicit_header else 0))
    coded = math.ceil(numerator / denominator) * (int(cr) + 4)
    return 8 + max(coded, 0)


def time_on_air_s(sf: int, bw_hz: float, payload_bytes: int, *, cr: int = 1, crc: int = 1,
                  implicit_header: bool = False, preamble_symbols: int = PREAMBLE_SYMBOLS_DEFAULT,
                  de: int | None = None) -> float:
    """空中时间 ``ToA = Tpreamble + Tpayload``（秒）。

    ``de=None`` 时按 :func:`low_data_rate_optimize` 自动判定。
    """
    de_value = low_data_rate_optimize(sf, bw_hz) if de is None else int(de)
    tsym = symbol_duration_s(sf, bw_hz)
    preamble = (int(preamble_symbols) + PREAMBLE_OVERHEAD_SYMBOLS) * tsym
    payload = payload_symbol_count(sf, payload_bytes, cr=cr, crc=crc,
                                   implicit_header=implicit_header, de=de_value) * tsym
    return preamble + payload


def nominal_bitrate_bps(sf: int, bw_hz: float, *, cr: int = 1) -> float:
    """标称比特率 ``Rb = SF * (BW / 2**SF) * 4/(4+CR)``。SF7/BW125k/4-5 → 5468.75 bps。"""
    return int(sf) * symbol_rate_symbols_per_s(sf, bw_hz) * (4.0 / (4.0 + int(cr)))


def airtime_bitrate_bps(payload_bytes: int, toa_s: float) -> float:
    """含前导码/包头开销的实际有效比特率（payload bit / 总空中时间）。"""
    if toa_s <= 0:
        raise ValueError("ToA 必须为正数")
    return (8.0 * int(payload_bytes)) / float(toa_s)


# ---------------------------------------------------------------------------
# 能量
# ---------------------------------------------------------------------------
def energy_per_symbol_j(tx_power_dbm: float, sf: int, bw_hz: float) -> float:
    """单符号辐射能量 ``E_sym = P * Tsym``（焦耳）。"""
    return dbm_to_mw(tx_power_dbm) * 1e-3 * symbol_duration_s(sf, bw_hz)


def energy_per_bit_j(tx_power_dbm: float, toa_s: float, payload_bytes: int) -> float:
    """每载荷比特能量 ``E_b = P * ToA / (8 * payload_bytes)``（焦耳）。"""
    return dbm_to_mw(tx_power_dbm) * 1e-3 * float(toa_s) / (8.0 * int(payload_bytes))


# ---------------------------------------------------------------------------
# 链路预算
# ---------------------------------------------------------------------------
def free_space_path_loss_db(freq_hz: float, distance_m: float) -> float:
    """自由空间路损（FSPL）：``20log10(d) + 20log10(f) - 147.55``（d 米、f 赫兹）。"""
    if distance_m <= 0:
        raise ValueError("距离必须为正数")
    return 20.0 * math.log10(float(distance_m)) + 20.0 * math.log10(float(freq_hz)) - 147.55


def sensitivity_dbm(sf: int, bw_hz: float) -> float:
    """接收灵敏度（dBm）：以 BW=125 kHz 手册表为基准，按 ``10*log10(BW/125k)`` 做热噪声缩放。

    ⚠️ 这是**工程近似**（真实灵敏度还含实现损耗与调制损耗），报告里一律标注。
    """
    base = SENSITIVITY_DBM_BW125.get(int(sf))
    if base is None:
        raise ValueError(f"SF 超出 {SF_MIN}~{SF_MAX}: {sf}")
    return base + 10.0 * math.log10(float(bw_hz) / (SENSITIVITY_REF_BW_KHZ * 1000))


def snr_limit_db(sf: int) -> float:
    """解调所需最小 SNR（dB，BW=125 kHz 手册值；与带宽无关）。"""
    value = SNR_LIMIT_DB_BW125.get(int(sf))
    if value is None:
        raise ValueError(f"SF 超出 {SF_MIN}~{SF_MAX}: {sf}")
    return value


def max_free_space_range_m(tx_power_dbm: float, freq_hz: float, rx_sensitivity_dbm: float, *,
                           tx_gain_dbi: float = 0.0, rx_gain_dbi: float = 0.0,
                           loss_db: float = 0.0) -> float:
    """链路余量为 0 时的**自由空间**距离上限（米）。这是理论上限，不含地物/多径/衰落。"""
    budget_db = (float(tx_power_dbm) + float(tx_gain_dbi) + float(rx_gain_dbi)
                 - float(loss_db) - float(rx_sensitivity_dbm))
    exponent = (budget_db + 147.55 - 20.0 * math.log10(float(freq_hz))) / 20.0
    return 10.0 ** exponent


def in_ism_433(freq_hz: float) -> bool:
    """频率是否落在 433.05–434.79 MHz ISM 子带内（含端点）。"""
    low, high = ISM_433_RANGE_HZ
    return low <= float(freq_hz) <= high


def eirp_dbm(tx_power_dbm: float, *, tx_gain_dbi: float = 0.0, loss_db: float = 0.0) -> float:
    """等效全向辐射功率 ``EIRP = P_conducted + G_tx − 馈线损耗``。"""
    return float(tx_power_dbm) + float(tx_gain_dbi) - float(loss_db)


def erp_dbm(tx_power_dbm: float, *, tx_gain_dbi: float = 0.0, loss_db: float = 0.0) -> float:
    """等效辐射功率（半波振子参考）``ERP = EIRP − 2.15 dB``。"""
    return eirp_dbm(tx_power_dbm, tx_gain_dbi=tx_gain_dbi, loss_db=loss_db) - DIPOLE_TO_ISOTROPIC_DB


def max_tx_power_dbm_for_erp(*, tx_gain_dbi: float = 0.0, loss_db: float = 0.0,
                             limit_dbm: float = ERP_LIMIT_DBM) -> float:
    """让 ERP 刚好等于限值所允许的**传导**发射功率（供合规化建议直接用）。"""
    return float(limit_dbm) + DIPOLE_TO_ISOTROPIC_DB - float(tx_gain_dbi) + float(loss_db)


def link_budget(spec: dict[str, Any], *, distance_m: float | None = None) -> dict[str, Any]:
    """链路预算：路损 / 接收功率 / 余量 / 自由空间距离上限。"""
    sf = int(spec["sf"])
    bw_hz = float(spec["bw_hz"])
    freq_hz = float(spec["freq_hz"])
    distance = float(spec.get("target_distance_m", 1000.0) if distance_m is None else distance_m)
    tx_gain = float(spec.get("tx_antenna_gain_dbi", 0.0))
    rx_gain = float(spec.get("rx_antenna_gain_dbi", 0.0))
    loss = float(spec.get("cable_loss_db", 0.0))
    sens = sensitivity_dbm(sf, bw_hz)
    fsl = free_space_path_loss_db(freq_hz, distance)
    rx_power = float(spec["tx_power_dbm"]) + tx_gain + rx_gain - loss - fsl
    return {
        "distance_m": distance,
        "fsl_db": round(fsl, 2),
        "rx_power_dbm": round(rx_power, 2),
        "sensitivity_dbm": round(sens, 2),
        "link_margin_db": round(rx_power - sens, 2),
        "required_snr_db": snr_limit_db(sf),
        "max_free_space_range_m": round(max_free_space_range_m(
            spec["tx_power_dbm"], freq_hz, sens,
            tx_gain_dbi=tx_gain, rx_gain_dbi=rx_gain, loss_db=loss), 1),
    }


# ---------------------------------------------------------------------------
# 频谱：真合成 chirp + FFT（纯标准库 radix-2）
# ---------------------------------------------------------------------------
def synth_chirp_iq(sf: int, bw_hz: float, sample_rate_hz: float, *, symbols: int = 1,
                   freq_offset_hz: float = 0.0) -> list[complex]:
    """合成 LoRa 基带 chirp 复数序列（单位幅度）。

    每个符号内瞬时频率从 ``-BW/2`` 线性升到 ``+BW/2``（一次完整扫频 = 1 chip/Hz），
    相位取瞬时频率的积分以保证符号内连续（真实 LoRa 的循环移频在**带宽占用**上等价）。
    """
    tsym = symbol_duration_s(sf, bw_hz)
    per_symbol = int(round(tsym * sample_rate_hz))
    if per_symbol <= 0:
        raise ValueError("采样率过低：单符号采样点数为 0")
    n_total = per_symbol * int(symbols)
    if n_total > 1 << 20:
        raise ValueError("采样点数过多（> 2**20）：降低 sample_rate_hz 或 symbols")
    slope = chirp_rate_hz_per_s(sf, bw_hz)
    dt = 1.0 / float(sample_rate_hz)
    half_bw = float(bw_hz) / 2.0
    offset = float(freq_offset_hz)
    samples: list[complex] = []
    for index in range(n_total):
        t = (index % per_symbol) * dt
        phase = 2.0 * math.pi * (-half_bw * t + 0.5 * slope * t * t + offset * t)
        samples.append(cmath.exp(1j * phase))
    return samples


def _fft_radix2(values: list[complex]) -> list[complex]:
    """就地迭代 radix-2 FFT；长度须为 2 的幂。"""
    n = len(values)
    if n & (n - 1):
        raise ValueError("FFT 长度必须是 2 的幂")
    data = list(values)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    length = 2
    while length <= n:
        angle = -2.0 * math.pi / length
        step = cmath.exp(1j * angle)
        for start in range(0, n, length):
            w = 1 + 0j
            for offset in range(length // 2):
                even = data[start + offset]
                odd = data[start + offset + length // 2] * w
                data[start + offset] = even + odd
                data[start + offset + length // 2] = even - odd
                w *= step
        length <<= 1
    return data


SPECTRUM_WINDOWS = ("hann", "rect")


def _window_weights(length: int, name: str) -> list[float]:
    if name == "rect":
        return [1.0] * length
    if name == "hann":
        return [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (length - 1)) for i in range(length)]
    raise ValueError(f"未知窗函数 {name!r}，可选 {SPECTRUM_WINDOWS}")


def spectrum_db(samples: list[complex], sample_rate_hz: float, *, window: str = "rect",
                zero_pad_to: int | None = None) -> tuple[list[float], list[float]]:
    """**双边**幅度谱（dB，归一化到峰值 0 dB）→ ``(freqs_hz, mag_db)``。

    返回双边（``-fs/2 … +fs/2``）而非单边：LoRa 基带 chirp 跨越 ``±BW/2``，
    只取正频率半边会把占用带宽算成实际值的一半（本模块首版实测踩到，见 README「踩坑」）。

    **默认不加窗（``rect``）**，这**不是**疏忽：chirp 是扫频信号，功率谱密度按
    「停留时间」加权，等时加权才给出真实的带内平坦谱；加 Hann 会按窗形调制各频点的
    停留幅度，实测把 -6 dB 带宽从 0.98·BW 压到 0.50·BW（见 README「频谱口径」）。
    补零到 ``>= 4×`` 原长只为提高读谱分辨率（单符号仅 256 点 = 977 Hz/bin）。
    """
    length = len(samples)
    if length == 0:
        raise ValueError("样本为空")
    weights = _window_weights(length, window)
    weighted = [value * weights[i] for i, value in enumerate(samples)]
    n = 1
    target = max(int(zero_pad_to or 0), length * 4)
    while n < target:
        n <<= 1
    padded = weighted + [0j] * (n - length)
    bins = _fft_radix2(padded)
    rotated = bins[n // 2:] + bins[:n // 2]          # fftshift
    peak = max(abs(value) for value in rotated) or 1.0
    freqs = [(index - n // 2) * float(sample_rate_hz) / n for index in range(n)]
    mags = [20.0 * math.log10((abs(value) / peak) or 1e-12) for value in rotated]
    return freqs, mags


def occupied_bandwidth_hz(freqs: list[float], mag_db: list[float], *,
                          drop_db: float | None = None, energy_fraction: float | None = None) -> float:
    """占用带宽：``drop_db``（如 -6 dB）或 ``energy_fraction``（如 0.99）二选一。"""
    if (drop_db is None) == (energy_fraction is None):
        raise ValueError("drop_db 与 energy_fraction 必须二选一")
    if drop_db is not None:
        peak = max(mag_db)
        inside = [freqs[i] for i, value in enumerate(mag_db) if value >= peak + float(drop_db)]
    else:
        powers = [(10.0 ** (value / 10.0), freqs[i]) for i, value in enumerate(mag_db)]
        total = sum(power for power, _ in powers) or 1e-30
        ordered = sorted(powers, reverse=True)
        accumulated = 0.0
        inside = []
        for power, freq in ordered:
            accumulated += power
            inside.append(freq)
            if accumulated / total >= float(energy_fraction):
                break
    if not inside:
        return 0.0
    return max(inside) - min(inside)


# ---------------------------------------------------------------------------
# 规格校验 / 指标汇总
# ---------------------------------------------------------------------------
def validate_spec(spec: dict[str, Any]) -> list[str]:
    """返回问题列表（空 = 合法）。不抛异常，供调用方决定错误语义。"""
    problems: list[str] = []
    sf = spec.get("sf")
    if not isinstance(sf, int) or not (SF_MIN <= sf <= SF_MAX):
        problems.append(f"sf 必须是 {SF_MIN}~{SF_MAX} 的整数，收到 {sf!r}")
    cr = spec.get("cr")
    if isinstance(cr, bool) or not isinstance(cr, int) or cr not in CR_CHOICES:
        problems.append(f"cr 必须是 {list(CR_CHOICES)} 之一（CR=4/(4+cr)），收到 {cr!r}")
    for key in ("freq_hz", "bw_hz", "tx_power_dbm", "channel_spacing_hz", "tx_period_s",
                "target_distance_m", "sample_rate_hz"):
        value = spec.get(key)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
            problems.append(f"{key} 必须为正数，收到 {value!r}")
    payload = spec.get("payload_bytes")
    if not isinstance(payload, int) or isinstance(payload, bool) or not (1 <= payload <= 255):
        problems.append(f"payload_bytes 必须是 1~255 的整数，收到 {payload!r}")
    sample_rate = spec.get("sample_rate_hz")
    bw = spec.get("bw_hz")
    if isinstance(sample_rate, (int, float)) and isinstance(bw, (int, float)) and sample_rate < bw:
        problems.append(f"sample_rate_hz ({sample_rate}) 必须 ≥ bw_hz ({bw})，否则频谱混叠")
    return problems


def compute_metrics(spec: dict[str, Any] | None = None, *, with_spectrum: bool = True) -> dict[str, Any]:
    """把规格算成一份指标字典（含频谱占用）。非法规格抛 ``ValueError``。"""
    merged = dict(DEFAULT_SPEC)
    merged.update({k: v for k, v in (spec or {}).items() if v is not None or k in ("de",)})
    merged["channel_spacing_hz"] = merged.get("channel_spacing_hz") or merged["bw_hz"]
    merged["low_data_rate_optimize"] = (
        low_data_rate_optimize(merged["sf"], merged["bw_hz"])
        if merged.get("low_data_rate_optimize") is None
        else int(merged["low_data_rate_optimize"])
    )
    problems = validate_spec(merged)
    if problems:
        raise ValueError("; ".join(problems))

    sf = int(merged["sf"])
    bw_hz = float(merged["bw_hz"])
    freq_hz = float(merged["freq_hz"])
    payload = int(merged["payload_bytes"])
    cr = int(merged["cr"])
    tsym = symbol_duration_s(sf, bw_hz)
    toa = time_on_air_s(sf, bw_hz, payload, cr=cr, crc=int(merged["crc"]),
                        implicit_header=bool(merged["implicit_header"]),
                        preamble_symbols=int(merged["preamble_symbols"]),
                        de=merged["low_data_rate_optimize"])
    preamble = (int(merged["preamble_symbols"]) + PREAMBLE_OVERHEAD_SYMBOLS) * tsym
    nominal = nominal_bitrate_bps(sf, bw_hz, cr=cr)
    airtime = airtime_bitrate_bps(payload, toa)
    budget = link_budget(merged)
    duty_cycle_pct = toa / float(merged["tx_period_s"]) * 100.0
    radiated_erp = erp_dbm(merged["tx_power_dbm"],
                           tx_gain_dbi=float(merged.get("tx_antenna_gain_dbi", 0.0)),
                           loss_db=float(merged.get("cable_loss_db", 0.0)))

    metrics: dict[str, Any] = {
        "kind": merged["kind"],
        "freq_hz": freq_hz,
        "freq_mhz": round(freq_hz / 1e6, 6),
        "bw_hz": bw_hz,
        "bw_khz": round(bw_hz / 1e3, 3),
        "sf": sf,
        "cr": cr,
        "cr_ratio": f"4/{4 + cr}",
        "crc": int(merged["crc"]),
        "implicit_header": bool(merged["implicit_header"]),
        "low_data_rate_optimize": int(merged["low_data_rate_optimize"]),
        "tx_power_dbm": float(merged["tx_power_dbm"]),
        "tx_power_mw": round(dbm_to_mw(merged["tx_power_dbm"]), 4),
        "payload_bytes": payload,
        "symbol_duration_ms": round(tsym * 1e3, 6),
        "symbol_rate_sps": round(symbol_rate_symbols_per_s(sf, bw_hz), 4),
        "chip_rate_kchips_s": round(chip_rate_chips_per_s(bw_hz) / 1e3, 3),
        "chirp_rate_mhz_s": round(chirp_rate_hz_per_s(sf, bw_hz) / 1e6, 4),
        "payload_symbols": payload_symbol_count(
            sf, payload, cr=cr, crc=int(merged["crc"]),
            implicit_header=bool(merged["implicit_header"]), de=merged["low_data_rate_optimize"]),
        "preamble_duration_ms": round(preamble * 1e3, 6),
        "payload_duration_ms": round((toa - preamble) * 1e3, 6),
        "time_on_air_ms": round(toa * 1e3, 6),
        "nominal_bitrate_bps": round(nominal, 3),
        "airtime_bitrate_bps": round(airtime, 3),
        "spectral_efficiency_bps_per_hz": round(airtime / bw_hz, 6),
        "bit_efficiency_pct": round(airtime / nominal * 100.0, 3),
        "energy_per_symbol_uj": round(energy_per_symbol_j(merged["tx_power_dbm"], sf, bw_hz) * 1e6, 6),
        "energy_per_bit_uj": round(energy_per_bit_j(merged["tx_power_dbm"], toa, payload) * 1e6, 6),
        "duty_cycle_pct": round(duty_cycle_pct, 4),
        "duty_cycle_limit_pct": DUTY_CYCLE_LIMIT_PCT,
        "duty_cycle_ok": duty_cycle_pct <= DUTY_CYCLE_LIMIT_PCT,
        "tx_period_s": float(merged["tx_period_s"]),
        "min_tx_period_s_for_duty_cycle": round(toa / (DUTY_CYCLE_LIMIT_PCT / 100.0), 4),
        "eirp_dbm": round(eirp_dbm(merged["tx_power_dbm"],
                                   tx_gain_dbi=float(merged.get("tx_antenna_gain_dbi", 0.0)),
                                   loss_db=float(merged.get("cable_loss_db", 0.0))), 3),
        "erp_dbm": round(radiated_erp, 3),
        "erp_limit_dbm": ERP_LIMIT_DBM,
        "erp_ok": radiated_erp <= ERP_LIMIT_DBM,
        "max_tx_power_dbm_for_erp": round(max_tx_power_dbm_for_erp(
            tx_gain_dbi=float(merged.get("tx_antenna_gain_dbi", 0.0)),
            loss_db=float(merged.get("cable_loss_db", 0.0))), 3),
        "in_ism_433": in_ism_433(freq_hz),
        "ism_433_range_mhz": [ISM_433_RANGE_HZ[0] / 1e6, ISM_433_RANGE_HZ[1] / 1e6],
        "regulatory_note": REGULATORY_NOTE,
        "sensitivity_note": "灵敏度按手册 BW=125 kHz 表 + 10log10(BW/125k) 热噪声缩放，属工程近似",
    }
    metrics.update(budget)

    if with_spectrum:
        samples = synth_chirp_iq(sf, bw_hz, float(merged["sample_rate_hz"]),
                                 symbols=int(merged.get("spectrum_symbols", 1)))
        freqs, mags = spectrum_db(samples, float(merged["sample_rate_hz"]))
        obw6 = occupied_bandwidth_hz(freqs, mags, drop_db=-6.0)
        obw99 = occupied_bandwidth_hz(freqs, mags, energy_fraction=0.99)
        spacing = float(merged["channel_spacing_hz"])
        metrics.update({
            "spectrum_samples": len(samples),
            "spectrum_bins": len(freqs),
            "spectrum_window": "rect（chirp 等时加权；加窗会压掉扫频两端，见 README）",
            "occupied_bw_6db_hz": round(obw6, 1),
            "occupied_bw_99pct_hz": round(obw99, 1),
            "occupied_bw_6db_over_bw": round(obw6 / bw_hz, 4),
            "occupied_bw_99pct_over_bw": round(obw99 / bw_hz, 4),
            # 「带宽利用率」= -6 dB 带宽 / 调制带宽：chirp 把能量铺满 BW 的比例
            "bandwidth_utilisation_pct": round(obw6 / bw_hz * 100.0, 3),
            "channel_spacing_hz": spacing,
            # 信道占用 = 99% 能量带宽 / 信道间隔；>100% 说明间隔需放宽（含截断泄漏）
            "channel_occupancy_pct": round(obw99 / spacing * 100.0, 3),
            "spectrum_method": "纯标准库 radix-2 FFT（单符号合成 chirp + 4× 补零）",
            "spectrum_caveat": (
                "99% 能量带宽含矩形截断的谱泄漏（理论占用 = BW）；"
                "如需精确 OBW 应按 ITU-R SM.443 用真实仪表测"),
        })
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LoRa 物理层数值（工单242 唯一真值源）")
    parser.add_argument("--sf", type=int, default=DEFAULT_SPEC["sf"])
    parser.add_argument("--bw-khz", type=float, default=125.0)
    parser.add_argument("--freq-mhz", type=float, default=433.92)
    parser.add_argument("--cr", type=int, default=DEFAULT_SPEC["cr"])
    parser.add_argument("--power-dbm", type=float, default=DEFAULT_SPEC["tx_power_dbm"])
    parser.add_argument("--payload-bytes", type=int, default=DEFAULT_PAYLOAD_BYTES)
    parser.add_argument("--target-distance-m", type=float, default=1000.0)
    parser.add_argument("--no-spectrum", action="store_true", help="跳过 FFT（快）")
    parser.add_argument("--json", action="store_true", help="只打印 JSON（默认即打印 JSON）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = dict(DEFAULT_SPEC)
    spec.update({
        "sf": args.sf, "bw_hz": args.bw_khz * 1e3, "freq_hz": args.freq_mhz * 1e6,
        "cr": args.cr, "tx_power_dbm": args.power_dbm, "payload_bytes": args.payload_bytes,
        "target_distance_m": args.target_distance_m,
    })
    try:
        metrics = compute_metrics(spec, with_spectrum=not args.no_spectrum)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "metrics": metrics}, ensure_ascii=False, indent=1))
    return 0


__all__ = [
    "CR_CHOICES", "DEFAULT_SPEC", "DIPOLE_TO_ISOTROPIC_DB", "DUTY_CYCLE_LIMIT_PCT",
    "ERP_LIMIT_DBM", "ISM_433_RANGE_HZ", "SF_MAX", "SF_MIN", "SPECTRUM_WINDOWS",
    "airtime_bitrate_bps", "chip_rate_chips_per_s", "chirp_rate_hz_per_s", "compute_metrics",
    "dbm_to_mw", "eirp_dbm", "energy_per_bit_j", "energy_per_symbol_j", "erp_dbm",
    "free_space_path_loss_db", "in_ism_433", "link_budget", "low_data_rate_optimize", "main",
    "max_free_space_range_m", "max_tx_power_dbm_for_erp", "mw_to_dbm", "nominal_bitrate_bps",
    "occupied_bandwidth_hz", "payload_symbol_count", "sensitivity_dbm", "snr_limit_db",
    "spectrum_db", "symbol_duration_s", "symbol_rate_symbols_per_s", "synth_chirp_iq",
    "time_on_air_s", "validate_spec",
]

if __name__ == "__main__":
    raise SystemExit(main())
