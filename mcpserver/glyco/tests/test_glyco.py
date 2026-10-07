"""glyco 工具组验收（工单203 任务二）。

覆盖：GlycoCT 解析 / 组成统计 / 层次树 / IUPAC 方言边界（如实报错）/ GlyTouCan 网络降级 /
annotate_glycan 未配置模型时的 degraded / GlycoAgent 总线契约 / 未知工具容错。

⚠️ 实测口径（2026-10-07）：glypy 的 ``iupac`` 方言**不接受 CFG 简写**（``Man9GlcNAc2``）与常见
condensed 写法，均抛 ``IUPACError``；**可用路径为 GlycoCT**（RES/LIN）。测试按此实测行为断言。
"""
from __future__ import annotations

import asyncio
import json

from mcpserver.glyco import GlycoAgent
from mcpserver.glyco import tools as G

#: 实测可解析的最小 GlycoCT（Glc + Man，1→4 键）
GCT_TWO = "RES\n1b:x-dglc-HEX-1:5\n2b:b-dman-HEX-1:5\nLIN\n1:1o(4+1)2d\n"
#: 三残基（Glc ← Man ← Man）
GCT_THREE = ("RES\n1b:x-dglc-HEX-1:5\n2b:b-dman-HEX-1:5\n3b:a-dman-HEX-1:5\n"
             "LIN\n1:1o(4+1)2d\n2:2o(3+1)3d\n")


def test_parse_glycoct_ok():
    r = G.parse_glycan(GCT_TWO, "glycoct")
    assert r["status"] == "ok", r
    assert r["residue_count"] == 2
    assert r["total_mass"] and r["total_mass"] > 300
    assert sum(r["composition"].values()) == 2, r["composition"]


def test_parse_auto_prefers_glycoct():
    r = G.parse_glycan(GCT_THREE, "auto")
    assert r["status"] == "ok" and r["residue_count"] == 3, r


def test_cfg_shorthand_is_rejected_with_hint():
    """CFG 简写（工单举例的 Man9GlcNAc2）在 glypy 方言下不可解析 —— 必须报错并给提示，不得假装成功。"""
    r = G.parse_glycan("Man9GlcNAc2", "iupac")
    assert r["status"] == "error" and r["error"] == "parse_failed", r
    assert "GlycoCT" in r.get("hint", ""), r


def test_empty_and_bad_format():
    assert G.parse_glycan("")["error"] == "empty_input"
    assert G.parse_glycan(GCT_TWO, "nope")["error"].startswith("unknown_format")


def test_to_tree_structure():
    r = G.to_tree(GCT_THREE, "glycoct")
    assert r["status"] == "ok", r
    assert r["node_count"] >= 1 and r["max_depth"] >= 0
    assert all({"depth", "mass"} <= set(n) for n in r["nodes"]), r["nodes"]


def test_to_tree_propagates_parse_error():
    r = G.to_tree("Man9GlcNAc2", "iupac")
    assert r["status"] == "error", r


def test_glytoucan_lookup_degrades_without_network():
    """网络不可用时应返回 degraded（含原因），不得抛异常。"""
    r = G.glytoucan_lookup("G00054MO")
    assert r["status"] in ("ok", "degraded"), r
    if r["status"] == "degraded":
        assert "glytoucan_unreachable" in r["reason"]
    assert G.glytoucan_lookup("")["error"] == "empty_accession"


def test_annotate_glycan_reports_degraded_not_silent():
    """权重未配置 → degraded（明确原因），不得静默返回空结果。"""
    r = G.annotate_glycan(GCT_TWO, "glycoct")
    assert r["status"] == "degraded", r
    assert r["reason"] in ("annotation_model_not_configured",) or r["reason"].startswith("glycowork_unavailable")


def test_agent_contract_json():
    agent = GlycoAgent()
    out = asyncio.run(agent.handle_handoff({"tool": "parse_glycan",
                                            "params": {"text": GCT_TWO, "fmt": "glycoct"}}))
    assert isinstance(out, str)
    data = json.loads(out)
    assert data["status"] == "ok" and data["residue_count"] == 2


def test_agent_lists_tools_and_rejects_unknown():
    agent = GlycoAgent()
    listed = json.loads(asyncio.run(agent.handle_handoff({"tool": ""})))
    assert set(listed["available_tools"]) == set(G.TOOLS)
    bad = json.loads(asyncio.run(agent.handle_handoff({"tool": "nope"})))
    assert bad["status"] == "error" and bad["error"].startswith("unknown_tool")
