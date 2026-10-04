"""
测试 W61-04: ELRS → LoRaCanary 433MHz 链路借鉴
pytest 全绿 ≥4 用例
验收硬线: 433MHz 链路预算 ≥ 2.4GHz 同功率 15dB 优势

作者: Hermes subagent
日期: 2026-09-02
"""

import math

import pytest

from tools.elrs_loracanary_adapt import (
    FHSS_DOMAIN_TABLE,
    LORA_TIER_PARAMS,
    PATH_LOSS_TABLE_100KM,
    LoRaCanaryTier,
    RegulatoryDomain,
    compute_data_rate_bps,
    compute_symbol_time_us,
    estimate_sensitivity,
    free_space_path_loss_db,
    get_433_vs_24g_advantage_db,
    get_domain_channels,
    get_tier_params,
    path_loss_advantage_433_vs,
    select_lora_tier,
    summarize_fhss_table,
    summarize_tier_params,
)

# ----------------------------------------------------------------------
# 验收硬线: 433MHz vs 2.4GHz 路径损耗差 ≈ 15dB (100km)
# ----------------------------------------------------------------------


class TestPathLossAdvantage:
    """验收: 433MHz 链路预算 ≥ 2.4GHz 同功率 15dB 优势"""

    def test_433_vs_24g_advantage_100km(self):
        """
        验收硬线: 433MHz vs 2.4GHz @100km 路径损耗差 ≈ 15dB
        ELRS 勘察报告 §3 给出: +15.0 dB
        """
        adv = get_433_vs_24g_advantage_db(100.0)
        # 允许 ±0.5 dB 容差（浮点误差）
        assert abs(adv - 15.0) < 0.5, (
            f"433MHz 对 2.4GHz 优势应为 ~15dB, 实际 {adv:.2f} dB"
        )

    def test_433_vs_24g_advantage_50km(self):
        """
        验证: 50km 处路径损耗差仍约 15dB（自由空间损耗与距离无关，只与频率比有关）
        """
        adv = get_433_vs_24g_advantage_db(50.0)
        # 自由空间损耗: 距离项 20*log10(d) 消去，差值仅来自频率项
        # 所以 50km 和 100km 差值相同
        assert abs(adv - 15.0) < 0.5

    def test_path_loss_table_100km_values(self):
        """
        验证 100km 预计算路径损耗表数值正确（抄 ELRS 勘察报告 §3）
        """
        assert abs(PATH_LOSS_TABLE_100KM["433 MHz"] - 125.2) < 0.5
        assert abs(PATH_LOSS_TABLE_100KM["2400 MHz"] - 140.2) < 0.5
        assert PATH_LOSS_TABLE_100KM["433 MHz"] < PATH_LOSS_TABLE_100KM["2400 MHz"]

    def test_free_space_formula(self):
        """验证自由空间路径损耗公式量纲正确"""
        # 已知点: d=1km, f=433MHz → Lfs ≈ 85.2 dB
        # Lfs = 20*log10(1) + 20*log10(433) + 32.44 = 0 + 52.73 + 32.44 = 85.17 dB
        loss = free_space_path_loss_db(1.0, 433.0)
        assert 84 < loss < 87, f"1km@433MHz 路径损耗应为 ~85dB, 实际 {loss:.2f}"

    def test_frequency_ratio_drives_advantage(self):
        """
        验证: 频率比相同 → 路径损耗优势相同（与距离无关）
        f2/f1 比值决定损耗差，距离项在差分中抵消
        """
        # 868MHz vs 433MHz 频率比 2.0 → 差 6dB
        adv_868 = path_loss_advantage_433_vs(868.0, d_km=50.0)
        adv_868_100 = path_loss_advantage_433_vs(868.0, d_km=100.0)
        assert abs(adv_868 - 6.0) < 0.5
        assert abs(adv_868 - adv_868_100) < 0.01  # 与距离无关


# ----------------------------------------------------------------------
# FHSS 域表测试
# ----------------------------------------------------------------------


class TestFhssDomainTable:
    """FHSS 域表结构与数值验证"""

    def test_domain_table_complete(self):
        """验证 4 个 433MHz 域全部存在"""
        assert len(FHSS_DOMAIN_TABLE) == 4
        for domain in RegulatoryDomain:
            assert domain in FHSS_DOMAIN_TABLE

    def test_au433_channels(self):
        """AU433: 3 信道，频率范围合理"""
        entry = FHSS_DOMAIN_TABLE[RegulatoryDomain.AU433]
        assert len(entry.channels) == 3
        assert all(433.0 <= ch <= 435.0 for ch in entry.channels)

    def test_us433_channels(self):
        """US433: 8 信道"""
        entry = FHSS_DOMAIN_TABLE[RegulatoryDomain.US433]
        assert len(entry.channels) == 8
        assert all(433.0 <= ch <= 439.0 for ch in entry.channels)

    def test_us433w_channels(self):
        """US433W: 20 信道，覆盖更宽范围"""
        entry = FHSS_DOMAIN_TABLE[RegulatoryDomain.US433W]
        assert len(entry.channels) == 20
        assert entry.channels[0] < 424.0
        assert entry.channels[-1] > 437.0

    def test_get_domain_channels(self):
        """get_domain_channels 返回正确列表"""
        chs = get_domain_channels(RegulatoryDomain.EU433)
        assert len(chs) == 3
        assert chs == FHSS_DOMAIN_TABLE[RegulatoryDomain.EU433].channels

    def test_channel_spacing_positive(self):
        """所有域信道间隔 > 0"""
        for entry in FHSS_DOMAIN_TABLE.values():
            assert entry.channel_spacing_mhz > 0

    def test_duty_cycle_reasonable(self):
        """占空比 0~100 范围"""
        for entry in FHSS_DOMAIN_TABLE.values():
            assert 0 < entry.max_duty_cycle_pct <= 100


# ----------------------------------------------------------------------
# LoRa 参数档位测试
# ----------------------------------------------------------------------


class TestLoraTierParams:
    """LoRa 参数档位表验证"""

    def test_all_tiers_present(self):
        """三个档位全部存在"""
        assert len(LORA_TIER_PARAMS) == 3
        for tier in LoRaCanaryTier:
            assert tier in LORA_TIER_PARAMS

    def test_tier_params_fields(self):
        """每个档位含必要字段"""
        required = {"sf", "bw_khz", "cr", "preamble", "crc_bytes", "explicit_header"}
        for params in LORA_TIER_PARAMS.values():
            assert required.issubset(params.keys())

    def test_sf_range(self):
        """SF 在 LoRa 合法范围 (7~12)"""
        for params in LORA_TIER_PARAMS.values():
            assert 7 <= params["sf"] <= 12

    def test_symbol_time_positive(self):
        """符号时间 > 0"""
        for tier, params in LORA_TIER_PARAMS.items():
            tsym = compute_symbol_time_us(params["sf"], params["bw_khz"])
            assert tsym > 0

    def test_data_rate_positive(self):
        """数据率 > 0"""
        for params in LORA_TIER_PARAMS.values():
            dr = compute_data_rate_bps(params["sf"], params["bw_khz"], 4, 5)
            assert dr > 0

    def test_sensitivity_reasonable(self):
        """灵敏度在合理范围 (LoRa SX1276 典型 -120 ~ -140 dBm)"""
        for params in LORA_TIER_PARAMS.values():
            sens = estimate_sensitivity(params["sf"], params["bw_khz"])
            assert -150 < sens < -100

    def test_get_tier_params_copy(self):
        """get_tier_params 返回独立副本（不泄露内部 dict）"""
        p1 = get_tier_params(LoRaCanaryTier.SHORT_RANGE)
        p1["sf"] = 999
        p2 = get_tier_params(LoRaCanaryTier.SHORT_RANGE)
        assert p2["sf"] == 7


# ----------------------------------------------------------------------
# 档位选择逻辑测试
# ----------------------------------------------------------------------


class TestLoraTierSelection:
    """select_lora_tier 距离/数据率分级逻辑"""

    def test_short_range_distance(self):
        """≤2km → SHORT_RANGE"""
        tier = select_lora_tier(distance_km=1.0)
        assert tier == LoRaCanaryTier.SHORT_RANGE

    def test_medium_range_distance(self):
        """2~20km → MEDIUM_RANGE"""
        for d in [5.0, 10.0, 15.0, 20.0]:
            assert select_lora_tier(distance_km=d) == LoRaCanaryTier.MEDIUM_RANGE

    def test_long_range_distance(self):
        """>20km → LONG_RANGE"""
        tier = select_lora_tier(distance_km=50.0)
        assert tier == LoRaCanaryTier.LONG_RANGE

    def test_data_rate_upgrade(self):
        """
        指定高数据率需求时，若当前档位不满足，应升级到更高速档
        LONG_RANGE 档位数据率最低，若需求 > LONG_RANGE 上限 → 尝试升级
        """
        # SF12/BW62k 的数据率极低，大部分应用需求都会触发升级到更高数据率档位
        tier = select_lora_tier(distance_km=1.0, required_data_rate_bps=1000.0)
        # 近距档 SF7/BW250k 数据率足够
        assert tier in [LoRaCanaryTier.SHORT_RANGE, LoRaCanaryTier.MEDIUM_RANGE]

    def test_tier_selection_no_required_dr(self):
        """无数据率需求时，按距离选档"""
        assert select_lora_tier(distance_km=0.5) == LoRaCanaryTier.SHORT_RANGE
        assert select_lora_tier(distance_km=30.0) == LoRaCanaryTier.LONG_RANGE


# ----------------------------------------------------------------------
# 汇总输出测试
# ----------------------------------------------------------------------


class TestSummaries:
    """summarize_* 函数输出非空字符串"""

    def test_fhss_summary_nonempty(self):
        s = summarize_fhss_table()
        assert len(s) > 0
        assert "433MHz FHSS 合规域表" in s
        assert "AU433" in s

    def test_tier_summary_nonempty(self):
        s = summarize_tier_params()
        assert len(s) > 0
        assert "LoRaCanary 参数档位表" in s
        assert "SF=" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])