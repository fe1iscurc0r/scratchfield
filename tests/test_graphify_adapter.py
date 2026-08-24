"""graphify 知识图谱适配包功能测试（W-03 验收）。

验收口径：
1. 图谱生成 → graph.json 落盘（上游 schema：nodes/links/confidence）
2. 提问返回含引用来源的回答 —— json.dumps 结果含 '"citation"' 字段（grep 断言口径）
3. agent-manifest.json 含 license 字段（硬约束），scan_and_register 可注册
4. pytest 全过
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from mcpserver.adapters.graphify.adapter import GraphifyBridge
from mcpserver.adapters.graphify.engine import (
    EXTRACTED,
    GraphifyError,
    GraphifyGraph,
    extract_corpus,
)

# ---------------------------------------------------------------- fixtures

PY_UTIL = '''\
def parse_input(raw):
    """解析输入"""
    return raw.strip()


def extract_features(samples):
    """谱特征提取"""
    return [float(s) for s in samples]


class FeatureExtractor:
    def fit(self, samples):
        return extract_features(samples)
'''

PY_MAIN = '''\
import rf_util


def run_pipeline(raw):
    data = rf_util.parse_input(raw)
    feats = rf_util.extract_features(data)
    clf = rf_util.FeatureExtractor()
    return clf.fit(feats)
'''

MD_NOTES = """\
# 射电频谱笔记

## Hilbert 变换

实信号转复基带的标准做法，参见 [设计文档](design.md)。

## 特征提取

谱特征用 extract_features 计算。
"""

MD_DESIGN = """\
# 系统设计

## 采样率

2.4 MHz 采样。
"""


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "rf_util.py").write_text(PY_UTIL, encoding="utf-8")
    (tmp_path / "main.py").write_text(PY_MAIN, encoding="utf-8")
    (tmp_path / "notes.md").write_text(MD_NOTES, encoding="utf-8")
    (tmp_path / "design.md").write_text(MD_DESIGN, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _no_env_graph(monkeypatch):
    """隔离 GRAPHIFY_GRAPH_JSON，防止开发机配置泄漏进测试。"""
    monkeypatch.delenv("GRAPHIFY_GRAPH_JSON", raising=False)


def _call(bridge: GraphifyBridge, **tool_call) -> dict:
    return json.loads(asyncio.run(bridge.handle_handoff(tool_call)))


# ---------------------------------------------------------------- 生成管线

def test_extract_corpus_builds_graph(corpus: Path):
    result = extract_corpus(corpus)
    assert result["ok"] is True
    assert result["nodes"] > 0 and result["links"] > 0
    graph_json = Path(result["graph_json"])
    assert graph_json.is_file()
    assert graph_json.parent.name == "graphify-out"

    data = json.loads(graph_json.read_text(encoding="utf-8"))
    node_fields = {"id", "label", "file_type", "source_file",
                   "source_location", "community"}
    assert node_fields <= set(data["nodes"][0])
    confidences = {l["confidence"] for l in data["links"]}
    assert EXTRACTED in confidences  # contains/imports 边必须可溯源

    # 幂等：重复生成不叠节点
    result2 = extract_corpus(corpus)
    assert result2["nodes"] == result["nodes"]


def test_extract_corpus_rejects_bad_path(tmp_path: Path):
    with pytest.raises(GraphifyError):
        extract_corpus(tmp_path / "nope")


# ------------------------------------------------------- 生成 → 提问 → 引用

def test_build_then_query_returns_citation(corpus: Path):
    """W-03 主验收：图谱生成 → 提问 → 回答含 citation 引用来源。"""
    bridge = GraphifyBridge()
    built = _call(bridge, tool_name="graphify_build", path=str(corpus))
    assert built["status"] == "ok"
    assert built["result"]["engine"] == "builtin-ast"
    assert built["result"]["upstream_cli"] in (True, False)

    resp = _call(bridge, tool_name="graphify_query",
                 question="extract features 谱特征提取在哪个文件", top_k=6)
    assert resp["status"] == "ok"
    result = resp["result"]
    assert result["ok"] is True and result["matches"]

    # grep 断言口径：序列化后必须能 grep 到 citation 字段
    raw = json.dumps(result, ensure_ascii=False)
    assert '"citation"' in raw
    # 每条命中都有引用，且引用能定位到源文件行号
    for m in result["matches"]:
        cit = m["citation"]
        assert set(cit) >= {"citation", "source_file", "source_location",
                            "label", "file_type"}
        assert cit["source_location"].startswith("L")
    code_hits = [m for m in result["matches"]
                 if m["citation"]["source_file"].endswith(".py")]
    assert code_hits, "谱特征问题应命中 rf_util.py 的代码节点"
    assert any("rf_util.py" in m["citation"]["source_file"]
               for m in code_hits)
    assert result["citations"], "顶层 citations 汇总不能为空"
    assert result["answer"]


def test_query_doc_nodes_cite_markdown(corpus: Path):
    bridge = GraphifyBridge()
    _call(bridge, tool_name="graphify_build", path=str(corpus))
    resp = _call(bridge, tool_name="graphify_query",
                 question="Hilbert 变换")
    assert resp["status"] == "ok"
    hit_files = [m["citation"]["source_file"]
                 for m in resp["result"]["matches"]]
    assert any(f.endswith("notes.md") for f in hit_files)


def test_query_unrelated_question_fails_fast(corpus: Path):
    bridge = GraphifyBridge()
    _call(bridge, tool_name="graphify_build", path=str(corpus))
    resp = _call(bridge, tool_name="graphify_query",
                 question="zzzzz qqwww 完全无关")
    assert resp["status"] == "error"  # 无命中 fail-fast，不静默空返回


def test_query_before_build_errors():
    resp = _call(GraphifyBridge(), tool_name="graphify_query",
                 question="anything")
    assert resp["status"] == "error"
    assert "graphify_build" in resp["error"]


# ---------------------------------------------------------------- 结构查询

def test_path_and_explain(corpus: Path):
    bridge = GraphifyBridge()
    _call(bridge, tool_name="graphify_build", path=str(corpus))

    path_resp = _call(bridge, tool_name="graphify_path",
                      a="main_run_pipeline", b="rf_util_parse_input")
    assert path_resp["status"] == "ok"
    pr = path_resp["result"]
    assert pr["ok"] is True and len(pr["path"]) >= 2
    for step in pr["steps"]:
        assert "citation" in step and step["citation"]["citation"]

    explain_resp = _call(bridge, tool_name="graphify_explain",
                         node="rf_util_extract_features")
    assert explain_resp["status"] == "ok"
    er = explain_resp["result"]
    assert er["ok"] is True and er["degree"] >= 1
    assert "citation" in er["node"]


def test_path_no_route_and_missing_node(corpus: Path):
    bridge = GraphifyBridge()
    _call(bridge, tool_name="graphify_build", path=str(corpus))
    missing = _call(bridge, tool_name="graphify_path",
                    a="main_run_pipeline", b="ghost_node")
    assert missing["status"] == "error"


# --------------------------------------------------- 上游 graph.json 兼容

UPSTREAM_GRAPH = {
    "directed": False, "multigraph": False, "graph": {},
    "nodes": [
        {"label": "analyze.py", "file_type": "code",
         "source_file": "worked/mixed-corpus/raw/analyze.py",
         "source_location": "L1", "id": "analyze", "community": 1},
        {"label": "analyze_data()", "file_type": "code",
         "source_file": "worked/mixed-corpus/raw/analyze.py",
         "source_location": "L6", "id": "analyze_analyze_data", "community": 1},
        {"label": "cash_flow.md", "file_type": "doc",
         "source_file": "worked/mixed-corpus/raw/cash_flow.md",
         "source_location": "L1", "id": "cash_flow", "community": 2},
    ],
    "links": [
        {"relation": "contains", "confidence": "EXTRACTED",
         "source_file": "worked/mixed-corpus/raw/analyze.py",
         "source_location": "L6", "weight": 1.0,
         "source": "analyze", "target": "analyze_analyze_data"},
        {"relation": "mentions", "confidence": "INFERRED",
         "source_file": "", "source_location": "L?", "weight": 0.5,
         "source": "analyze_analyze_data", "target": "cash_flow"},
    ],
}


def test_import_upstream_graph_json(tmp_path: Path):
    upstream = tmp_path / "upstream_graph.json"
    upstream.write_text(json.dumps(UPSTREAM_GRAPH), encoding="utf-8")
    bridge = GraphifyBridge()
    resp = _call(bridge, tool_name="graphify_import", graph_json=str(upstream))
    assert resp["status"] == "ok"
    assert resp["result"]["nodes"] == 3

    q = _call(bridge, tool_name="graphify_query", question="analyze data")
    assert q["status"] == "ok"
    match = q["result"]["matches"][0]
    assert match["citation"]["source_file"].endswith("analyze.py")
    assert match["citation"]["source_location"] == "L6"
    # grep 断言口径（上游 schema 同样成立）
    assert '"citation"' in json.dumps(q["result"], ensure_ascii=False)

    e = _call(bridge, tool_name="graphify_explain", node="analyze_analyze_data")
    assert e["status"] == "ok" and e["result"]["degree"] == 2


def test_import_rejects_empty_graph(tmp_path: Path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    resp = _call(GraphifyBridge(), tool_name="graphify_import",
                 graph_json=str(empty))
    assert resp["status"] == "error"


# ------------------------------------------------------------ MCP 注册链路

def test_manifest_license_field():
    """硬约束：manifest 必须含 license 字段。"""
    manifest_path = (Path(__file__).resolve().parents[1]
                     / "mcpserver" / "adapters" / "graphify"
                     / "agent-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["agentType"] == "mcp"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["entryPoint"]["module"] == \
        "mcpserver.adapters.graphify.adapter"
    commands = [c["command"] for c in
                manifest["capabilities"]["invocationCommands"]]
    assert "graphify_build" in commands and "graphify_query" in commands


def test_registry_scan_registers_graphify(corpus: Path):
    """scan_and_register_mcp_agents 能发现 graphify manifest 并实例化 Bridge。"""
    from mcpserver.mcp_registry import (
        clear_registry,
        get_service_instance,
        get_registered_services,
        scan_and_register_mcp_agents,
    )
    clear_registry()
    try:
        registered = scan_and_register_mcp_agents("mcpserver")
        assert "graphify" in registered
        assert "graphify" in get_registered_services()
        instance = get_service_instance("graphify")
        assert isinstance(instance, GraphifyBridge)

        # 注册后的实例直接可用：生成 → 提问 → 引用
        built = json.loads(asyncio.run(instance.handle_handoff(
            {"tool_name": "graphify_build", "path": str(corpus)})))
        assert built["status"] == "ok"
        q = json.loads(asyncio.run(instance.handle_handoff(
            {"tool_name": "graphify_query", "question": "parse input"})))
        assert q["status"] == "ok"
        assert '"citation"' in json.dumps(q["result"], ensure_ascii=False)
    finally:
        clear_registry()


def test_unified_call_end_to_end(corpus: Path):
    """模拟 apiserver /call 全链路：mcp_manager.unified_call 分发到 graphify。"""
    from mcpserver.mcp_registry import MCP_REGISTRY, clear_registry, scan_and_register_mcp_agents
    from mcpserver.mcp_manager import MCPManager
    clear_registry()
    try:
        scan_and_register_mcp_agents("mcpserver")
        manager = MCPManager()
        raw = asyncio.run(manager.unified_call(
            "graphify", {"tool_name": "graphify_build", "path": str(corpus)}))
        assert json.loads(raw)["status"] == "ok"
        raw = asyncio.run(manager.unified_call(
            "graphify", {"tool_name": "graphify_query",
                         "question": "FeatureExtractor fit"}))
        parsed = json.loads(raw)
        assert parsed["status"] == "ok"
        assert '"citation"' in json.dumps(parsed["result"], ensure_ascii=False)
    finally:
        clear_registry()


def test_unknown_tool_and_status():
    bridge = GraphifyBridge()
    bad = _call(bridge, tool_name="graphify_fly")
    assert bad["status"] == "error"
    status = _call(bridge, tool_name="graphify_status")
    assert status["status"] == "ok"
    assert status["result"]["loaded"] is False
    assert status["result"]["upstream_license"] == "Apache-2.0"


# ------------------------------------------------------------ engine 直测

def test_graphify_graph_schema_tolerance():
    """上游老格式（edges/_src/_tgt/file/line）也能加载。"""
    legacy = {
        "nodes": [
            {"node_id": "n1", "label": "solver.py", "type": "code",
             "file": "src/solver.py", "line": 1},
        ],
        "edges": [
            {"_src": "n1", "_tgt": "n1", "rel": "self"},  # 自环应被吞掉
        ],
    }
    g = GraphifyGraph(legacy)
    assert list(g.node_by_id) == ["n1"]
    assert g.links == []  # 自环不进邻接表


def test_tokenizer_splits_identifiers():
    from mcpserver.adapters.graphify.engine import tokenize
    assert "feature" in tokenize("FeatureExtractor fit_pipeline")
    assert "extractor" in tokenize("FeatureExtractor")
    assert "graph" in tokenize("graphify-out/graph.json")
