"""射频大脑 · 规则引擎（Phase 1 骨架，Phase 4 补相位轨迹判据）

确定性规则预筛候选调制方式，作为 LLM 决策的输入和兜底。
LLM 只做排序 + 参数细化，不凭空猜候选——候选从这里来。

判据优先级（基于实测数据）：
1. 包络变异系数 envelope_cv：OOK 幅度键控 ~0.85，FSK/GFSK 恒定包络 ~0.07
2. 瞬时频率跳变速率 freq_transition_slope（Phase 4）：FSK 硬切换高，GFSK 高斯平滑低
3. 谱峰数量：双峰 → FSK 类
4. 频谱平坦度：低 → 集中（连续相位调制）
"""
from __future__ import annotations

from mcpserver.rf_brain.schemas import FeatureVector

# 实测标定（sensor 合成信号，SNR 15~30dB）：FSK 硬切换 ≈ 0.18~0.24，
# GFSK 高斯成形 ≈ 0.07~0.12；SNR≤10dB 时鉴频噪声淹没判据，两者重叠。
FSK_SLOPE_THRESHOLD = 0.13


def preselect_candidates(fv: FeatureVector) -> list[str]:
    """根据频谱 + 包络特征预筛候选调制方式（有序，第一位最可能）。"""
    if not fv.is_valid_signal():
        return []

    candidates: list[str] = []
    env_cv = fv.envelope_cv

    # 判据 1：包络变异系数区分幅度键控 vs 恒定包络
    if env_cv > 0.3:
        # 幅度键控（OOK）
        candidates.append("OOK")
        # 补充候选
        if fv.n_peaks >= 2:
            candidates.append("FSK")
        candidates.append("GFSK")
    else:
        # 恒定包络（FSK/GFSK）
        slope = fv.freq_transition_slope
        if slope is not None:
            # Phase 4 主判据：瞬时相位轨迹——硬切换 vs 高斯平滑
            if slope > FSK_SLOPE_THRESHOLD:
                candidates.append("FSK")
                candidates.append("GFSK")
            else:
                candidates.append("GFSK")
                candidates.append("FSK")
        elif fv.n_peaks >= 2 and fv.peak_separation_hz and fv.peak_separation_hz > 0:
            candidates.append("FSK")
            candidates.append("GFSK")
        else:
            flatness = fv.spectral_flatness
            if flatness < 0.6:
                candidates.append("GFSK")
                candidates.append("FSK")
            else:
                candidates.append("FSK")
                candidates.append("GFSK")
        # OOK 作为第三候选兜底（恒定包络但可能误判）
        if len(candidates) < 3 and env_cv < 0.15:
            candidates.append("OOK")

    # 去重保序，最多 3 个
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:3]
