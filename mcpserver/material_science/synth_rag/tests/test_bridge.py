"""U-03 验收：synth_rag MCP 桥（SynthRagBridge）测试。

验收点（工单）：
1. add 入库 + search 检索命中（临时文件库，不污染默认库）
2. 坏输入报错（缺必填/非对象）
3. validate 物理校验（通过/失败两态）
4. register_synth_tools 注入 material_science agent，manifest 追加命令齐备
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcpserver.material_science.synth_rag.bridge import (
    SynthRagBridge,
    register_synth_tools,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST = REPO_ROOT / "mcpserver" / "material_science" / "agent-manifest.json"

_NEW_TOOLS = {"synth_search", "synth_add", "synth_validate"}

_ROUTE = {
    "name": "木质素纳米颗粒-水热法",
    "product": "木质素纳米颗粒",
    "method": "水热自组装",
    "yield_min": 0.30,
    "yield_max": 0.60,
    "source": "示例",
    "reactants": [{"name": "木质素", "amount": 5.0, "unit": "mg/mL"}],
    "conditions": {"temp_min_c": 140.0, "temp_max_c": 220.0, "time_h": 6.0},
}


@pytest.fixture()
def bridge(tmp_path) -> SynthRagBridge:
    return SynthRagBridge(db_path=str(tmp_path / "routes.db"))


def test_add_and_search(bridge):
    r = bridge.add(_ROUTE)
    assert r["status"] == "ok" and r["count"] == 1 and r["route_id"] >= 1
    # 按产物检索命中
    r = bridge.search(product="木质素")
    assert r["status"] == "ok" and r["count"] >= 1
    assert any("木质素" in str(x.get("product", "")) for x in r["results"])
    # 全空过滤词返回全量
    assert bridge.search()["count"] >= 1


def test_add_invalid_inputs(bridge):
    assert bridge.add(None)["status"] == "error"
    assert bridge.add({"name": "缺产物"})["status"] == "error"  # product 必填
    assert bridge.add({"product": ""})["status"] == "error"


def test_validate_pass_and_fail(bridge):
    r = bridge.validate(_ROUTE)
    assert r["status"] == "ok" and r["valid"] is True and r["passed"]
    # 无反应物 → reactant_present 规则失败
    bad = {k: v for k, v in _ROUTE.items() if k != "reactants"}
    r = bridge.validate(bad)
    assert r["valid"] is False
    assert any(i.get("rule") == "reactant_present" for i in r["issues"])
    # 非对象 → error
    assert bridge.validate("nope")["status"] == "error"


def test_register_into_agent_stub(bridge):
    """register_synth_tools 注入 agent.tools（与 biopred/duckdb 同模式）。"""

    class _Stub:
        tools: dict = {}

    stub = _Stub()
    register_synth_tools(stub)
    assert set(stub.tools) >= _NEW_TOOLS
    # 注册入口可直调（参数解包由工具闭包完成）
    out = stub.tools["synth_validate"]({"route": _ROUTE})
    assert out["status"] == "ok" and out["valid"] is True


def test_manifest_appends_synth_commands():
    """manifest 追加 3 个 synth 命令且保留全部旧条目。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commands = [c["command"] for c in manifest["capabilities"]["invocationCommands"]]
    assert set(commands) >= _NEW_TOOLS
    assert len(commands) == 19  # 原有 13 + 新增 6


def test_material_science_agent_lists_new_tools():
    """硬验收：material_science 实例化成功且列出新增 6 工具。"""
    from mcpserver.material_science.materialscience_agent import MaterialScienceAgent

    agent = MaterialScienceAgent()
    assert (_NEW_TOOLS | {"bo_recommend", "bo_record", "bo_get_params"}) \
        <= set(agent.tools)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
