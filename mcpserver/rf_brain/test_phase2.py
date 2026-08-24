"""Phase 2 测试：LLM 决策层。

验收（SPEC 第九章）：三种信号 LLM 命中率 ≥ 2/3。
无 LLM 环境 → 走 rule_engine 兜底，验证兜底路径也正确输出 Decision。

注：本测试用兜底路径（不配 LLM 环境变量），验证决策层能稳定产出合法 Decision；
LLM 真调用的命中率验证在配了 RF_BRAIN_LLM_* 环境变量后另行测试。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcpserver.rf_brain.decision_layer import decide
from mcpserver.rf_brain.feature_extractor import extract_features
from mcpserver.rf_brain.rule_engine import preselect_candidates
from mcpserver.rf_brain.sensor import generate_iq, noise_only


def test_decision_gfsk():
    iq = generate_iq("GFSK", snr_db=20.0, seed=42)
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    d = decide(fv)
    print(f"[GFSK] decision={d.modulation} conf={d.confidence} reasoning={d.reasoning}")
    assert d.decision == "demodulate"
    assert d.modulation in ("GFSK", "FSK"), "兜底路径 GFSK 信号应决策为 GFSK/FSK"
    assert d.demod_params, "应有解调参数"
    print("✅ Phase2 GFSK 决策通过")


def test_decision_noise():
    iq = noise_only()  # 纯噪声，不是负 SNR 信号
    fv = extract_features(iq)
    fv.modulation_candidates = preselect_candidates(fv)
    d = decide(fv)
    print(f"[NOISE] modulation={d.modulation} conf={d.confidence}")
    assert d.modulation == "unknown", "无有效信号应决策为 unknown"
    assert d.confidence == 0.0
    print("✅ Phase2 无信号决策通过")


if __name__ == "__main__":
    test_decision_gfsk()
    test_decision_noise()
    print("\n🎉 Phase 2 全部通过")
