"""Phase 3 测试：闭环收敛。

验收（SPEC 第九章）：
- OOK（幅度键控）→ 必须收敛到 OOK（envelope_cv 可靠区分）
- GFSK / FSK（恒定包络频移键控）→ 收敛到 {GFSK, FSK} 任一个都算对

诚实边界：M1 合成信号里 GFSK 与 FSK 都是连续相位，频谱几乎一致，
频谱+包络特征下本质不可区分（区分需瞬时相位轨迹，属 Phase 4 接真底座）。
故 M1 把两者归为「恒定包络频移键控」大类。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcpserver.rf_brain.loop import run_loop
from mcpserver.rf_brain.sensor import generate_iq


def test_loop_convergence():
    results = {}
    for mod in ("GFSK", "FSK", "OOK"):
        iq = generate_iq(mod, snr_db=20.0, seed=42)
        r = run_loop(iq, sample_rate=2_000_000, center_freq=433_920_000, ground_truth_modulation=mod)
        results[mod] = r
        print(f"[{mod}] converged={r.converged} final_mod={r.modulation} attempts={r.attempts}")

    # 强断言：OOK 必须精确
    assert results["OOK"].converged, "OOK 应闭环收敛"
    assert results["OOK"].modulation == "OOK", f"OOK 最终调制应为 OOK，实际 {results['OOK'].modulation}"

    # 恒定包络大类：GFSK/FSK 收敛到 {GFSK, FSK} 任一即可
    for mod in ("GFSK", "FSK"):
        r = results[mod]
        assert r.converged, f"{mod} 应闭环收敛，实际 {r.modulation}/{r.converged}"
        assert r.modulation in ("GFSK", "FSK"), f"{mod} 应收敛到恒定包络频移键控类，实际 {r.modulation}"

    print("✅ Phase3 闭环收敛通过（OOK 精确区分，GFSK/FSK 归大类）")


if __name__ == "__main__":
    test_loop_convergence()
    print("\n🎉 Phase 3 全部通过")
