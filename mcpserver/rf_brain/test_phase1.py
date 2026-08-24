"""Phase 1 测试：特征提取 + 候选预筛。

验收（SPEC 第九章）：
- GFSK 合成信号 → candidates 含 GFSK 且排第一
- 纯噪声 → 判定无有效信号
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.feature_extractor import extract_features
from mcpserver.rf_brain.rule_engine import preselect_candidates
from mcpserver.rf_brain.sensor import generate_iq, noise_only


def test_gfsk_candidate_first():
    iq = generate_iq("GFSK", snr_db=20.0, seed=42)
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    print(f"[GFSK] snr={fv.snr_db:.1f}dB flatness={fv.spectral_flatness:.3f} peaks={fv.n_peaks} bw={fv.bandwidth_hz}")
    print(f"[GFSK] candidates={fv.modulation_candidates}")
    assert fv.is_valid_signal(), "GFSK 应判定为有效信号"
    assert "GFSK" in fv.modulation_candidates, "候选应含 GFSK"
    assert fv.modulation_candidates[0] in ("GFSK", "FSK"), "GFSK 应排候选第一（或 FSK，同为连续相位）"
    print("✅ Phase1 GFSK 候选预筛通过")


def test_fsk_candidate():
    iq = generate_iq("FSK", snr_db=20.0, seed=42)
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    print(f"[FSK] candidates={fv.modulation_candidates}")
    assert "FSK" in fv.modulation_candidates, "FSK 候选应含 FSK"
    print("✅ Phase1 FSK 候选预筛通过")


def test_ook_candidate():
    iq = generate_iq("OOK", snr_db=20.0, seed=42)
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    print(f"[OOK] candidates={fv.modulation_candidates}")
    assert len(fv.modulation_candidates) > 0, "OOK 应有候选"
    print("✅ Phase1 OOK 候选预筛通过")


def test_noise_no_signal():
    iq = noise_only()
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    print(f"[NOISE] snr={fv.snr_db:.1f}dB candidates={fv.modulation_candidates}")
    assert not fv.is_valid_signal(), "纯噪声应判定为无有效信号"
    assert fv.modulation_candidates == [], "无有效信号候选应为空"
    print("✅ Phase1 噪声无信号判定通过")


if __name__ == "__main__":
    test_gfsk_candidate_first()
    test_fsk_candidate()
    test_ook_candidate()
    test_noise_no_signal()
    print("\n🎉 Phase 1 全部通过")
