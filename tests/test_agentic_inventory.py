"""`mcpserver.agentic_inventory` 的测试（工单249）。

四层：
  ① 姿态 `posture` —— 权重/档位/阈值 + **版本钉定判定**（7 个真实样本）
  ② 盘存 `inventory` —— 在**真实仓**上跑、行形状、指纹、信号
  ③ 对账与 diff —— 缺口的**真伪两侧**都要测（真缺口必须报、不适用必须不报）
  ④ 契约 `server` —— manifest ↔ 派发表 ↔ handle_handoff

⚠️ 本文件最重要的一条纪律：**报出的每一条缺口都要能被证伪**。
实测教训：第一版检测器拿 `_TOOLS`（本仓**部分**模块的约定）去判所有 bridge，
一口气报出 **41 个假缺口** —— 因此这里既有"真缺口必须报"的用例，也有"不适用不许报"的用例。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from mcpserver.agentic_inventory import inventory as inv
from mcpserver.agentic_inventory import posture
from mcpserver.agentic_inventory import server as ai_server

MODULE_DIR = Path(__file__).resolve().parents[1] / "mcpserver" / "agentic_inventory"
REPO_ROOT = Path(__file__).resolve().parents[1]


# ============================================================ ① 姿态


def test_score_weighted_sum_and_band():
    all_sig = dict.fromkeys(posture.SIGNAL_WEIGHTS, True)
    p = posture.score(all_sig)
    assert p.confidence == sum(posture.SIGNAL_WEIGHTS.values()) == 110
    assert p.band == posture.BAND_CATALOG and p.emitted is True
    assert p.signals == sorted(posture.SIGNAL_WEIGHTS)


def test_score_unknown_signal_raises():
    """未知信号必须报错 —— 否则加了信号忘了配权重时置信度会**悄悄偏低**。"""
    with pytest.raises(KeyError) as ei:
        posture.score({"manifest": True, "brand_new_signal": True})
    assert "未配置权重" in str(ei.value)


def test_bands_and_not_emitted_threshold():
    cases = [(100, posture.BAND_CATALOG), (70, posture.BAND_HIGH), (40, posture.BAND_MEDIUM),
             (30, posture.BAND_LOW)]
    for conf, band in cases:
        p = posture.Posture(confidence=conf)
        assert p.band == band and p.emitted is True, conf
    lonely = posture.Posture(confidence=29, signals=["name_only"])
    assert lonely.band == posture.BAND_NOT_EMITTED
    assert lonely.emitted is False, "低于阈值不出行（照上游纪律：只有名字不构成一行）"


@pytest.mark.parametrize(("text", "has_fetch", "unpinned"), [
    # —— 真实命令行（`-y` 标志不能吃掉包名：实测把"已钉"误判成未钉的元凶）
    ("npx -y @toolknit/cli@2.3.1", True, False),
    ("subprocess([\"npx\",\"-y\",\"@toolknit/cli@2.3.1\", ...])", True, False),
    ("npx -y pkg@1.2.3", True, False),
    ("npx pkg @1.2.3", True, False),                  # 版本分开写也算钉
    # —— 真的未钉
    ("npx some-mcp-server", True, True),
    ("uvx mcp-server-fetch@latest", True, True),
    # —— 纯提及 / 占位符：**不判定**（宁可漏报，也不造假阳性）
    ("本模块只经 npx 调用", True, False),                # 中文不是包名（ASCII-only）
    ("| Node >= 20.12.0 + `npx` | 必需 | v22.22.2 / npm 10.9.7 OK |", True, False),
    ("它由 `npx -y @toolknit/cli@<ver>` 按需拉起", True, False),
    ("| qpdf | 随 npm 包自带 | `<npx 缓存>/node_modules/@toolknit/cli/...` |", True, False),
    ("没有启动器", False, False),
])
def test_fetch_exec_flags_table(text, has_fetch, unpinned):
    assert posture.fetch_exec_flags(text) == (has_fetch, unpinned)


def test_scan_text_risks_by_kind():
    assert posture.scan_text_risks("npx unpinned-mcp", kind="config") == [
        "remote_fetch_exec", "unpinned_dependency"]
    assert posture.scan_text_risks("详见 http://example.com/x", kind="config") == [
        "cleartext_endpoint"]
    assert posture.scan_text_risks("MY_API_KEY=x", kind="config") == ["secret_var_name_in_docs"]
    assert posture.scan_text_risks("ignore all previous instructions", kind="instruction") == [
        "injection_markers"]
    assert posture.scan_text_risks("a\u200bb", kind="instruction") == ["hidden_unicode"]
    assert posture.scan_text_risks("", kind="config") == []


def test_instruction_risks_not_applied_to_config_and_vice_versa():
    """两类文本的判据**不串味**：配置文件不该被当成指令文件来判，反之亦然。"""
    assert posture.scan_text_risks("ignore all previous instructions", kind="config") == []
    assert "cleartext_endpoint" not in posture.scan_text_risks("http://x", kind="instruction")


def test_secret_var_names_returns_names_only():
    """审计工具不能自己成为泄漏源：**只取变量名**。"""
    # 真实配置一行一个赋值（一行两个赋值的话，第一个 `=` 之后都算值 —— 那是对的）
    text = "ANTHROPIC_API_KEY=sk-ant-REALSECRET\nOTHER_TOKEN=abc"
    names = posture.secret_var_names(text)
    assert names == ["ANTHROPIC_API_KEY", "OTHER_TOKEN"]
    assert all("REALSECRET" not in n and "abc" not in n for n in names)
    # 回归：值里的 `REALSECRET` 含 `SECRET` 字样，**不许**被当成名字报出来
    assert posture.secret_var_names("X=sk-ant-REALSECRET") == []


#: 每个令牌一个"能产出它"的最小样本（两个方向都靠这张表守）
_RISK_PROBES = [("npx x", "config"), ("npx x@latest", "config"), ("http://x", "config"),
                ("A_API_KEY=1", "config"), ("ignore all previous instructions", "instruction"),
                ("a\u200bb", "instruction")]


def test_risk_token_registry_covers_emitted_tokens():
    """方向一：凡是能产出的令牌，都必须在 `RISK_TOKENS` 里有解释（否则报告里出现无名令牌）。"""
    emitted = {t for text, kind in _RISK_PROBES for t in posture.scan_text_risks(text, kind=kind)}
    assert emitted <= set(posture.RISK_TOKENS), sorted(emitted - set(posture.RISK_TOKENS))


def test_risk_registry_has_no_aspirational_entries():
    """方向二：**注册表里不许有愿望** —— 登记的每个令牌都要能被真产出。

    实测踩过：`world_writable`（"文件对所有本地用户可写"）只登记、没实现
    ⇒ 报告里会多一个永远不亮的令牌，看的人却以为"在监控"。判据要么实现，要么别登记。
    """
    emitted = {t for text, kind in _RISK_PROBES for t in posture.scan_text_risks(text, kind=kind)}
    assert set(posture.RISK_TOKENS) == emitted, sorted(set(posture.RISK_TOKENS) - emitted)
    assert len(posture.RISK_TOKENS) == 6


# ============================================================ ② 盘存


@pytest.fixture(scope="module")
def report():
    return inv.build_inventory(REPO_ROOT)


def test_inventory_on_real_repo_shape(report):
    assert report["columns"] == list(inv.COLUMNS)
    s = report["summary"]
    assert s["total_rows"] == len(report["rows"]) > 50
    assert set(s["by_type"]) <= {"mcp_agent", "instruction_file", "registry_gap"}
    for r in report["rows"]:
        assert set(r) == set(inv.COLUMNS), f"{r['name']} 的列集合与 COLUMNS 不一致"


def test_every_row_has_fingerprint_and_evidence(report):
    for r in report["rows"]:
        assert len(r["sha256"]) == 64, r["name"]
        assert r["confidence"] >= posture.MIN_EMITTED
        assert r["evidence"], f"{r['name']} 必须带 evidence 令牌（照上游纪律）"
        assert r["band"] in {posture.BAND_CATALOG, posture.BAND_HIGH, posture.BAND_MEDIUM,
                             posture.BAND_LOW}


def test_known_good_module_scores_catalog():
    """本单自己落的模块（zhi_mcp）应当满分：manifest+entryPoint+契约+派发表+测试+README+requirements 全齐。"""
    rows = {r.name: r for r in inv.scan_agents(REPO_ROOT)}
    r = rows["zhi_mcp"]
    assert r.post.confidence == sum(posture.SIGNAL_WEIGHTS.values())
    assert r.post.band == posture.BAND_CATALOG
    assert r.post.quality_flags == []
    assert r.detail["dispatcher_checkable"] is True
    assert r.detail["declared_commands"] == r.detail["code_tools"]


def test_sha256_is_content_fingerprint(tmp_path):
    a = tmp_path / "mcpserver" / "m1"
    a.mkdir(parents=True)
    (a / "agent-manifest.json").write_text('{"name": "m1"}', encoding="utf-8")
    first = inv.scan_agents(tmp_path)[0]
    assert first.sha256 == hashlib.sha256(b'{"name": "m1"}').hexdigest()
    (a / "agent-manifest.json").write_text('{"name": "m1", "v": 2}', encoding="utf-8")
    second = inv.scan_agents(tmp_path)[0]
    assert second.sha256 != first.sha256, "内容变了指纹必须变"


def test_launch_hash_tracks_entrypoint(tmp_path):
    """启动向量指纹：entryPoint 变了就是变了（上游 launch_hash 的概念）。"""
    d = tmp_path / "mcpserver" / "m1"
    d.mkdir(parents=True)
    (d / "agent-manifest.json").write_text(json.dumps({
        "name": "m1", "agentType": "mcp",
        "entryPoint": {"module": "mcpserver.m1.server", "class": "BridgeA"}}), encoding="utf-8")
    h1 = inv.scan_agents(tmp_path)[0].launch_hash
    (d / "agent-manifest.json").write_text(json.dumps({
        "name": "m1", "agentType": "mcp",
        "entryPoint": {"module": "mcpserver.m1.server", "class": "BridgeB"}}), encoding="utf-8")
    h2 = inv.scan_agents(tmp_path)[0].launch_hash
    assert h1 != h2
    assert inv.launch_fingerprint("a.b", "C") == inv.launch_fingerprint("a.b", "C")


def test_invalid_manifest_yields_row_not_crash(tmp_path):
    d = tmp_path / "mcpserver" / "broken"
    d.mkdir(parents=True)
    (d / "agent-manifest.json").write_text("{not json", encoding="utf-8")
    rows = inv.scan_agents(tmp_path)
    assert len(rows) == 1 and rows[0].source == "manifest-invalid"
    assert "json_error" in rows[0].detail


def test_instruction_files_scanned(report):
    instr = [r for r in report["rows"] if r["type"] == "instruction_file"]
    assert instr, "仓内有 AGENTS.md，应被扫到"
    for r in instr:
        assert r["category"] == "agent-instruction"
        assert r["confidence"] == 100
        assert "size" in r["detail"]


def test_suppressed_rows_reported_in_summary():
    """低于阈值虽不出行，但**必须在 summary 里留名**（否则"没了"和"被抑制"分不清）。"""
    assert "suppressed_below_threshold" in build_summary_keys()


def build_summary_keys() -> set:
    return set(inv.build_inventory(REPO_ROOT)["summary"])


def test_type_filter(report):
    only_agents = [r for r in report["rows"] if r["type"] == "mcp_agent"]
    assert len(only_agents) == report["summary"]["by_type"]["mcp_agent"]


# ============================================================ ③ 对账与 diff（真伪两侧）


def test_reconcile_clean_on_real_repo(report):
    """真实仓当前**没有**缺口 —— 若有，说明要么真有问题、要么检测器又太严。"""
    gaps = [r for r in report["rows"] if r["type"] == "registry_gap"]
    assert gaps == [], f"真实仓出现缺口，需逐条查证（勿直接改判据放宽）：{[g['name'] for g in gaps]}"


def test_reconcile_reports_missing_handoff(tmp_path):
    """**真缺口必须报**：entryPoint 的类没有 handle_handoff ⇒ 注册器会拒。"""
    d = tmp_path / "mcpserver" / "nogood"
    d.mkdir(parents=True)
    (d / "server.py").write_text("class Bridge:\n    pass\n", encoding="utf-8")
    (d / "agent-manifest.json").write_text(json.dumps({
        "name": "nogood", "agentType": "mcp",
        "entryPoint": {"module": "mcpserver.nogood.server", "class": "Bridge"}}), encoding="utf-8")
    rows = inv.reconcile(inv.scan_agents(tmp_path))
    assert len(rows) == 1 and rows[0].name == "nogood"
    assert any("handle_handoff" in x for x in rows[0].detail["reasons"])
    assert "entryPoint" in rows[0].detail


def test_reconcile_reports_real_dispatcher_mismatch(tmp_path):
    """**真缺口必须报**：用了 `_TOOLS` 表、但表里的键与 manifest 声明不一致。"""
    d = tmp_path / "mcpserver" / "mismatch"
    d.mkdir(parents=True)
    (d / "server.py").write_text(
        "class Bridge:\n"
        "    _TOOLS = {'a': 'a'}\n"
        "    async def handle_handoff(self, task):\n"
        "        return ''\n", encoding="utf-8")
    (d / "agent-manifest.json").write_text(json.dumps({
        "name": "mismatch", "agentType": "mcp",
        "entryPoint": {"module": "mcpserver.mismatch.server", "class": "Bridge"},
        "capabilities": {"invocationCommands": [{"command": "a"}, {"command": "b"}]}}),
        encoding="utf-8")
    rows = inv.reconcile(inv.scan_agents(tmp_path))
    assert len(rows) == 1
    assert any("派发表不一致" in x for x in rows[0].detail["reasons"])


def test_reconcile_does_not_flag_uncheckable_dispatch(tmp_path):
    """**不适用不许报**（这条正是那 41 个假缺口的守卫）：没 `_TOOLS` 表的 bridge 不算缺口。"""
    d = tmp_path / "mcpserver" / "otherstyle"
    d.mkdir(parents=True)
    (d / "server.py").write_text(
        "class Bridge:\n"
        "    async def handle_handoff(self, task):\n"
        "        tools = {'a', 'b'}\n"          # 另一种派发风格，没有 _TOOLS
        "        return ''\n", encoding="utf-8")
    (d / "agent-manifest.json").write_text(json.dumps({
        "name": "otherstyle", "agentType": "mcp",
        "entryPoint": {"module": "mcpserver.otherstyle.server", "class": "Bridge"},
        "capabilities": {"invocationCommands": [{"command": "a"}, {"command": "b"}]}}),
        encoding="utf-8")
    rows = inv.scan_agents(tmp_path)
    assert rows[0].detail["dispatcher_checkable"] is False
    assert "dispatcher_uncheckable" in rows[0].post.quality_flags
    assert inv.reconcile(rows) == [], "不适用必须**不**产出缺口"


def test_snapshot_and_diff_detect_launch_vector_change():
    old = {"mcp_agent:mcpserver/x/agent-manifest.json": {"type": "mcp_agent", "sha256": "a" * 64, "launch_hash": "h1", "confidence": 100,
                 "risk_flags": "", "quality_flags": ""}}
    new = {"mcp_agent:mcpserver/x/agent-manifest.json": {"type": "mcp_agent", "sha256": "a" * 64, "launch_hash": "h2", "confidence": 100,
                 "risk_flags": "", "quality_flags": ""},
           "mcp_agent:mcpserver/y/agent-manifest.json": {"type": "mcp_agent", "sha256": "b" * 64, "launch_hash": "h3", "confidence": 40,
                 "risk_flags": "cleartext_endpoint", "quality_flags": ""}}
    d = inv.diff_snapshots(old, new)
    assert d["added"] == ["mcp_agent:mcpserver/y/agent-manifest.json"] and d["removed"] == []
    assert [c["name"] for c in d["changed"]] == ["mcp_agent:mcpserver/x/agent-manifest.json"]
    assert d["launch_vector_changes"] == [
        "mcp_agent:mcpserver/x/agent-manifest.json"], "启动向量变了必须单独点名"


def test_snapshot_shape(report):
    snap = inv.snapshot(report)
    assert len(snap) == len(report["rows"]), "快照键是 type:path ⇒ 行数与键数必须一一对应"
    assert all(":" in k for k in snap)
    # 回归：仓里有**三个** AGENTS.md（apiserver/、frontend/src/、mcpserver/）—— 按 name 做键会静默合并
    agents_md = [k for k in snap if k.endswith("AGENTS.md")]
    assert len(agents_md) == 3, agents_md
    for name, v in snap.items():
        assert set(v) == {"type", "sha256", "launch_hash", "confidence",
                          "risk_flags", "quality_flags"}


# ============================================================ ④ 契约层


def test_manifest_entrypoint_and_handoff_contract():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    assert d["agentType"] == "mcp"
    ep = d["entryPoint"]
    mod = __import__(ep["module"], fromlist=["x"])
    cls = getattr(mod, ep["class"])
    assert callable(getattr(cls, "handle_handoff", None))


def test_manifest_commands_match_dispatch_table():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    declared = {c["command"] for c in d["capabilities"]["invocationCommands"]}
    assert declared == set(ai_server.AgenticInventoryBridge._TOOLS)


def test_bridge_inventory_and_filter():
    br = ai_server.AgenticInventoryBridge()
    full = br.inventory()["data"]
    assert full["summary"]["total_rows"] > 50
    only_instr = br.inventory(type_filter="instruction_file")["data"]
    assert all(r["type"] == "instruction_file" for r in only_instr["rows"])
    assert only_instr["summary"]["filtered_by"] == "instruction_file"


def test_bridge_risk_report_explains_tokens():
    rk = ai_server.AgenticInventoryBridge().risk_report()["data"]
    for token in rk["flag_counts"]:
        assert rk["tokens"][token] != "(未登记的令牌)", f"{token} 没有解释"


def test_bridge_column_spec_declares_what_we_dropped():
    spec = ai_server.AgenticInventoryBridge().column_spec()["data"]
    assert spec["diff_from_upstream"]["we_dropped"] == ["running", "pid", "port"]
    assert "隐私" in spec["diff_from_upstream"]["why"] or "家目录" in spec["diff_from_upstream"]["why"]
    assert spec["signal_weights"] == dict(sorted(posture.SIGNAL_WEIGHTS.items()))


def test_bridge_doctor_cannot_list():
    doc = ai_server.AgenticInventoryBridge().doctor()
    assert len(doc["cannot"]) == 4
    assert any("不报密钥的值" in x for x in doc["cannot"])


def test_bridge_snapshot_and_diff_roundtrip():
    br = ai_server.AgenticInventoryBridge()
    snap = br.snapshot()["data"]["snapshot"]
    same = br.diff(json.dumps(snap), json.dumps(snap))["data"]
    assert same == {"added": [], "removed": [], "changed": [], "launch_vector_changes": []}
    mutated = json.loads(json.dumps(snap))
    first = next(iter(mutated))
    mutated[first]["launch_hash"] = "tampered"
    d = br.diff(json.dumps(snap), json.dumps(mutated))["data"]
    assert d["launch_vector_changes"] == [first]


def test_handle_handoff_success_and_errors():
    br = ai_server.AgenticInventoryBridge()
    ok = json.loads(asyncio.run(br.handle_handoff({"tool_name": "column_spec"})))
    assert ok["status"] == "success"
    bad = json.loads(asyncio.run(br.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "未知工具" in bad["message"]
    wrong = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "inventory", "params": {"oops": 1}})))
    assert wrong["status"] == "error" and "参数错误" in wrong["message"]


def test_cli_main_runs(capsys):
    assert ai_server.main(["columns"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert ai_server.main(["risks"]) == 0
    capsys.readouterr()


def test_cli_diff_accepts_at_file(tmp_path, capsys):
    """`diff` 的两个入参可以用 `@文件` —— 真实快照 24 KB，**Windows 命令行放不下**。

    （证据目录就是靠这条路复跑的；不加这条就只能把 JSON 硬塞进 argv。）
    """
    key = "mcp_agent:mcpserver/x/agent-manifest.json"
    row = {"type": "mcp_agent", "sha256": "a" * 64, "launch_hash": "h1",
           "confidence": 100, "risk_flags": "", "quality_flags": ""}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({key: row}), encoding="utf-8")
    b.write_text(json.dumps({key: {**row, "launch_hash": "h2"}}), encoding="utf-8")
    assert ai_server.main(["diff", f"@{a}", f"@{b}"]) == 0
    d = json.loads(capsys.readouterr().out)["data"]
    assert d["launch_vector_changes"] == [key]
    # 不带 `@` ⇒ 仍按 JSON 文本处理（既有行为不变）
    assert ai_server.load_snapshot_arg('{"a": 1}') == '{"a": 1}'
    # `@` 指向不存在的文件 ⇒ **明确报错**，不许把字面 `@路径` 当成 JSON 文本静默处理
    with pytest.raises(FileNotFoundError):
        ai_server.load_snapshot_arg("@" + str(tmp_path / "nope.json"))


def test_diff_accepts_snapshot_tool_envelope():
    """`snapshot` 子命令**写出来的就是整份输出**（含 ok/tool/data）⇒ `diff` 必须能吃回去。

    否则用户得自己写一行拆壳代码才能把两个子命令接起来（旧版 README 就是这么绕的）。
    """
    key = "mcp_agent:mcpserver/x/agent-manifest.json"
    row = {"type": "mcp_agent", "sha256": "a" * 64, "launch_hash": "h1",
           "confidence": 100, "risk_flags": "", "quality_flags": ""}
    env = {"ok": True, "tool": "snapshot",
           "data": {"repo_root": ".", "count": 1, "snapshot": {key: row}}}
    tampered = json.loads(json.dumps(env))
    tampered["data"]["snapshot"][key]["launch_hash"] = "h2"
    br = ai_server.AgenticInventoryBridge()
    d = br.diff(json.dumps(env), json.dumps(tampered))["data"]
    assert d["launch_vector_changes"] == [key]
    # 内层形状（既有用法）**行为不变**
    assert ai_server.unwrap_snapshot({key: row}) == {key: row}
    assert ai_server.unwrap_snapshot(env) == {key: row}


def test_module_has_no_third_party_imports():
    allowed = {"__future__", "argparse", "ast", "asyncio", "dataclasses", "hashlib",
               "json", "logging", "pathlib", "re", "typing"}
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
