"""Phase 5 自主闭环测试：频谱扫描调度器 + 能量检测 + 候选信号表 + 失败重试反馈环。

验收（工单「rf_brain 全自动闭环 Phase5」）：
- 能量检测阈值分离：SNR 15~30dB 三调制全 >12dB，噪声全 <12dB
- 盲扫语义：能量检测只读 IQ，不感知布点表 present 标记
- 白名单：144~148MHz（业余 2m）合法放行，越界（131.5M/49M 等）抛 ValueError
- run_sweep 端到端：误检率 <10%、漏检率 <10%、30 秒内完成
- 失配调制重试：demod 失败 → alternatives 重试 → 收敛（反馈环生效）
- 跨窗口隔离：相邻窗口能量互不污染
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.amateur_bands import AMATEUR_BANDS, assert_allowed_freq, is_allowed_freq
from mcpserver.rf_brain.autonomous import run_sweep
from mcpserver.rf_brain.loop import run_loop
from mcpserver.rf_brain.scanner import (
    ScanConfig,
    energy_detect,
    scan_spectrum,
)
from mcpserver.rf_brain.schemas import Decision, DemodFeedback
from mcpserver.rf_brain.sensor import generate_iq, noise_only

THRESHOLD = 12.0
_SIGNAL_SNRS = (15.0, 20.0, 30.0)
_MODS = ("GFSK", "FSK", "OOK")


# ---------------------------------------------------------------- 1. 能量阈值分离
def test_energy_detect_separates_signal_from_noise():
    """SNR 15/20/30dB 三调制能量全 >12dB；多 seed 噪声能量全 <12dB。"""
    for mod in _MODS:
        for snr in _SIGNAL_SNRS:
            iq = generate_iq(mod, snr_db=snr)
            e = energy_detect(iq)
            assert e > THRESHOLD, f"{mod}@{snr}dB 能量 {e:.2f}dB 未超过阈值 {THRESHOLD}dB"
    for seed in range(1, 9):
        e = energy_detect(noise_only(seed=seed))
        assert e < THRESHOLD, f"噪声 seed={seed} 能量 {e:.2f}dB 误判为信号"


def test_energy_detect_is_deterministic():
    """同一 IQ 快照 → 同一能量值（纯函数，无状态）。"""
    iq = generate_iq("GFSK", snr_db=20.0, seed=7)
    assert energy_detect(iq) == energy_detect(iq)


# ---------------------------------------------------------------- 2. 盲扫语义
def test_detection_depends_only_on_iq_not_schedule():
    """扫描器判定 = 纯能量阈值比较：detected 与布点表 present 标记解耦。

    验证方式：用扫描返回的 IQ 快照独立重算能量，必须与扫描结果一致——
    证明能量检测只读 IQ，没有偷看布点表。
    """
    config = ScanConfig(schedule=[
        {"freq": 144_100_000, "modulation": "GFSK", "snr_db": 20.0, "present": True},
        {"freq": 144_150_000, "modulation": "FSK", "snr_db": 15.0, "present": True},
        {"freq": 144_200_000, "modulation": "OOK", "snr_db": 30.0, "present": True},
        {"freq": 144_250_000, "modulation": "FSK", "snr_db": 20.0, "present": False},  # 噪声窗口
    ])
    result = scan_spectrum(config)
    assert result.n_windows == 4
    for cand in result.candidates:
        recomputed = energy_detect(cand.iq, config.sample_rate)
        assert recomputed == pytest.approx(cand.energy_db, abs=0.005), \
            "能量检测结果依赖布点表（盲扫语义被破坏）"
        assert cand.detected == (cand.energy_db >= config.energy_threshold_db)
        # ground_truth 仅用于测试台标注，不参与检测
        if cand.ground_truth is None:
            assert not cand.detected, "噪声窗口被误判为信号"
        else:
            assert cand.detected, f"信号窗口 {cand.ground_truth} 漏检"


# ---------------------------------------------------------------- 3. 白名单
def test_whitelist_allows_2m_frequencies():
    """144~148MHz（业余 2m 段）合法：校验通过、扫描放行。"""
    assert is_allowed_freq(144_850_000)
    assert_allowed_freq(144_850_000)  # 不抛异常
    assert is_allowed_freq(144_000_000)  # 下边界
    assert is_allowed_freq(148_000_000)  # 上边界
    result = scan_spectrum(ScanConfig(schedule=[
        {"freq": 144_100_000, "modulation": "GFSK", "snr_db": 20.0, "present": True},
        {"freq": 147_900_000, "modulation": "FSK", "snr_db": 20.0, "present": True},
    ]))
    assert result.n_windows == 2


@pytest.mark.parametrize("bad_freq", [
    131_500_000,   # 30~50MHz 之间，非业余段
    49_000_000,    # 低于 6m 下边界
    30_000_001,    # HF 与 6m 之间
    148_000_001,   # 超过 2m 上边界
    1_799_999,     # 低于 HF 下边界
])
def test_whitelist_rejects_out_of_band(bad_freq):
    """越界频点：断言校验抛 ValueError，扫描调度前置拦截（不产生半截结果）。"""
    with pytest.raises(ValueError):
        assert_allowed_freq(bad_freq)
    with pytest.raises(ValueError):
        scan_spectrum(ScanConfig(schedule=[
            {"freq": bad_freq, "modulation": "GFSK", "snr_db": 20.0, "present": True},
        ]))


def test_amateur_bands_aligned_with_rsba1():
    """白名单与 rsba1_adapter 数值对齐（来源 civ_commands.py AMATEUR_BANDS）。"""
    assert AMATEUR_BANDS == (
        (1_800_000, 30_000_000),
        (50_000_000, 54_000_000),
        (144_000_000, 148_000_000),
    )


# ---------------------------------------------------------------- 4. 失败重试反馈环
def test_loop_converges_with_correct_modulation_first():
    """正确调制排在候选首位 → 一轮内收敛（GFSK/FSK 判据、OOK 包络判据）。"""
    for mod in _MODS:
        iq = generate_iq(mod, snr_db=20.0, seed=7)
        loop = run_loop(iq, sample_rate=2_000_000.0, center_freq=144_850_000,
                        ground_truth_modulation=mod, max_attempts=3)
        assert loop.converged, f"{mod} 闭环未收敛: {loop.history}"
        assert loop.modulation == mod, f"{mod} 闭环收敛到错误调制 {loop.modulation}"


def test_loop_retries_on_demod_failure():
    """决策首猜错误 → demod 失败 → alternatives 重试 → 收敛（反馈环生效）。

    用 mock 同时钉住 decide（首猜 FSK，GFSK 为备选）与 demodulate（首次失败、
    重试成功），确定性验证 run_loop 的"失败→重试→收敛"控制流，
    不依赖玩具解调器对具体调制组合的噪声运气。
    """
    iq = generate_iq("GFSK", snr_db=20.0, seed=7)
    wrong_first = Decision(
        decision="demodulate",
        modulation="FSK",
        demod_params={"symbol_rate_hz": 48000},
        confidence=0.9,
        reasoning="mock 强制首猜 FSK",
        alternatives=[{"modulation": "GFSK", "confidence": 0.1}],
    )
    fail_fb = DemodFeedback(status="failed", demod_success=False, output_symbol_count=0,
                            feedback="mock 首猜失败")
    ok_fb = DemodFeedback(status="ok", demod_success=True, output_symbol_count=97,
                          feedback="mock 重试成功")
    with mock.patch("mcpserver.rf_brain.loop.decide", return_value=wrong_first), \
         mock.patch("mcpserver.rf_brain.loop.demodulate", side_effect=[fail_fb, ok_fb]):
        loop = run_loop(iq, sample_rate=2_000_000.0, center_freq=144_850_000,
                        ground_truth_modulation="GFSK", max_attempts=3)
    assert loop.converged
    assert loop.modulation == "GFSK"
    assert len(loop.history) >= 2, "反馈环未触发重试（history 应有首猜失败+重试成功两轮）"
    assert loop.history[0]["demod_success"] is False
    assert loop.history[-1]["demod_success"] is True


# ---------------------------------------------------------------- 5. run_sweep 端到端
def _e2e_schedule() -> list[dict]:
    """10 窗口：8 有信号（三调制 × 多 SNR）+ 2 噪声，全在 2m 业余段。"""
    return [
        {"freq": 144_100_000, "modulation": "GFSK", "snr_db": 20.0, "present": True},
        {"freq": 144_150_000, "modulation": "FSK", "snr_db": 15.0, "present": True},
        {"freq": 144_200_000, "modulation": "OOK", "snr_db": 30.0, "present": True},
        {"freq": 144_250_000, "modulation": "FSK", "snr_db": 30.0, "present": True},
        {"freq": 144_300_000, "modulation": "GFSK", "snr_db": 15.0, "present": True},
        {"freq": 144_350_000, "modulation": "OOK", "snr_db": 15.0, "present": True},
        {"freq": 144_400_000, "modulation": "GFSK", "snr_db": 30.0, "present": True},
        {"freq": 144_450_000, "modulation": "FSK", "snr_db": 20.0, "present": True},
        {"freq": 144_500_000, "modulation": "GFSK", "snr_db": 20.0, "present": False},
        {"freq": 144_550_000, "modulation": "FSK", "snr_db": 20.0, "present": False},
    ]


def test_run_sweep_e2e_acceptance():
    """端到端验收：误检率 <10%、漏检率 <10%、30 秒内完成、信号全收敛。"""
    config = ScanConfig(schedule=_e2e_schedule(), energy_threshold_db=THRESHOLD)
    t0 = time.perf_counter()
    report = run_sweep(config, max_attempts=3)
    wall = time.perf_counter() - t0

    assert report.n_windows == 10
    assert report.n_present == 8
    assert report.n_detected == 8
    assert report.false_positive == 0
    assert report.false_negative == 0
    assert report.false_positive_rate < 0.10, f"误检率 {report.false_positive_rate:.2%} 超限"
    assert report.false_negative_rate < 0.10, f"漏检率 {report.false_negative_rate:.2%} 超限"
    assert wall < 30.0, f"全自动闭环耗时 {wall:.1f}s 超 30s 验收线"
    for rep in report.candidates:
        if rep.ground_truth:
            assert rep.converged, f"{rep.center_freq_hz}Hz {rep.ground_truth} 未收敛"


def test_run_sweep_all_noise_zero_false_positive():
    """纯噪声环境：误检率必须 0（<10% 验收线的强条件）。"""
    config = ScanConfig(schedule=[
        {"freq": 144_100_000 + i * 50_000, "modulation": "GFSK", "snr_db": 20.0, "present": False}
        for i in range(10)
    ])
    report = run_sweep(config, max_attempts=3)
    assert report.false_positive == 0
    assert report.false_positive_rate == 0.0
    assert report.n_detected == 0


def test_run_sweep_all_signals_zero_false_negative():
    """全信号环境：漏检率必须 0。"""
    config = ScanConfig(schedule=[
        {"freq": 144_100_000 + i * 50_000,
         "modulation": _MODS[i % 3], "snr_db": 20.0, "present": True}
        for i in range(9)
    ])
    report = run_sweep(config, max_attempts=3)
    assert report.false_negative == 0
    assert report.false_negative_rate == 0.0
    assert report.n_detected == 9


# ---------------------------------------------------------------- 6. 跨窗口隔离
def test_adjacent_windows_do_not_cross_contaminate():
    """相邻窗口能量互不污染：每个窗口只由自身 IQ 决定，与邻居无关。"""
    config = ScanConfig(schedule=[
        {"freq": 144_100_000, "modulation": "GFSK", "snr_db": 20.0, "present": True},
        {"freq": 144_110_000, "modulation": "OOK", "snr_db": 20.0, "present": True},
        {"freq": 144_120_000, "modulation": "FSK", "snr_db": 20.0, "present": True},
    ])
    result = scan_spectrum(config)
    assert result.n_detected == 3
    # 每个候选的能量 = 独立重算自身 IQ 的能量（邻居多强都不影响）
    for cand in result.candidates:
        assert energy_detect(cand.iq, config.sample_rate) == pytest.approx(cand.energy_db, abs=0.005)
    # 两连发信号（GFSK→OOK 紧邻）：各自保留自身特征与标注
    assert result.candidates[0].ground_truth == "GFSK"
    assert result.candidates[1].ground_truth == "OOK"
    assert all(c.detected for c in result.candidates)
