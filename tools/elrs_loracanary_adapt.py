"""
W61-04: ELRS → LoRaCanary 433MHz 链路借鉴落地
参考: docs/elrs-openrx-勘察.md

借鉴点:
  1. FHSS 跳频 + 低信道数合规域表（433MHz 域）
  2. LoRa 参数分档 (SF/BW/数据率) → LoRaCanary 档位选择
  3. 链路预算对比（433MHz vs 2.4GHz 路径损耗差 ~15dB）

作者: Hermes subagent
日期: 2026-09-02
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# ----------------------------------------------------------------------
# 1. FHSS 跳频域表 (抄 ELRS FHSS.cpp 分域跳频表思路)
# ----------------------------------------------------------------------


class RegulatoryDomain(Enum):
    """433MHz ISM 合规域（抄 ELRS 域表）"""
    AU433 = "AU433"   # 澳大利亚 433MHz 域
    EU433 = "EU433"   # 欧盟 433MHz 域
    US433 = "US433"   # 美国 433MHz 域
    US433W = "US433W" # 美国宽域 433MHz


@dataclass
class FhssDomainEntry:
    domain: RegulatoryDomain
    channels: list[float]          # 信道中心频率 MHz
    channel_spacing_mhz: float     # 信道间隔 MHz
    max_duty_cycle_pct: float      # 最大占空比（%），CE 用


def build_433mhz_domain_table() -> dict[RegulatoryDomain, FhssDomainEntry]:
    """
    构建 433MHz FHSS 合规域表（抄 ELRS FHSS.cpp 思路）。
    ELRS 源:
      AU433: 433.42–434.42 MHz, 3 信道
      EU433: 433.10–434.45 MHz, 3 信道
      US433: 433.25–438.00 MHz, 8 信道
      US433W: 423.5–438.0 MHz, 20 信道
    """
    table = {}

    # AU433: 3 信道, 等间隔落在 433.42–434.42 MHz
    count = 3
    start = 433.42
    stop = 434.42
    spacing = (stop - start) / (count - 1)
    table[RegulatoryDomain.AU433] = FhssDomainEntry(
        domain=RegulatoryDomain.AU433,
        channels=[round(start + i * spacing, 3) for i in range(count)],
        channel_spacing_mhz=round(spacing, 3),
        max_duty_cycle_pct=10.0,   # CE/CE10% 典型值
    )

    # EU433: 3 信道, 433.10–434.45 MHz
    count = 3
    start = 433.10
    stop = 434.45
    spacing = (stop - start) / (count - 1)
    table[RegulatoryDomain.EU433] = FhssDomainEntry(
        domain=RegulatoryDomain.EU433,
        channels=[round(start + i * spacing, 3) for i in range(count)],
        channel_spacing_mhz=round(spacing, 3),
        max_duty_cycle_pct=10.0,
    )

    # US433: 8 信道, 433.25–438.00 MHz
    count = 8
    start = 433.25
    stop = 438.00
    spacing = (stop - start) / (count - 1)
    table[RegulatoryDomain.US433] = FhssDomainEntry(
        domain=RegulatoryDomain.US433,
        channels=[round(start + i * spacing, 3) for i in range(count)],
        channel_spacing_mhz=round(spacing, 3),
        max_duty_cycle_pct=100.0,  # FCC part 15.xxx 无严格占空比限制
    )

    # US433W: 20 信道, 423.5–438.0 MHz
    count = 20
    start = 423.5
    stop = 438.0
    spacing = (stop - start) / (count - 1)
    table[RegulatoryDomain.US433W] = FhssDomainEntry(
        domain=RegulatoryDomain.US433W,
        channels=[round(start + i * spacing, 3) for i in range(count)],
        channel_spacing_mhz=round(spacing, 3),
        max_duty_cycle_pct=100.0,
    )

    return table


# 单例，全局共享
FHSS_DOMAIN_TABLE = build_433mhz_domain_table()


def get_domain_channels(domain: RegulatoryDomain) -> list[float]:
    """返回指定域的信道频率列表 (MHz)"""
    return FHSS_DOMAIN_TABLE[domain].channels


# ----------------------------------------------------------------------
# 2. LoRa 参数分档 → LoRaCanary 档位选择
# ----------------------------------------------------------------------


class LoRaCanaryTier(Enum):
    """
    LoRaCanary 参数档位（抄 ELRS 分档思路，
    把「低延迟」与「远距离」做成同一物理层上的不同档位）。
    """
    # 近距高速档（低 SF, 宽 BW, 短包）
    SHORT_RANGE = "short_range"      # SF7 / BW 250k / 低延迟
    # 中距平衡档
    MEDIUM_RANGE = "medium_range"    # SF9 / BW 125k / 平衡
    # 远距低数据率档（高 SF, 窄 BW）
    LONG_RANGE = "long_range"        # SF12 / BW 62.5k / 最远


# LoRaCanary 各档位参数表
LORA_TIER_PARAMS: dict[LoRaCanaryTier, dict] = {
    LoRaCanaryTier.SHORT_RANGE: {
        "sf": 7,
        "bw_khz": 250,
        "cr": "4/5",
        "preamble": 8,      # 缩短前导（ELRS 极简包结构）
        "crc_bytes": 2,
        "explicit_header": False,  # 省略包头（ELRS 做法）
        "description": "近距高速档 SF7/BW250k",
    },
    LoRaCanaryTier.MEDIUM_RANGE: {
        "sf": 9,
        "bw_khz": 125,
        "cr": "4/5",
        "preamble": 8,
        "crc_bytes": 2,
        "explicit_header": False,
        "description": "中距平衡档 SF9/BW125k",
    },
    LoRaCanaryTier.LONG_RANGE: {
        "sf": 12,
        "bw_khz": 62,
        "cr": "4/5",
        "preamble": 8,
        "crc_bytes": 2,
        "explicit_header": False,
        "description": "远距低数据率档 SF12/BW62k",
    },
}


def compute_symbol_time_us(sf: int, bw_khz: float) -> float:
    """
    计算 LoRa 符号时间 Tsym。
    Tsym = (2^SF) / BW  (秒)
    """
    return (2 ** sf) / (bw_khz * 1e3) * 1e6  # µs


def compute_data_rate_bps(sf: int, bw_khz: float, cr_num: int = 4, cr_den: int = 5) -> float:
    """
    计算 LoRa 数据率。
    DR = SF * (BW / 2^SF) * cr  (bps)
    """
    return sf * (bw_khz * 1e3 / (2 ** sf)) * (cr_num / cr_den)


def estimate_sensitivity(sf: int, bw_khz: float, nf_db: float = 6.0) -> float:
    """
    估算接收灵敏度（dBm）。
    简化公式: Sens ≈ -174 + 10*log10(BW) + NF + SNR_required
    SNR_required 随 SF 变化（近似：SF7≈-7.5dB, 每+1档约-2.5dB）
    """
    bw_hz = bw_khz * 1e3
    snr_required_db = -7.5 - (sf - 7) * 2.5  # SF7=-7.5dB 基线
    sens = -174 + 10 * math.log10(bw_hz) + nf_db + snr_required_db
    return round(sens, 2)


def select_lora_tier(
    distance_km: float,
    required_data_rate_bps: float | None = None,
    available_tx_power_dbm: float = 20.0,
) -> LoRaCanaryTier:
    """
    根据距离 / 数据率需求选择 LoRaCanary 档位。

    参数:
      distance_km: 预计通信距离 (km)
      required_data_rate_bps: 最小需求数据率 (bps)，可 None
      available_tx_power_dbm: 可用发射功率 (dBm)

    返回:
      推荐 LoRaCanaryTier
    """
    # 距离分级（参考 ELRS 链路预算，433MHz 每+6dB ≈ 远一倍）
    if distance_km <= 2.0:
        tier = LoRaCanaryTier.SHORT_RANGE
    elif distance_km <= 20.0:
        tier = LoRaCanaryTier.MEDIUM_RANGE
    else:
        tier = LoRaCanaryTier.LONG_RANGE

    # 若指定数据率需求，验证该档位能否满足
    if required_data_rate_bps is not None:
        params = LORA_TIER_PARAMS[tier]
        actual_dr = compute_data_rate_bps(
            params["sf"], params["bw_khz"],
            *map(int, params["cr"].split("/"))
        )
        # 若不满足，升级到更高速档（降 SF 换数据率）
        if actual_dr < required_data_rate_bps:
            # 找更高数据率的档位
            for candidate in [LoRaCanaryTier.SHORT_RANGE, LoRaCanaryTier.MEDIUM_RANGE]:
                p = LORA_TIER_PARAMS[candidate]
                dr = compute_data_rate_bps(
                    p["sf"], p["bw_khz"],
                    *map(int, p["cr"].split("/"))
                )
                if dr >= required_data_rate_bps:
                    return candidate

    return tier


def get_tier_params(tier: LoRaCanaryTier) -> dict:
    """返回指定档位的完整参数 dict"""
    return LORA_TIER_PARAMS[tier].copy()


# ----------------------------------------------------------------------
# 3. 链路预算对比（433MHz vs 2.4GHz 路径损耗差）
# ----------------------------------------------------------------------


def free_space_path_loss_db(d_km: float, f_mhz: float) -> float:
    """
    自由空间路径损耗 (dB)。
    Lfs(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44
    """
    return 20 * math.log10(d_km) + 20 * math.log10(f_mhz) + 32.44


def path_loss_advantage_433_vs(f_mhz: float, d_km: float = 100.0) -> float:
    """
    433MHz 相对于其他频段的路径损耗优势 (dB)。
    基准: 433MHz; 其他频段损耗更大。
    """
    loss_433 = free_space_path_loss_db(d_km, 433.0)
    loss_other = free_space_path_loss_db(d_km, f_mhz)
    return round(loss_other - loss_433, 2)  # 正数 = 433MHz 省下的 dB


# 预计算 100km 处的各频段对比表
PATH_LOSS_TABLE_100KM = {
    "433 MHz":  round(free_space_path_loss_db(100.0, 433.0), 1),
    "868 MHz":  round(free_space_path_loss_db(100.0, 868.0), 1),
    "915 MHz":  round(free_space_path_loss_db(100.0, 915.0), 1),
    "2400 MHz": round(free_space_path_loss_db(100.0, 2400.0), 1),
}


# 验收用: 433MHz 对 2.4GHz 的路径损耗优势（100km）
def get_433_vs_24g_advantage_db(d_km: float = 100.0) -> float:
    """433MHz 相对 2.4GHz 的路径损耗节省量 (dB)"""
    return path_loss_advantage_433_vs(2400.0, d_km)


# ----------------------------------------------------------------------
# 导出表格（用于报告/调试）
# ----------------------------------------------------------------------


def summarize_fhss_table() -> str:
    """返回 FHSS 域表的人类可读摘要"""
    lines = ["=== 433MHz FHSS 合规域表 ==="]
    for domain, entry in FHSS_DOMAIN_TABLE.items():
        chans = ", ".join(f"{c:.3f}" for c in entry.channels)
        lines.append(
            f"  {domain.value}: {len(entry.channels)} 信道, "
            f"间隔 {entry.channel_spacing_mhz:.3f} MHz, "
            f"最大占空比 {entry.max_duty_cycle_pct:.0f}%, "
            f"频率: [{chans}] MHz"
        )
    return "\n".join(lines)


def summarize_tier_params() -> str:
    """返回 LoRa 参数档位的人类可读摘要"""
    lines = ["=== LoRaCanary 参数档位表 ==="]
    for tier, params in LORA_TIER_PARAMS.items():
        sf = params["sf"]
        bw = params["bw_khz"]
        dr = compute_data_rate_bps(sf, bw, 4, 5)
        tsym = compute_symbol_time_us(sf, bw)
        sens = estimate_sensitivity(sf, bw)
        lines.append(
            f"  {tier.value}: {params['description']}\n"
            f"    SF={sf}, BW={bw}kHz, DR={dr:.0f}bps, "
            f"Tsym={tsym:.1f}µs, Sens≈{sens:.1f}dBm"
        )
    return "\n".join(lines)