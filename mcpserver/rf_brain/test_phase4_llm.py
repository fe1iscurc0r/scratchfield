"""Phase 4 · LLM 接通端到端测试（需配置 RF_BRAIN_LLM_* 环境变量）

验证「真 LLM 决策」下的完整闭环：感知 → 特征 → LLM 决策 → 解调 → 反馈。
无环境变量时自动跳过 LLM，走规则兜底（保证 CI 不挂）。

跑法：
  export RF_BRAIN_LLM_BASE_URL=... RF_BRAIN_LLM_MODEL=... RF_BRAIN_LLM_API_KEY=...
  python3 mcpserver/rf_brain/test_phase4_llm.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcpserver.rf_brain.decision_layer import _llm_available
from mcpserver.rf_brain.loop import run_loop
from mcpserver.rf_brain.sensor import generate_iq


def main():
    if not _llm_available():
        print("⚠️ 未配置 RF_BRAIN_LLM_*，跳过 LLM 端到端（走规则兜底不影响 CI）")
        return

    print("=== LLM 接通端到端闭环 ===")
    results = {}
    for mod in ("GFSK", "FSK", "OOK"):
        iq = generate_iq(mod, snr_db=20.0, seed=42)
        r = run_loop(iq, sample_rate=2_000_000, center_freq=433_920_000, ground_truth_modulation=mod)
        results[mod] = r
        print(f"[{mod}] converged={r.converged} final={r.modulation} attempts={r.attempts}")

    # OOK 必须精确（envelope_cv 决定）
    assert results["OOK"].converged and results["OOK"].modulation == "OOK", "LLM 下 OOK 应精确识别"
    # GFSK/FSK 归大类
    for mod in ("GFSK", "FSK"):
        assert results[mod].converged, f"{mod} 应闭环收敛"
        assert results[mod].modulation in ("GFSK", "FSK"), f"{mod} 应收敛到恒定包络类"

    print("✅ LLM 端到端闭环通过（OOK 精确，GFSK/FSK 大类）")


if __name__ == "__main__":
    main()
