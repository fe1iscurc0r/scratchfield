"""Phase 4 DSP 测试：GFSK vs FSK 瞬时相位轨迹判据 + liquid-dsp 对拍。

验收（工单「射频大脑 Phase 4」）：
- GFSK（高斯平滑坡道）与 FSK（硬切换尖峰）的 freq_transition_slope 可分离
- rule_engine 据此把正确调制排候选第一（突破 M1「GFSK/FSK 归大类」边界）
- liquid-dsp 接入后同一测试信号特征与 numpy 参考一致（DLL 缺失时跳过对拍）
- DLL 缺失时 extract_features 自动降级 numpy，闭环不停摆
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain import liquid_backend
from mcpserver.rf_brain.feature_extractor import extract_features
from mcpserver.rf_brain.rule_engine import FSK_SLOPE_THRESHOLD, preselect_candidates
from mcpserver.rf_brain.sensor import generate_iq, noise_only

_SEEDS = (42, 7, 123)


@pytest.fixture(autouse=True)
def _reset_liquid_load_state(monkeypatch):
    """每个测试前重置 liquid_backend 模块级加载缓存，避免跨测试污染。"""
    monkeypatch.setattr(liquid_backend, "_load_attempted", False)
    monkeypatch.setattr(liquid_backend, "_lib", None)


def test_gfsk_fsk_slope_separation():
    """瞬时相位轨迹判据：FSK 硬切换指标显著高于 GFSK 高斯成形。"""
    for seed in _SEEDS:
        gfsk = extract_features(generate_iq("GFSK", snr_db=20.0, seed=seed)).freq_transition_slope
        fsk = extract_features(generate_iq("FSK", snr_db=20.0, seed=seed)).freq_transition_slope
        print(f"[seed={seed}] GFSK slope={gfsk:.4f}  FSK slope={fsk:.4f}")
        assert gfsk is not None and fsk is not None
        assert gfsk < FSK_SLOPE_THRESHOLD < fsk, (
            f"seed={seed}: 判据未分离 GFSK={gfsk:.4f} / FSK={fsk:.4f}（阈值 {FSK_SLOPE_THRESHOLD}）"
        )


def test_rule_engine_orders_gfsk_fsk_correctly():
    """Phase 4 突破：恒定包络内部细分，正确调制排候选第一。"""
    for mod in ("GFSK", "FSK"):
        iq = generate_iq(mod, snr_db=20.0, seed=42)
        fv = extract_features(iq)
        fv.modulation_candidates = preselect_candidates(fv)
        print(f"[{mod}] slope={fv.freq_transition_slope:.4f} candidates={fv.modulation_candidates}")
        assert fv.modulation_candidates[0] == mod, f"{mod} 应排候选第一"


def test_ook_and_noise_unaffected():
    """OOK 走包络判据、噪声判无信号——相位轨迹判据不干扰原有路径。"""
    ook = extract_features(generate_iq("OOK", snr_db=20.0, seed=42))
    assert preselect_candidates(ook)[0] == "OOK"
    noise = extract_features(noise_only())
    assert not noise.is_valid_signal()
    assert preselect_candidates(noise) == []


def test_low_snr_degrades_gracefully():
    """SNR≤10dB 判据重叠是可接受边界：候选仍含 FSK 大类，不崩不抛。"""
    fv = extract_features(generate_iq("FSK", snr_db=10.0, seed=42))
    cands = preselect_candidates(fv)
    assert set(cands) <= {"FSK", "GFSK", "OOK"} and len(cands) > 0


def test_numpy_fallback_when_no_dll():
    """本机无 libliquid 时降级 numpy 参考实现，特征照常产出。"""
    fv = extract_features(generate_iq("GFSK", snr_db=20.0, seed=42), force_numpy=True)
    assert fv.is_valid_signal()
    assert fv.freq_transition_slope is not None
    if not liquid_backend.is_available():
        # 无 DLL：默认路径 == numpy 路径，结果完全一致
        fv_default = extract_features(generate_iq("GFSK", snr_db=20.0, seed=42))
        assert fv_default.snr_db == pytest.approx(fv.snr_db, abs=1e-9)


@pytest.mark.skipif(not liquid_backend.is_available(), reason="libliquid 未编译（天选7 硬件环境才有）")
def test_liquid_numpy_feature_parity():
    """验收：liquid-dsp 接入后同一测试信号特征与 numpy 参考一致（容差内）。

    窗函数不同（Hamming vs Hanning），逐 bin 功率不要求相等；
    要求决策层消费的语义特征一致：主峰频率、带宽、平坦度、SNR。
    """
    for mod in ("GFSK", "FSK", "OOK"):
        iq = generate_iq(mod, snr_db=20.0, seed=42)
        ref = extract_features(iq, force_numpy=True)
        liq = extract_features(iq)  # 默认路径应走 liquid
        print(f"[{mod}] numpy snr={ref.snr_db:.1f} liquid snr={liq.snr_db:.1f}")
        assert liq.peak_freq_hz == pytest.approx(ref.peak_freq_hz, rel=1e-3)
        assert liq.spectral_flatness == pytest.approx(ref.spectral_flatness, abs=0.05)
        assert liq.snr_db == pytest.approx(ref.snr_db, abs=3.0)
        if ref.bandwidth_hz:
            assert liq.bandwidth_hz == pytest.approx(ref.bandwidth_hz, rel=0.3)


# ---------------------------------------------------------------- 回退路径日志与覆盖
def _isolate_no_dll(monkeypatch):
    """隔离环境：env 清空 + 候选目录指向不存在的路径，保证必然全 miss。"""
    monkeypatch.setenv("LIQUID_DSP_LIB", "")
    monkeypatch.setattr(liquid_backend, "_CANDIDATE_DIRS",
                        [Path("C:/nonexistent-libliquid-dir")] if sys.platform == "win32"
                        else [Path("/nonexistent-libliquid-dir")])


def test_fallback_logs_candidate_miss_and_summary(caplog, monkeypatch):
    """DLL 缺失时：逐候选路径 debug 日志 + 最终降级 warning 摘要都输出。"""
    _isolate_no_dll(monkeypatch)
    caplog.set_level(logging.DEBUG, logger="mcpserver.rf_brain.liquid_backend")
    assert liquid_backend.is_available() is False
    # 降级摘要为 warning（默认 root WARNING 级别下可见，进程内仅一次）
    assert any(r.levelno == logging.WARNING and "libliquid 未找到" in r.message
               for r in caplog.records)
    # 候选路径逐条扫描（debug）——仅当存在候选路径时（env 为空则 0 条）
    miss_records = [r for r in caplog.records if "候选路径不存在" in r.message]
    expected = len(liquid_backend._lib_candidates())  # env 清空 → 指向不存在目录
    assert len(miss_records) == expected


def test_load_failure_logs_warning_and_falls_back(caplog, monkeypatch, tmp_path):
    """文件存在但 CDLL 加载失败 → warning 含失败原因 + 降级 numpy（P6 分支）。"""
    name = liquid_backend._LIB_NAMES.get(sys.platform, liquid_backend._LIB_NAMES_DEFAULT)[0]
    fake = tmp_path / name
    fake.write_bytes(b"not-a-real-dll")  # 伪 DLL：文件在，加载必然失败
    monkeypatch.setattr(liquid_backend, "_CANDIDATE_DIRS", [tmp_path])
    monkeypatch.setenv("LIQUID_DSP_LIB", "")
    caplog.set_level(logging.WARNING, logger="mcpserver.rf_brain.liquid_backend")
    assert liquid_backend.is_available() is False
    assert any(r.levelno == logging.WARNING and "加载" in r.message and "失败" in r.message
               for r in caplog.records)


def test_power_spectrum_raises_when_unavailable(monkeypatch):
    """lib 不可用时 power_spectrum 抛明确 RuntimeError（绝不静默空返回）。"""
    monkeypatch.setattr(liquid_backend, "_load_lib", lambda: None)
    with pytest.raises(RuntimeError, match="liquid-dsp 不可用"):
        liquid_backend.power_spectrum(generate_iq("GFSK", snr_db=20.0, seed=42))


def test_lib_candidates_env_priority(monkeypatch):
    """DLL 定位顺序：LIQUID_DSP_LIB 环境变量优先于 vendor 目录（平台无关）。"""
    monkeypatch.setenv("LIQUID_DSP_LIB", "C:/custom/libliquid.dll")
    cands = liquid_backend._lib_candidates()
    assert cands[0] == Path("C:/custom/libliquid.dll")
    monkeypatch.delenv("LIQUID_DSP_LIB")
    cands = liquid_backend._lib_candidates()
    names = liquid_backend._LIB_NAMES.get(sys.platform, liquid_backend._LIB_NAMES_DEFAULT)
    assert any(str(cands[0]).endswith(str(Path("vendor") / n)) for n in names)


def test_extract_features_logs_numpy_backend_choice(caplog, monkeypatch):
    """feature_extractor 回退 numpy 分支有 debug 日志输出（后端选择可寻址）。"""
    _isolate_no_dll(monkeypatch)
    caplog.set_level(logging.DEBUG, logger="mcpserver.rf_brain.feature_extractor")
    extract_features(generate_iq("GFSK", snr_db=20.0, seed=42), force_numpy=True)
    assert any(r.levelno == logging.DEBUG and "numpy 参考实现" in r.message
               for r in caplog.records)


if __name__ == "__main__":
    test_gfsk_fsk_slope_separation()
    test_rule_engine_orders_gfsk_fsk_correctly()
    test_ook_and_noise_unaffected()
    test_low_snr_degrades_gracefully()
    test_numpy_fallback_when_no_dll()
    if liquid_backend.is_available():
        test_liquid_numpy_feature_parity()
    else:
        print("⚠️ libliquid 不可用，跳过对拍（天选7 编译后自动纳入）")
    print("\n🎉 Phase 4 DSP 验收全部通过")
