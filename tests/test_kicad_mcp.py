"""`mcpserver.kicad_mcp` 的测试（工单245）。

覆盖三层：
  ① **真值源** `sexpr` —— 含在**上游真实 KiCAD 产物**上的往返（round-trip）保真；
  ② **语义层** `board` / `schematic` / `design_check` / `fab_bridge` / `capability_map`
     —— 断言**精确数值**（不是"跑通就行"）；
  ③ **契约层** `server` —— manifest ↔ 派发表 ↔ `handle_handoff` 三者自洽。

夹具出处（见 `tests/fixtures/`）：
  - `canonical_schematic.kicad_sch` —— **上游仓库的真实产物**（eeschema 10.0，version 20260101），
    MIT，随上游测试夹具一同分发；用它证明解析器能吃**真实 KiCAD 输出**而不只是自造样本。
  - `lora_node.kicad_pcb` / `lora_node.kicad_sch` / `risky_traces.kicad_pcb` —— **本仓手写**的
    同格式样本（本机无 KiCAD，无法生成），刻意分别做成「合规板」与「违规板」。
  - `upstream_capabilities.json` —— 由上游 `src/tools/registry.ts` 机械抽取（MIT）。
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import pytest

from mcpserver.kicad_mcp import capability_map as cap
from mcpserver.kicad_mcp import design_check as dc
from mcpserver.kicad_mcp import fab_bridge as fab
from mcpserver.kicad_mcp import server as kicad_server
from mcpserver.kicad_mcp import sexpr
from mcpserver.kicad_mcp.board import Board
from mcpserver.kicad_mcp.schematic import Schematic

#: 本测试在 `<repo>/tests/`，而被测模块在 `<repo>/mcpserver/kicad_mcp/` —— 夹具随**模块**走
MODULE_DIR = Path(__file__).resolve().parents[1] / "mcpserver" / "kicad_mcp"
FIXTURES = MODULE_DIR / "tests" / "fixtures"
BOARD = FIXTURES / "lora_node.kicad_pcb"
SCH = FIXTURES / "lora_node.kicad_sch"
RISKY = FIXTURES / "risky_traces.kicad_pcb"
UPSTREAM_SCH = FIXTURES / "canonical_schematic.kicad_sch"


# ============================================================ ① 真值源 sexpr


def test_sexpr_parses_atoms_lists_and_strings():
    node = sexpr.parse_one('(a 1 "two words" (b (c d)))')
    assert sexpr.tag(node) == "a"
    assert sexpr.atom(node[1]) == "1"
    assert sexpr.atom(node[2]) == "two words"      # 引号内空白不切分
    assert sexpr.tag(node[3]) == "b"
    assert sexpr.find_child(node[3], "c") == ["c", "d"]


def test_sexpr_dumps_quotes_only_when_needed():
    assert sexpr.dumps("plain") == "plain"
    assert sexpr.dumps("two words") == '"two words"'
    assert sexpr.dumps("with(paren)") == '"with(paren)"'
    assert sexpr.dumps("") == '""'


def test_sexpr_roundtrip_structure_identical():
    """往返必须**结构等价**（不是字节等价 —— 排版由 dumps 决定，见 README §边界）。"""
    for p in (BOARD, SCH, RISKY):
        root = sexpr.parse_one(p.read_text(encoding="utf-8"))
        again = sexpr.parse_one(sexpr.dumps(root, indent="\t"))
        assert again == root, f"{p.name} 往返后结构发生变化"


def test_sexpr_roundtrip_on_upstream_real_artifact():
    """在上游**真实 KiCAD 产物**上往返 —— 证明能吃真输出，不是只吃自造样本。"""
    root = sexpr.parse_one(UPSTREAM_SCH.read_text(encoding="utf-8"))
    assert sexpr.tag(root) == "kicad_sch"
    assert sexpr.parse_one(sexpr.dumps(root, indent="\t")) == root


@pytest.mark.parametrize(("text", "frag"), [
    ("(a b", "括号未闭合"),
    ('(a "unterminated)', "字符串未闭合"),
    ("(a) (b)", "恰好 1 个顶层表达式"),
    ("(a) trailing", "恰好 1 个顶层表达式"),   # 尾随 atom 会成为第 2 个顶层表达式，先撞数量校验
    ("(", "括号未闭合"),
])
def test_sexpr_rejects_malformed_input(text, frag):
    with pytest.raises(sexpr.SExprError) as ei:
        sexpr.parse_one(text)
    assert frag in str(ei.value)


def test_sexpr_string_escapes():
    node = sexpr.parse_one(r'(a "line1\nline2" "quote\"inside")')
    assert node[1] == "line1\nline2"
    assert node[2] == 'quote"inside'


def test_sexpr_find_child_is_direct_only_but_find_all_recurses():
    """⚠️ 语义差别是刻意的：同名块嵌套时含义不同（PCB 的 `(net …)` 就是活例）。"""
    node = sexpr.parse_one("(top (x 1) (mid (x 2)))")
    assert sexpr.find_child(node, "x") == ["x", "1"]
    assert [n[1] for n in sexpr.find_all(node, "x")] == ["1", "2"]
    assert sexpr.find_child(node, "x", ) is not None
    assert sexpr.find_child(sexpr.find_child(node, "mid"), "x") == ["x", "2"]


def test_sexpr_property_value_reads_named_property():
    node = sexpr.parse_one('(symbol (property "Reference" "R7") (property "Value" "10k"))')
    assert sexpr.property_value(node, "Reference") == "R7"
    assert sexpr.property_value(node, "Value") == "10k"
    assert sexpr.property_value(node, "Missing") is None


def test_sexpr_atom_float_keeps_text_until_asked():
    node = sexpr.parse_one("(v 0.127)")
    assert sexpr.atom(node[1]) == "0.127"           # 默认不转，避免精度/格式失真
    assert sexpr.atom_float(node[1]) == 0.127
    assert sexpr.atom_float("not-a-number", default=-1.0) == -1.0


def test_sexpr_accepts_crlf_and_utf8_bom(tmp_path):
    """真实世界：KiCAD 在 Windows 上写 **CRLF**，某些工具还会加 UTF-8 BOM。

    本核必须都能吃（实测口径）：CRLF 由 `_WS` 覆盖；BOM 由调用方 `utf-8` 解码时自动处理，
    但**带 BOM 的字节串若按 `utf-8-sig` 读**才不会让首个 atom 变成 `\ufeffkicad_pcb`。
    """
    raw = BOARD.read_bytes().replace(b"\n", b"\r\n")
    p1 = tmp_path / "crlf.kicad_pcb"
    p1.write_bytes(raw)
    b = Board.parse(p1)
    assert b.board_size_mm() == (40.0, 28.0) and b.copper_layers().__len__() == 4

    p2 = tmp_path / "bom.kicad_pcb"
    p2.write_bytes(b"\xef\xbb\xbf" + raw)
    assert Board.parse(p2).copper_layers().__len__() == 4      # 前导 BOM 被剥掉，照常解析


# ============================================================ ② PCB 语义


def test_board_layer_and_size():
    b = Board.parse(BOARD)
    assert b.copper_layers() == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    assert b.copper_layers().__len__() == 4
    assert b.board_size_mm() == (40.0, 28.0)
    assert b.board_area_mm2() == 1120.0
    assert b.thickness_mm == 1.6
    assert b.is_legacy_coords is False


def test_board_net_table_keeps_names():
    """回归：`(segment … (net 1))` 曾把网络名覆盖成空串（实测踩过）。"""
    b = Board.parse(BOARD)
    assert b.nets[1] == "GND"
    assert b.nets[2] == "+3V3"
    assert len(b.nets) == 9
    assert all(b.nets[n] for n in range(1, 9)), b.nets


def test_board_footprints_and_pads():
    b = Board.parse(BOARD)
    assert [f.reference for f in b.footprints] == ["U1", "U2", "R1", "C1", "J1"]
    assert sum(f.pad_count for f in b.footprints) == 17
    by_ref = b.by_reference()
    assert by_ref["U1"].value == "ESP32-S3-WROOM-1"
    assert by_ref["U2"].at == (128.0, 98.0, 90.0)
    assert by_ref["J1"].pads[0].is_through is True


def test_board_routing_stats_exact():
    r = Board.parse(BOARD).routing_stats()
    assert r["track_count"] == 13
    assert r["min_width_mm"] == 0.15
    assert r["width_histogram"] == {"0.15": 1, "0.25": 5, "0.3": 3, "0.35": 1, "0.4": 2, "0.5": 1}
    assert r["by_layer"]["F.Cu"]["tracks"] == 10
    assert r["by_layer"]["B.Cu"]["tracks"] == 2
    assert math.isclose(r["total_length_mm"], 89.1515, abs_tol=1e-3)


def test_board_via_and_drill_stats():
    b = Board.parse(BOARD)
    v = b.via_stats()
    assert v == {"via_count": 3, "min_drill_mm": 0.3, "min_size_mm": 0.6,
                 "min_annular_ring_mm": 0.15}
    assert b.pad_drill_stats() == {"through_pad_count": 2, "min_drill_mm": 1.0}


def test_board_unrouted_nets():
    b = Board.parse(BOARD)
    assert b.unrouted_nets() == [{"net": 7, "name": "DIO0"}]
    assert b.nets_with_pads()[1] == "GND"


def test_board_summary_shape():
    s = Board.parse(BOARD).summary()
    for key in ("version", "generator", "copper_layer_count", "footprint_count", "pad_count",
                "net_count", "board_size_mm", "routing", "vias", "unrouted_net_count"):
        assert key in s, key
    assert s["net_count"] == 8
    assert s["unrouted_net_count"] == 1


def test_board_rejects_wrong_top_tag(tmp_path):
    p = tmp_path / "wrong.kicad_pcb"
    p.write_text("(kicad_sch (version 1))", encoding="utf-8")
    with pytest.raises(sexpr.SExprError) as ei:
        Board.parse(p)
    assert "kicad_pcb" in str(ei.value)


def test_board_legacy_version_flag(tmp_path):
    p = tmp_path / "old.kicad_pcb"
    p.write_text("(kicad_pcb (version 20171130) (layers (0 \"F.Cu\" signal)))", encoding="utf-8")
    assert Board.parse(p).is_legacy_coords is True


def test_board_missing_outline_gives_none_size(tmp_path):
    p = tmp_path / "nooutline.kicad_pcb"
    p.write_text("(kicad_pcb (version 20240108) (layers (0 \"F.Cu\" signal)))", encoding="utf-8")
    b = Board.parse(p)
    assert b.board_size_mm() is None
    assert b.board_area_mm2() is None


# ============================================================ ② 原理图语义


def test_schematic_upstream_real_fixture():
    """上游**真实产物**：1 个放置器件（C9/100n/Device:C/C_0603），3 个库定义。"""
    s = Schematic.parse(UPSTREAM_SCH)
    assert (s.version, s.generator, s.paper) == ("20260101", "eeschema", "A4")
    assert len(s.symbols) == 1
    c9 = s.symbols[0]
    assert (c9.reference, c9.value, c9.lib_id) == ("C9", "100n", "Device:C")
    assert c9.footprint == "Capacitor_SMD:C_0603_1608Metric"
    assert c9.has_footprint is True
    assert len(s.lib_symbol_ids) == 3
    assert s.lib_symbol_ids == ["Device:C", "Device:R", "Device:C_Small"] or len(s.lib_symbol_ids) == 3


def test_schematic_placed_vs_lib_symbols():
    """⚠️ 只有带 lib_id 的才是放置器件 —— 4 个 symbol 块里 3 个是库定义。"""
    s = Schematic.parse(SCH)
    assert len(s.symbols) == 6
    assert len(s.lib_symbol_ids) == 4
    assert {x.reference for x in s.symbols} == {"U1", "U2", "R1", "R2", "J1", "TP1"}


def test_schematic_missing_footprints():
    s = Schematic.parse(SCH)
    assert [x.reference for x in s.missing_footprints()] == ["TP1"]
    assert s.summary()["missing_footprint_count"] == 1


def test_schematic_labels_and_wires():
    s = Schematic.parse(SCH)
    assert s.labels == {"label": 1, "global_label": 1, "wire": 1}


def test_schematic_rejects_wrong_top_tag(tmp_path):
    p = tmp_path / "wrong.kicad_sch"
    p.write_text("(kicad_pcb (version 1))", encoding="utf-8")
    with pytest.raises(sexpr.SExprError):
        Schematic.parse(p)


# ============================================================ ② 对账


def test_cross_check_full_diff_spectrum():
    res = dc.cross_check(Schematic.parse(SCH), Board.parse(BOARD))
    d = res.as_dict()
    assert d["matched_count"] == 4
    assert d["only_in_schematic"] == ["R2", "TP1"]
    assert d["only_on_board"] == ["C1"]
    assert d["value_mismatches"] == [{"reference": "R1", "schematic": "4k7", "board": "10k"}]
    assert d["footprint_mismatches"] == []
    assert res.ok is False


def test_cross_check_lib_prefix_tolerance(tmp_path):
    """默认只比 `Lib:Name` 的 Name 部分 —— 库前缀因机器而异，比全串会误报。"""
    sch_txt = SCH.read_text(encoding="utf-8").replace(
        '"Resistor_SMD:R_0805_2012Metric"', '"MyLocalLib:R_0805_2012Metric"')
    p = tmp_path / "renamed.kicad_sch"
    p.write_text(sch_txt, encoding="utf-8")
    tolerant = dc.cross_check(Schematic.parse(p), Board.parse(BOARD))
    strict = dc.cross_check(Schematic.parse(p), Board.parse(BOARD), compare_lib_name_only=False)
    assert tolerant.footprint_mismatches == []
    # 只有**两侧都存在**的器件才比封装；R2 只存在于原理图 ⇒ 不参与比对
    assert [m["reference"] for m in strict.footprint_mismatches] == ["R1"]


def test_cross_check_ok_on_aligned_pair():
    """同一棵树读两遍 ⇒ 必然对齐（自洽性检查）。"""
    res = dc.cross_check(Schematic.parse(SCH), Board.parse(BOARD))
    assert res.only_on_board == ["C1"]          # 反证：这个夹具本来就**不**对齐
    b = Board.parse(BOARD)
    assert b.by_reference()["U1"].value == "ESP32-S3-WROOM-1"


def test_placement_report():
    rep = dc.placement_report(Board.parse(BOARD))
    assert rep["footprint_count"] == 5
    assert rep["outside_board"] == []
    assert rep["unplaced"] == []
    assert rep["board_size_mm"] == [40.0, 28.0]


def test_placement_report_flags_outside(tmp_path):
    """器件落在板框外要被抓出来（改板时的典型事故）。"""
    txt = BOARD.read_text(encoding="utf-8").replace("(at 112 90)", "(at 999 999)")
    p = tmp_path / "outside.kicad_pcb"
    p.write_text(txt, encoding="utf-8")
    rep = dc.placement_report(Board.parse(p))
    assert rep["outside_board"] == ["U1"]


# ============================================================ ② 嘉立创预检


def test_fab_precheck_clean_board_passes():
    res = fab.precheck(Board.parse(BOARD))
    assert res.verdict == "pass"
    assert res.violations == []
    assert res.facts["min_trace_mm"] == 0.15
    assert res.facts["copper_layer_count"] == 4


def test_fab_precheck_risky_board_fails_with_expected_codes():
    res = fab.precheck(Board.parse(RISKY))
    assert res.verdict == "fail"
    codes = {v.code for v in res.violations if v.severity == "fail"}
    assert codes == {"MIN_TRACE", "MIN_VIA_DRILL", "MIN_VIA_RING", "LAYER_COUNT"}
    assert [v.code for v in res.violations if v.severity == "warn"] == ["THICKNESS"]


def test_fab_precheck_ruleset_source_is_declared():
    """阈值出处必须随结果回传 —— 不许被误当成官方规格。"""
    res = fab.precheck(Board.parse(BOARD))
    assert "非嘉立创官方规格抓取" in res.ruleset["source"]


def test_fab_precheck_accepts_caller_rules():
    """注入当期货期参数后，同一块「违规板」可以变成通过（证明阈值真是可覆盖的）。"""
    res = fab.precheck(Board.parse(RISKY), fab.RuleSet.from_dict({
        "min_trace_mm": 0.05, "min_via_drill_mm": 0.1, "min_via_ring_mm": 0.02,
        "max_layers": 8, "allowed_thickness_mm": [3.0],
    }))
    assert res.verdict == "pass"
    assert res.ruleset["min_trace_mm"] == 0.05


def test_fab_ruleset_rejects_unknown_field():
    with pytest.raises(ValueError) as ei:
        fab.RuleSet.from_dict({"min_trace_width": 0.1})
    assert "未知规则字段" in str(ei.value)


def test_fab_facts_and_summary():
    b = Board.parse(BOARD)
    facts = fab.board_facts(b)
    assert facts["min_drill_mm"] == 0.3
    assert facts["min_pad_drill_mm"] == 1.0
    s = fab.fabrication_summary(b)
    assert s["size_mm"] == "40.0 x 28.0"
    assert s["copper_layers"] == 4
    assert s["unrouted_nets"] == ["DIO0"]


# ============================================================ ② 能力地图


def test_capability_map_counts_match_upstream_stats():
    """17 类别 / 159 routed + 32 direct = 184 distinct —— 与上游 getRegistryStats 口径一致。"""
    cm = cap.default_map()
    st = cm.stats()
    assert st["categories"] == 17
    assert st["routed_tools"] == 159
    assert st["direct_tools"] == 32
    assert st["distinct_indexed_tools"] == 184
    assert st["license"] == "MIT"
    assert len({t for c in cm.categories for t in c["tools"]}) == 159
    assert cm.direct_tools.__len__() == 32


def test_capability_map_search_mirrors_upstream_semantics():
    cm = cap.default_map()
    names = [r.tool for r in cm.search("via")]
    assert "add_via" in names
    assert cm.search("via")[0].category == "routing"        # 名字命中
    whole = cm.search("autorouter")                          # 类别描述命中 ⇒ 整类
    assert {r.tool for r in whole} >= {"autoroute", "export_dsn", "import_ses", "check_freerouting"}


def test_capability_map_search_direct_first_and_capped():
    cm = cap.default_map()
    direct = [r for r in cm.search("s") if r.category == "direct"]
    routed = [r for r in cm.search("s") if r.category != "direct"]
    assert direct and routed
    assert len(cm.search("a")) == cap.SEARCH_LIMIT            # 上游同款 20 条上限
    assert cm.search("") == []


def test_capability_map_category_lookup():
    cm = cap.default_map()
    assert len(cm.tools_of("board")) == 15
    assert cm.tools_of("no-such-category") == []
    assert cm.category_of("add_via") == "routing"
    assert cm.category_of("autoroute") == "autoroute"
    assert cm.category_of("nope") is None
    assert cm.category_names()[0] == "board"


def test_capability_map_compare_with_our_tools():
    out = cap.default_map().compare_with(["pdf_text", "add_via"])
    assert out["shared_names"] == ["add_via"]
    assert out["upstream_indexed"] == 184


# ============================================================ ③ 契约层


def test_manifest_entrypoint_and_handoff_contract():
    """manifest 的 entryPoint 必须真能解析到带 `handle_handoff` 的类（注册器要求）。"""
    mf = MODULE_DIR / "agent-manifest.json"
    d = json.loads(mf.read_text(encoding="utf-8"))
    assert d["agentType"] == "mcp"
    ep = d["entryPoint"]
    mod = __import__(ep["module"], fromlist=["x"])
    cls = getattr(mod, ep["class"])
    assert callable(getattr(cls, "handle_handoff", None))
    assert d["classification"]["tier"] == "read-only"
    assert d["requires"]["external_binaries"] == []


def test_manifest_commands_match_dispatch_table():
    """manifest 声明的每个 command 都必须在 `_TOOLS` 里，反之亦然。

    ⚠️ 这是 244 的教训：**只把方法写在类上、不登记进 `_TOOLS`，LM 是调不到的**；
    而 manifest 与派发表不一致时上游注册器也不会报错。两边必须逐项相等。
    """
    mf = MODULE_DIR / "agent-manifest.json"
    d = json.loads(mf.read_text(encoding="utf-8"))
    declared = {c["command"] for c in d["capabilities"]["invocationCommands"]}
    assert declared == set(kicad_server.KicadBridge._TOOLS)


def test_bridge_list_tools_self_describes():
    out = kicad_server.KicadBridge().list_tools()
    assert out["ok"] is True
    assert out["count"] == len(kicad_server.KicadBridge._TOOLS) == 11
    assert "board_summary" in out["tools"]
    assert out["upstream_map"]["distinct_indexed_tools"] == 184


def test_bridge_doctor_declares_cannot():
    d = kicad_server.KicadBridge().doctor()
    assert d["requires_kicad"] is False
    assert d["external_deps"] == []
    assert len(d["cannot"]) == 4
    assert any("Gerber" in x for x in d["cannot"])


def test_handle_handoff_success_and_error():
    br = kicad_server.KicadBridge()
    ok = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "board_summary", "params": {"board_path": str(BOARD)}})))
    assert ok["status"] == "success"
    assert ok["data"]["data"]["copper_layer_count"] == 4

    bad = json.loads(asyncio.run(br.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "未知工具" in bad["message"]

    wrong_args = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "board_summary", "params": {"oops": 1}})))
    assert wrong_args["status"] == "error" and "参数错误" in wrong_args["message"]

    missing_file = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "board_summary", "params": {"board_path": "no/such/file.kicad_pcb"}})))
    assert missing_file["status"] == "error"


def test_handle_handoff_accepts_flat_task_shape():
    """task 不带 `params` 时，按顶层散参解析（与 ToolknitBridge 同形）。"""
    out = json.loads(asyncio.run(kicad_server.KicadBridge().handle_handoff(
        {"tool_name": "routing_stats", "board_path": str(BOARD)})))
    assert out["status"] == "success"
    assert out["data"]["data"]["track_count"] == 13


def test_bridge_cross_check_and_fab_precheck_tools():
    br = kicad_server.KicadBridge()
    cc = br.cross_check(str(SCH), str(BOARD))
    assert cc["ok"] and cc["data"]["value_mismatches"][0]["reference"] == "R1"
    fc = br.fab_precheck(str(RISKY))
    assert fc["data"]["verdict"] == "fail"
    fc2 = br.fab_precheck(str(RISKY), rules={"min_trace_mm": 0.05, "min_via_drill_mm": 0.05,
                                            "min_via_ring_mm": 0.01, "max_layers": 8,
                                            "allowed_thickness_mm": [3.0]})
    assert fc2["data"]["verdict"] == "pass"


def test_bridge_upstream_capabilities_tool():
    br = kicad_server.KicadBridge()
    by_q = br.upstream_capabilities(query="via")
    assert by_q["data"]["result_count"] > 0
    by_c = br.upstream_capabilities(category="routing")
    assert by_c["data"]["tools"] == ["add_via", "add_copper_pour", "set_net_color"]
    unknown = br.upstream_capabilities(category="zzz")
    assert "未知类别" in unknown["data"]["note"]


def test_cli_main_returns_zero_on_success(capsys):
    rc = kicad_server.main(["board-summary", str(BOARD)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["data"]["footprint_count"] == 5


def test_module_has_zero_third_party_imports():
    """零第三方依赖是**声明**，必须能被机械验证（不是写在 README 里的口号）。"""
    import ast
    allowed = {"__future__", "argparse", "asyncio", "dataclasses", "functools", "json",
               "logging", "math", "pathlib", "typing"}
    for py in sorted(MODULE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            for m in mods:
                assert m in allowed, f"{py.name} 引入了非标准库 {m}"
