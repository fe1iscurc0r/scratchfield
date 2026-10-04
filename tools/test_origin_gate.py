"""origin_gate 测试（A34 验收：伪造来源注入成功率降 ≥50%，正常通过率 ≥90%）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from origin_gate import GatedTool, NaiveTool, OriginGate, simulate


def test_mint_verify_roundtrip():
    gate = OriginGate(secret=b"secret")
    tok = gate.mint("v1", "user")
    assert gate.verify("v1", "user", tok)
    assert not gate.verify("v2", "user", tok)  # 值不同 → 校验失败
    assert not gate.verify("v1", "attacker", tok)  # 来源不同 → 校验失败


def test_forged_origin_denied():
    gate = OriginGate(secret=b"secret")
    tool = GatedTool(gate)
    assert tool.execute("x", "user", "0" * 64) is False  # 伪造令牌被拒


def test_genuine_origin_allowed():
    gate = OriginGate(secret=b"secret")
    tool = GatedTool(gate)
    tok = gate.mint("x", "user")
    assert tool.execute("x", "user", tok) is True


def test_metrics_meet_acceptance():
    s = simulate(seed=0)
    assert s["forge_reduction"] >= 0.50, f"伪造降幅 {s['forge_reduction']*100:.0f}% 不达标"
    assert s["genuine_pass_rate"] >= 0.90, f"正常通过率 {s['genuine_pass_rate']*100:.1f}% 不达标"


def test_named_source_provenance():
    """ROPE 核心语义：值必须溯源到用户「或用户命名来源」。"""
    gate = OriginGate(secret=b"secret")
    tool = GatedTool(gate)
    # 用户命名来源 "radio-config" 铸造有效令牌 → 通过
    tok = gate.mint("freq=146.52", source="radio-config")
    assert tool.execute("freq=146.52", "radio-config", tok) is True
    # 攻击者伪造令牌（来源声称 radio-config）→ 拒绝
    assert tool.execute("freq=146.52", "radio-config", "0" * 64) is False
    # 令牌与来源不匹配（user 铸造却声称 radio-config）→ 拒绝
    wrong = gate.mint("freq=146.52", source="user")
    assert tool.execute("freq=146.52", "radio-config", wrong) is False
