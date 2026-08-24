"""射频大脑 · 闭环编排（Phase 3）

感知 → 决策 → 解调 → BER 反馈 → 失败则用 alternatives 重试 → 最多 N 次。
这是"决策带反馈迭代"的核心，不是一次性判断。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mcpserver.rf_brain.decision_layer import decide
from mcpserver.rf_brain.demod_ref import demodulate
from mcpserver.rf_brain.feature_extractor import extract_features
from mcpserver.rf_brain.schemas import Decision, DemodFeedback, FeatureVector


@dataclass
class LoopResult:
    """闭环运行结果。"""
    modulation: str
    converged: bool                       # 是否收敛到正确解调
    attempts: int
    history: list[dict] = field(default_factory=list)  # 每轮决策 + 反馈
    protocol: str | None = None           # 协议叶子：解码器命中的协议（aprs/psk31/...）
    protocol_payload: dict | None = None  # 协议解码负载（文本/数字等）


def _probe_protocol(iq, sample_rate: float) -> tuple[str | None, dict | None]:
    """树的最末层：调制收敛后，用解码器注册表试全部协议，命中即收敛到叶子。

    解码器对纯噪声/陌生信号都返回失败结果（注册表健壮性保证），
    所以 probe 永远不抛异常；认不出协议返回 (None, None)——不误报。
    """
    from mcpserver.rf_brain.decoders import decode_all

    for r in decode_all(iq, sample_rate):
        if r.success:
            return r.decoder, r.payload
    return None, None


def run_loop(
    iq,
    sample_rate: float,
    center_freq: float,
    ground_truth_modulation: str | None = None,
    max_attempts: int = 3,
) -> LoopResult:
    """跑一轮完整闭环。

    ground_truth 仅用于测试断言，不参与闭环逻辑。
    """
    fv: FeatureVector = extract_features(iq, sample_rate=sample_rate, center_freq=center_freq)

    # 无有效信号 → 直接返回
    if not fv.is_valid_signal():
        return LoopResult(modulation="unknown", converged=False, attempts=0,
                          history=[{"phase": "感知", "result": "无有效信号（SNR 低于阈值）"}])

    tried: list[str] = []
    current_fv = fv

    for attempt in range(1, max_attempts + 1):
        decision: Decision = decide(current_fv)
        mod = decision.modulation
        if mod in tried:
            # 避免重复尝试同一调制
            alt = next((a["modulation"] for a in decision.alternatives if a["modulation"] not in tried), None)
            if alt is None:
                break
            mod = alt
        tried.append(mod)

        symbol_rate = decision.demod_params.get("symbol_rate_hz", 48000)
        feedback: DemodFeedback = demodulate(iq, mod, sample_rate, symbol_rate)

        entry = {
            "attempt": attempt,
            "modulation": mod,
            "confidence": decision.confidence,
            "demod_success": feedback.demod_success,
            "feedback": feedback.feedback,
        }

        if feedback.demod_success:
            protocol, payload = _probe_protocol(iq, sample_rate)
            return LoopResult(
                modulation=mod,
                converged=True,
                attempts=attempt,
                history=[entry],
                protocol=protocol,
                protocol_payload=payload,
            )

        # 失败 → 用 alternatives 下一候选，构造新的"决策"（简单：直接改候选）
        next_alt = next((a["modulation"] for a in decision.alternatives if a["modulation"] not in tried), None)
        if next_alt is None:
            return LoopResult(modulation=mod, converged=False, attempts=attempt, history=[entry])

        # 直接尝试下一候选（M1 简化：不重新过 LLM，避免过度设计）
        mod2 = next_alt
        tried.append(mod2)
        symbol_rate2 = decision.demod_params.get("symbol_rate_hz", 48000)
        fb2 = demodulate(iq, mod2, sample_rate, symbol_rate2)
        entry2 = {
            "attempt": attempt,
            "modulation": mod2,
            "confidence": decision.confidence,
            "demod_success": fb2.demod_success,
            "feedback": fb2.feedback,
        }
        if fb2.demod_success:
            protocol, payload = _probe_protocol(iq, sample_rate)
            return LoopResult(
                modulation=mod2,
                converged=True,
                attempts=attempt,
                history=[entry, entry2],
                protocol=protocol,
                protocol_payload=payload,
            )

    # 调制层全部失败 → 兜底探协议叶子：解调是玩具级（M1），认不出调制
    # 不代表不是协议信号——APRS/DTMF 等协议解码器独立于 demod_ref。
    protocol, payload = _probe_protocol(iq, sample_rate)
    return LoopResult(
        modulation=tried[-1] if tried else "unknown",
        converged=False,
        attempts=len(tried),
        history=[{"phase": "协议层", "protocol": protocol,
                  "result": f"调制未收敛，协议探针: {protocol or '未命中'}"}],
        protocol=protocol,
        protocol_payload=payload,
    )
