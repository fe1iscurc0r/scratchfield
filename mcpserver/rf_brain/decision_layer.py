"""射频大脑 · LLM 决策层（Phase 2）

输入 FeatureVector → 构造 prompt → 调 LLM → 解析 Decision。
LLM 只做候选排序 + 参数细化，候选由 rule_engine 提供。
LLM 不可用/超时 → 用 rule_engine 的 top-1 兜底，保证闭环不停摆。

provider 无关：读环境变量，不硬编码。
"""
from __future__ import annotations

import json
import os
import re

from mcpserver.rf_brain.rule_engine import preselect_candidates
from mcpserver.rf_brain.schemas import Decision, FeatureVector

# 环境变量（provider 无关）
_LLM_BASE_URL = os.environ.get("RF_BRAIN_LLM_BASE_URL", "")
_LLM_API_KEY = os.environ.get("RF_BRAIN_LLM_API_KEY", "")
_LLM_MODEL = os.environ.get("RF_BRAIN_LLM_MODEL", "")


def _llm_available() -> bool:
    return bool(_LLM_BASE_URL and _LLM_MODEL)


def _build_prompt(fv: FeatureVector, candidates: list[str]) -> str:
    """构造决策 prompt，few-shot + 强制 JSON 输出。"""
    few_shot = """你是射频信号分析专家。根据频谱特征向量，从候选调制方式中选最可能的一种，并给出解调参数。

关键判据：
- envelope_cv（包络变异系数）> 0.3 → 幅度键控 OOK（包络剧烈波动）；< 0.15 → 恒定包络 FSK/GFSK
- freq_transition_slope（瞬时频率跳变指标）> 0.13 → FSK 硬切换；≤ 0.13 → GFSK 高斯平滑（恒定包络内部细分；SNR 低时不可靠）
- flatness > 0.5 → 接近噪声；< 0.05 → 频谱高度集中（有调制）
- 注意 n_peaks 可能有假峰，envelope_cv 才是区分 OOK 的决定性特征

示例1：
输入：{"envelope_cv": 0.07, "bandwidth": 125000, "snr_db": 18.5, "flatness": 0.72, "n_peaks": 1, "candidates": ["GFSK", "FSK"]}
输出：{"modulation": "GFSK", "reasoning": "envelope_cv=0.07恒定包络，排除OOK；单峰窄带，GFSK", "confidence": 0.85}

示例2：
输入：{"envelope_cv": 0.85, "n_peaks": 34, "candidates": ["OOK", "FSK", "GFSK"]}
输出：{"modulation": "OOK", "reasoning": "envelope_cv=0.85包络剧烈波动，幅度键控，OOK", "confidence": 0.9}
"""
    data = {
        "peak_freq_hz": fv.peak_freq_hz,
        "bandwidth_hz": fv.bandwidth_hz,
        "snr_db": round(fv.snr_db, 1),
        "flatness": round(fv.spectral_flatness, 3),
        "envelope_cv": round(fv.envelope_cv, 3),
        "freq_transition_slope": round(fv.freq_transition_slope, 4) if fv.freq_transition_slope is not None else None,
        "n_peaks": fv.n_peaks,
        "peak_separation_hz": fv.peak_separation_hz,
        "symbol_rate_estimate_hz": fv.symbol_rate_estimate_hz,
        "candidates": candidates,
    }
    return (
        few_shot
        + "\n现在分析这个信号：\n"
        + json.dumps(data, ensure_ascii=False)
        + "\n只输出一个 JSON 对象，包含 modulation / reasoning / confidence 三个字段，不要输出任何其他文字。"
    )


def _call_llm(prompt: str) -> dict | None:
    """调用 OpenAI 兼容接口（provider 无关），失败返回 None。"""
    import urllib.request

    payload = {
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        f"{_LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_LLM_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
        # 提取 JSON 对象
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return None
    except Exception:
        return None


def _fallback_decision(fv: FeatureVector, candidates: list[str]) -> Decision:
    """LLM 兜底：用 rule_engine top-1。"""
    mod = candidates[0] if candidates else "unknown"
    return Decision(
        decision="demodulate",
        modulation=mod,
        demod_params=_default_params(mod, fv),
        confidence=0.5,
        reasoning=f"规则引擎兜底（LLM 不可用）：top-1 候选 {mod}",
        alternatives=[{"modulation": c, "confidence": 0.5 / (i + 2)} for i, c in enumerate(candidates[1:], start=1)],
    )


def _default_params(modulation: str, fv: FeatureVector) -> dict:
    """根据调制方式给默认解调参数。

    symbol_rate 不盲信带宽估计：OOK 基带含直流偏置（0/1 电平），-3dB 带宽
    测量会退化到单 FFT bin（如 500Hz），作为符号率会使解调 sps 过大、符号
    不足而失败。故只在合理区间 [1k, 200k] 内取估计值，否则回落到传感器
    默认符号率 48k（M1 合成信号固定 48k）。
    """
    est = fv.symbol_rate_estimate_hz
    if not (est and 1_000 <= est <= 200_000):
        est = 48_000.0
    return {
        "symbol_rate_hz": est,
        "filter_bandwidth_hz": fv.bandwidth_hz or 125000,
        "decimation": 4,
        "center_offset_hz": 0,
    }


def decide(fv: FeatureVector) -> Decision:
    """决策入口：读特征 → 候选 → LLM（或兜底）→ Decision。"""
    candidates = fv.modulation_candidates or preselect_candidates(fv)
    if not candidates:
        return Decision(
            decision="demodulate",
            modulation="unknown",
            demod_params={},
            confidence=0.0,
            reasoning="无有效信号，无候选调制方式",
            alternatives=[],
        )

    if _llm_available():
        prompt = _build_prompt(fv, candidates)
        result = _call_llm(prompt)
        if result:
            mod = str(result.get("modulation", "")).upper()
            if mod not in {c.upper() for c in candidates}:
                mod = candidates[0]  # LLM 跑出候选外 → 拒绝，用 top-1
            return Decision(
                decision="demodulate",
                modulation=mod,
                demod_params=_default_params(mod, fv),
                confidence=float(result.get("confidence", 0.5)),
                reasoning=str(result.get("reasoning", "")),
                alternatives=[{"modulation": c, "confidence": 0.2} for c in candidates if c.upper() != mod],
            )

    return _fallback_decision(fv, candidates)
