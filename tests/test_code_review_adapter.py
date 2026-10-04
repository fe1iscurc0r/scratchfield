"""code-review-graph 适配包功能测试（02-01 验收）。

验收口径（对齐工单）：
1. 门禁默认关：ENABLE_ADAPTER_CODE_REVIEW 未开 → 不实例化（不破坏现状）
2. 建图：节点(module/class/function/method) + 边(contains/imports/calls)，跨文件调用可解析
3. query：定义 + 调用者/被调者；缺失 fail-fast（CodeReviewError，非静默空返回）
4. impact_radius：变更文件反向 BFS，按深度分层
5. detect_changes：git diff → 变更函数 + 风险分 + 测试缺口
6. 确定性：同一目录两次建图 → 字节级一致 JSON
7. agent-manifest.json：license 字段（硬约束）+ 4 核心命令 + entryPoint 可解析注册
8. handle_handoff：ok / error 两种信封
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from mcpserver.adapters.code_review import (
    CodeReviewError,
    CodeReviewGraphBridge,
    GraphIndex,
    estimate_tokens,
    is_enabled,
)
from mcpserver.mcp_registry import create_agent_instance, load_manifest_file

# ---------------------------------------------------------------- fixtures

PY_UTIL = '''\
def parse_input(raw):
    """解析输入"""
    return raw.strip()


def extract_features(samples):
    """谱特征提取"""
    return [float(s) for s in samples]
'''

PY_MAIN = '''\
import pkg.util


def run_pipeline(raw):
    data = pkg.util.parse_input(raw)
    feats = pkg.util.extract_features(data)
    return feats


class Runner:
    def go(self, x):
        return run_pipeline(x)
'''

PY_TEST = '''\
import pkg.util


def test_extract():
    assert pkg.util.extract_features([1, 2]) == [1.0, 2.0]
'''


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "util.py").write_text(PY_UTIL, encoding="utf-8")
    (tmp_path / "pkg" / "main.py").write_text(PY_MAIN, encoding="utf-8")
    (tmp_path / "tests" / "test_util.py").write_text(PY_TEST, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_gate(monkeypatch):
    monkeypatch.delenv("ENABLE_ADAPTER_CODE_REVIEW", raising=False)
    monkeypatch.delenv("CRG_INDEX_JSON", raising=False)


# ---------------------------------------------------------------- 门禁

def test_gate_default_off():
    """工单铁律：默认关，不破坏现状 —— 未开即实例化 raise。"""
    assert is_enabled() is False
    with pytest.raises(CodeReviewError):
        CodeReviewGraphBridge()


def test_gate_explicit_on(monkeypatch):
    monkeypatch.setenv("ENABLE_ADAPTER_CODE_REVIEW", "1")
    assert is_enabled() is True
    bridge = CodeReviewGraphBridge()  # 不 raise 即通过
    assert bridge is not None


# ---------------------------------------------------------------- 建图

def test_build_nodes_and_edges(sample_project):
    idx = GraphIndex.build(sample_project)
    kinds = {n["kind"] for n in idx.nodes}
    assert {"module", "class", "function", "method"} <= kinds
    # 跨文件调用解析：run_pipeline → util.parse_input / util.extract_features
    run = idx.query("run_pipeline")["matches"][0]
    callee_names = {c["name"] for c in run["callees"]}
    assert callee_names == {"parse_input", "extract_features"}
    # self.method 归属：Runner.go → run_pipeline
    go = idx.query("go")["matches"][0]
    assert {c["name"] for c in go["callees"]} == {"run_pipeline"}
    # import 边：main → util
    import_edges = [e for e in idx.edges if e["kind"] == "imports"]
    assert any(e["dst"] == "pkg/util.py::" for e in import_edges)


def test_build_missing_dir_fail_fast(tmp_path):
    with pytest.raises(CodeReviewError):
        GraphIndex.build(tmp_path / "不存在")


# ---------------------------------------------------------------- 查询

def test_query_callers_and_callees(sample_project):
    idx = GraphIndex.build(sample_project)
    r = idx.query("parse_input")["matches"][0]
    assert [c["name"] for c in r["callers"]] == ["run_pipeline"]
    assert r["callees"] == []


def test_query_miss_fail_fast(sample_project):
    idx = GraphIndex.build(sample_project)
    with pytest.raises(CodeReviewError):
        idx.query("不存在的函数")


# ---------------------------------------------------------------- 影响半径

def test_impact_radius_depth(sample_project):
    idx = GraphIndex.build(sample_project)
    ir = idx.impact_radius(["pkg/util.py"], max_depth=2)
    nodes = ir["impacted_nodes"]
    # util 自身函数 depth0；run_pipeline depth1；Runner.go depth2（经由 run_pipeline）
    assert nodes["pkg/util.py::parse_input"]["depth"] == 0
    assert nodes["pkg/main.py::run_pipeline"]["depth"] == 1
    assert nodes["pkg/main.py::Runner.go"]["depth"] == 2


def test_impact_radius_unknown_file_fail_fast(sample_project):
    idx = GraphIndex.build(sample_project)
    with pytest.raises(CodeReviewError):
        idx.impact_radius(["不存在.py"])


# ---------------------------------------------------------------- 变更检测

def test_detect_changes_risk_and_gap(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("def alpha(x):\n    return x\n\ndef beta(x):\n    return alpha(x)\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text("def test_beta():\n    assert beta(1) == 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / "app.py").write_text("def alpha(x):\n    return x + 1\n\ndef beta(x):\n    return alpha(x)\n", encoding="utf-8")

    idx = GraphIndex.build(repo)
    dc = idx.detect_changes(base="HEAD")
    assert dc["changed_files"] == ["app.py"]
    funcs = {f["function"]: f for f in dc["changed_functions"]}
    assert "alpha" in funcs          # 变更行命中的函数
    assert "beta" not in funcs       # beta 区间无变更
    assert funcs["alpha"]["has_test"] is False   # alpha 无测试覆盖
    assert funcs["alpha"]["risk_score"] >= 0
    assert funcs["alpha"]["level"] in ("low", "medium", "high")
    assert "alpha" in [g["function"] for g in dc["test_gaps"]]


# ---------------------------------------------------------------- 确定性

def test_build_deterministic(sample_project):
    a = json.dumps(GraphIndex.build(sample_project).to_dict(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(GraphIndex.build(sample_project).to_dict(), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_save_load_roundtrip(sample_project, tmp_path):
    idx = GraphIndex.build(sample_project)
    out = idx.save(tmp_path / "idx.json")
    loaded = GraphIndex.load(out)
    assert loaded.nodes == idx.nodes
    assert loaded.edges == idx.edges
    assert loaded.query("run_pipeline")["total"] == 1


# ---------------------------------------------------------------- manifest + 注册

def test_manifest_registered():
    manifest_path = Path(__file__).resolve().parents[1] / "mcpserver" / "adapters" \
        / "code_review" / "agent-manifest.json"
    manifest = load_manifest_file(manifest_path)
    assert manifest is not None
    assert manifest["agentType"] == "mcp"
    assert "license" in manifest                 # 供应链铁律：license 声明
    cmds = [c["command"] for c in manifest["capabilities"]["invocationCommands"]]
    assert {"code_review_detect_changes", "code_review_get_impact_radius",
            "code_review_query_graph", "code_review_get_architecture_overview"} <= set(cmds)


def test_manifest_entrypoint_resolves(monkeypatch):
    """注册通道可解析 entryPoint（模块前缀白名单 + 类实例化），门禁开时成功。"""
    monkeypatch.setenv("ENABLE_ADAPTER_CODE_REVIEW", "1")
    manifest_path = Path(__file__).resolve().parents[1] / "mcpserver" / "adapters" \
        / "code_review" / "agent-manifest.json"
    manifest = load_manifest_file(manifest_path)
    instance = create_agent_instance(manifest, "code_review")
    assert instance is not None
    assert hasattr(instance, "handle_handoff")


# ---------------------------------------------------------------- handoff 分发

def test_handle_handoff_ok_and_error(monkeypatch, sample_project):
    monkeypatch.setenv("ENABLE_ADAPTER_CODE_REVIEW", "1")
    monkeypatch.setenv("CRG_INDEX_JSON", str(sample_project / "none.json"))
    bridge = CodeReviewGraphBridge()
    bridge.tool_build_index(str(sample_project))

    async def run():
        ok = await bridge.handle_handoff(
            {"tool_name": "code_review_query_graph", "name": "run_pipeline"})
        err = await bridge.handle_handoff(
            {"tool_name": "code_review_query_graph", "name": "nope_xyz"})
        return ok, err

    ok, err = asyncio.run(run())
    assert json.loads(ok)["status"] == "ok"
    assert json.loads(err)["status"] == "error"
    assert json.loads(err)["service"] == "code_review"


# ---------------------------------------------------------------- token 估算

def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2  # ceil(5/4)=2


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)
