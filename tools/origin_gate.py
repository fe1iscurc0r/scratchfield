"""ROPE 确定性起源门控（A34 · NEKO 工具调用护栏）。

依据 round3 digest-g3-2026-08-31.md（2608.27496 ROPE 起源强制）：
「值必须不可伪造地溯源到用户或命名来源才可到达状态改变工具」的确定性起源
检查，比任何 LLM 判断更可靠（ASR 压至 1.6-2.6% 且保留 82-100% 干净效用）。

核心：不依赖模型自我仲裁，而是用**不可伪造的起源令牌**（HMAC）做确定性门控——
只有用户/用户命名来源能铸造有效令牌；模型或攻击者无法伪造。

原型（纯 stdlib，确定性）：
  - OriginGate：HMAC 铸造/校验起源令牌（source:value → token）
  - StateChangingTool：只有 verify 通过才执行状态改变
  - 对比：无门控工具 vs 门控工具，伪造来源注入成功率与正常通过率

验收（SPEC A34）：伪造来源注入成功率降 ≥50%，正常调用通过率 ≥90%。

运行：
  python tools/origin_gate.py
"""
from __future__ import annotations

import hashlib
import hmac
import random
from dataclasses import dataclass


@dataclass
class OriginGate:
    """确定性起源门控：HMAC 令牌不可伪造溯源。"""

    secret: bytes

    def mint(self, value: str, source: str = "user") -> str:
        """用户/命名来源铸造令牌。"""
        return hmac.new(self.secret, f"{source}:{value}".encode(), hashlib.sha256).hexdigest()

    def verify(self, value: str, source: str, token: str) -> bool:
        """确定性起源校验：令牌必须与 (source, value) 匹配。"""
        return hmac.compare_digest(self.mint(value, source), token)


class NaiveTool:
    """无门控工具（基线）：任何调用都执行。"""

    def __init__(self) -> None:
        self.executed = 0

    def execute(self, value: str, source: str, token: str) -> bool:
        self.executed += 1
        return True  # 不检查起源


class GatedTool:
    """门控工具：只有起源校验通过才执行。"""

    def __init__(self, gate: OriginGate) -> None:
        self.gate = gate
        self.executed = 0

    def execute(self, value: str, source: str, token: str) -> bool:
        if not self.gate.verify(value, source, token):
            return False
        self.executed += 1
        return True


def simulate(n_genuine: int = 100, n_forged: int = 100, corrupt_rate: float = 0.05, seed: int = 0) -> dict:
    """对比无门控 vs 门控：伪造注入成功率 + 正常通过率。"""
    gate = OriginGate(secret=b"neko-origin-gate-secret")
    naive = NaiveTool()
    gated = GatedTool(gate)
    rng = random.Random(seed)

    # 正常调用（含少量令牌损坏，模拟噪声信道）
    genuine_pass = 0
    for i in range(n_genuine):
        value = f"cmd-{i}"
        token = gate.mint(value, "user")
        if rng.random() < corrupt_rate:
            token = token[:-1] + ("0" if token[-1] != "0" else "1")  # 损坏令牌
        naive.execute(value, "user", token)
        genuine_pass += gated.execute(value, "user", token)

    # 伪造注入（攻击者伪造令牌）
    forge_pass_naive = 0
    forge_pass_gated = 0
    for i in range(n_forged):
        value = f"forged-{i}"
        fake_token = "0" * 64  # 伪造令牌（无有效 HMAC）
        forge_pass_naive += naive.execute(value, "user", fake_token)
        forge_pass_gated += gated.execute(value, "user", fake_token)

    return {
        "forge_success_naive": forge_pass_naive / n_forged,
        "forge_success_gated": forge_pass_gated / n_forged,
        "forge_reduction": 1.0 - (forge_pass_gated / n_forged) / max(forge_pass_naive / n_forged, 1e-9),
        "genuine_pass_rate": genuine_pass / n_genuine,
    }


def main() -> int:
    s = simulate()
    print(f"[伪造注入成功率] 无门控 {s['forge_success_naive']*100:.0f}% → 门控 {s['forge_success_gated']*100:.0f}%"
          f"（降 {s['forge_reduction']*100:.0f}%，验收要求 ≥50%）")
    print(f"[正常调用通过率] {s['genuine_pass_rate']*100:.1f}%（验收要求 ≥90%）")
    return 0 if s["forge_reduction"] >= 0.50 and s["genuine_pass_rate"] >= 0.90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
