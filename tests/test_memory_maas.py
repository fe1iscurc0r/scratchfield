"""记忆 MaaS 测试（W-06 验收）。

四层：
1. core：五件套组合（血统链/写卡+检索/衰减报告）
2. HTTP sidecar：TestClient 全端点（验收主体：调记忆 API 返回会话血统）
3. bridge：MCP 工具（sidecar 不通 → 进程内降级）
4. 注册链路：scan_and_register + unified_call 全链路
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from mcpserver.memory_maas.bridge import MemoryMaasBridge
from mcpserver.memory_maas.core import (
    MemoryMaasCore,
    MemoryMaasError,
    reset_core,
)

# 词级 token 内容（FTS5 unicode61 对连续中文按整段切词，测试用显式分词）
TURNS_COOLPROP = [
    {"role": "user", "content": "用 CoolProp 算水在 300K 的密度"},
    {"role": "assistant", "content": "PropsSI D T 300 P 101325 Water 结果 996.56 kg/m3"},
]
TURNS_RADIO = [
    {"role": "user", "content": "IC-705 采样率 2.4MHz 频谱怎么配置"},
    {"role": "assistant", "content": "rsba1 adapter 桥接 SDR 采样 Hilbert 变换"},
]


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch):
    """每测独立数据目录 + 结束复位单例，绝不碰仓库默认目录。"""
    monkeypatch.setenv("MEMORY_MAAS_DATA_DIR", str(tmp_path / "maas_data"))
    monkeypatch.setenv("MEMORY_MAAS_URL", "http://127.0.0.1:1")  # 强制进程内降级
    reset_core()
    yield
    reset_core()


# ---------------------------------------------------------------- 1. core

def test_core_lineage_chain(tmp_path: Path):
    core = MemoryMaasCore(tmp_path / "c1")
    core.start()
    try:
        core.register_session("root", summary="根会话")
        core.register_session("child", parent_id="root", branch_label="exp-a",
                              summary="实验分支")
        core.register_session("gc", parent_id="child", summary="孙会话")
        chain = core.trace("gc")
        assert [s["session_id"] for s in chain] == ["root", "child", "gc"]
        assert chain[0]["parent_id"] is None
        branches = core.branches_under("root")
        assert "exp-a" in branches and "child" in branches["exp-a"]
    finally:
        core.close()


def test_core_write_card_then_search_with_lineage(tmp_path: Path):
    core = MemoryMaasCore(tmp_path / "c2")
    core.start()
    try:
        core.register_session("s_cool", summary="CoolProp 会话")
        wrote = core.write_card("s_cool", TURNS_COOLPROP)
        assert wrote["ok"] and wrote["cards"]
        result = core.search("CoolProp 密度")
        assert result["ok"] and result["count"] >= 1
        hit = result["matches"][0]
        assert hit["session_id"] == "s_cool"
        # 验收口径：检索命中返回会话血统
        assert [s["session_id"] for s in hit["lineage"]] == ["s_cool"]
    finally:
        core.close()


def test_core_search_empty_query_fails_fast(tmp_path: Path):
    core = MemoryMaasCore(tmp_path / "c3")
    core.start()
    try:
        with pytest.raises(MemoryMaasError):
            core.search("   ")
    finally:
        core.close()


def test_core_lifecycle_report_and_touch(tmp_path: Path):
    import time as _time
    core = MemoryMaasCore(tmp_path / "c4")
    core.start()
    try:
        core.register_session("s_radio", summary="射频会话")
        core.write_card("s_radio", TURNS_RADIO)
        report = core.lifecycle_report()
        assert report["ok"] and report["total"] >= 1
        assert report["keep"] + report["decay"] + report["expire"] == report["total"]
        # touch 续命后 last_access 刷新 → 决策回到 keep/decay（不应立即过期）
        card_id = report["records"][0]["card_id"]
        core.touch_card(card_id)
        fresh = core.lifecycle_report()
        assert fresh["expire"] <= report["expire"]
        assert _time.time() - fresh["records"][0]["last_access"] < 60
    finally:
        core.close()


def test_core_status(tmp_path: Path):
    core = MemoryMaasCore(tmp_path / "c5")
    core.start()
    try:
        st = core.status()
        assert st["ok"] and st["lineage_sessions"] == 0 and st["cards"] == 0
        core.register_session("sx")
        core.write_card("sx", TURNS_RADIO)
        st2 = core.status()
        assert st2["lineage_sessions"] == 1 and st2["cards"] >= 1
        assert st2["writer_stats"]["written"] >= 1
    finally:
        core.close()


# ---------------------------------------------------------- 2. HTTP sidecar

@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient
    from mcpserver.memory_maas.app import app

    with TestClient(app) as c:  # with 触发 lifespan：get_core() 建库+启动后台写
        yield c


def test_http_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "memory_maas"


def test_http_lineage_trace_returns_chain(client):
    """W-06 主验收：任一模块经 HTTP 调记忆 API 成功返回会话血统。"""
    for sid, parent in [("root", None), ("child", "root"), ("gc", "child")]:
        resp = client.post("/memory/lineage/register",
                           json={"session_id": sid, "parent_id": parent,
                                 "summary": f"{sid} 概要"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["session_id"] == sid

    resp = client.get("/memory/lineage/trace/gc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["depth"] == 3
    assert [s["session_id"] for s in body["lineage"]] == ["root", "child", "gc"]
    assert body["lineage"][1]["parent_id"] == "root"

    branches = client.get("/memory/lineage/branches/root").json()
    assert branches["ok"] and "child" in branches["branches"].get("main", [])


def test_http_lineage_conflict_maps_409(client):
    client.post("/memory/lineage/register",
                json={"session_id": "root", "summary": "根"})
    resp = client.post("/memory/lineage/register",
                       json={"session_id": "bad", "parent_id": "ghost"})
    assert resp.status_code == 409  # 父会话不存在 → LineageError → 409
    assert "父会话不存在" in resp.json()["detail"]


def test_http_write_card_and_search_with_lineage(client):
    client.post("/memory/lineage/register",
                json={"session_id": "s_cool", "summary": "CoolProp 会话"})
    resp = client.post("/memory/cards",
                       json={"session_id": "s_cool", "turns": TURNS_COOLPROP})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] and resp.json()["cards"]

    hit = client.post("/memory/search", json={"query": "CoolProp 密度",
                                              "limit": 5})
    assert hit.status_code == 200
    body = hit.json()
    assert body["count"] >= 1
    match = body["matches"][0]
    assert match["session_id"] == "s_cool"
    assert [s["session_id"] for s in match["lineage"]] == ["s_cool"]

    cards = client.get("/memory/cards/s_cool").json()
    assert cards["cards"] and cards["cards"][0]["confidence"] > 0


def test_http_lifecycle_endpoints(client):
    client.post("/memory/lineage/register",
                json={"session_id": "s_radio", "summary": "射频会话"})
    client.post("/memory/cards",
                json={"session_id": "s_radio", "turns": TURNS_RADIO})
    report = client.get("/memory/lifecycle/report").json()
    assert report["ok"] and report["total"] >= 1
    assert report["keep"] + report["decay"] + report["expire"] == report["total"]

    import time as _time
    # 置信度 ≥ min_confidence_keep 才参与 expire 判定（低置信走 decay 分支）
    enrich = client.post("/memory/lifecycle/enrich", json={
        "records": [{"last_access": _time.time() - 60 * 86400 * 60,
                     "confidence": 0.5}]})
    assert enrich.status_code == 200
    assert enrich.json()["records"][0]["decision"] == "expire"

    bad = client.post("/memory/lifecycle/enrich", json={"records": []})
    assert bad.status_code == 422


def test_http_search_validation(client):
    resp = client.post("/memory/search", json={"query": " "})
    assert resp.status_code == 422


def test_http_status(client):
    body = client.get("/status").json()
    assert body["ok"] and "data_dir" in body and "writer_stats" in body


# ---------------------------------------------------------------- 3. bridge

def test_bridge_memory_search_inprocess_with_lineage():
    bridge = MemoryMaasBridge()
    # sidecar URL 指向不可达端口（fixture 已设）→ 进程内降级
    w = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_write", "session_id": "s1",
         "turns": TURNS_COOLPROP})))
    assert w["status"] == "ok" and w["via"] == "in-process"

    r = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_search", "query": "CoolProp 密度"})))
    assert r["status"] == "ok" and r["via"] == "in-process"
    assert r["matches"]
    assert [s["session_id"] for s in r["matches"][0]["lineage"]] == ["s1"]


def test_bridge_memory_lineage_chain_and_branches():
    bridge = MemoryMaasBridge()
    from mcpserver.memory_maas.core import get_core
    core = get_core()
    core.register_session("root")
    core.register_session("b1", parent_id="root", branch_label="exp")
    r = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_lineage", "session_id": "b1"})))
    assert r["status"] == "ok"
    assert [s["session_id"] for s in r["lineage"]] == ["root", "b1"]
    assert "b1" in r["branches"].get("exp", [])

    miss = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_lineage", "session_id": "ghost"})))
    assert miss["status"] == "error"


def test_bridge_unknown_tool_and_empty_query():
    bridge = MemoryMaasBridge()
    bad = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_fly"})))
    assert bad["status"] == "error"
    empty = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_search", "query": ""})))
    assert empty["status"] == "error"

    st = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "memory_status"})))
    assert st["status"] == "ok" and st["via"] == "in-process"


# ------------------------------------------------------- 4. 注册链路（MCP）

def test_manifest_and_registry_scan():
    from mcpserver.mcp_registry import (
        clear_registry,
        get_service_instance,
        scan_and_register_mcp_agents,
    )
    manifest_path = (Path(__file__).resolve().parents[1]
                     / "mcpserver" / "memory_maas" / "agent-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["agentType"] == "mcp"
    assert manifest["license"] == "AGPL-3.0"  # 跟主仓 + NEKO 五件套同源
    assert manifest["entryPoint"]["class"] == "MemoryMaasBridge"
    commands = [c["command"] for c in
                manifest["capabilities"]["invocationCommands"]]
    assert "memory_search" in commands

    clear_registry()
    try:
        registered = scan_and_register_mcp_agents("mcpserver")
        assert "memory_maas" in registered
        assert isinstance(get_service_instance("memory_maas"), MemoryMaasBridge)
    finally:
        clear_registry()


def test_unified_call_returns_lineage():
    """W-06 验收（MCP 路径）：unified_call 调 memory_maas 返回会话血统。"""
    from mcpserver.mcp_manager import MCPManager
    from mcpserver.mcp_registry import clear_registry, scan_and_register_mcp_agents
    clear_registry()
    try:
        scan_and_register_mcp_agents("mcpserver")
        manager = MCPManager()
        raw = asyncio.run(manager.unified_call(
            "memory_maas",
            {"tool_name": "memory_write", "session_id": "u1",
             "turns": TURNS_COOLPROP}))
        assert json.loads(raw)["status"] == "ok"
        raw = asyncio.run(manager.unified_call(
            "memory_maas",
            {"tool_name": "memory_lineage", "session_id": "u1"}))
        parsed = json.loads(raw)
        assert parsed["status"] == "ok"
        assert [s["session_id"] for s in parsed["lineage"]] == ["u1"]
    finally:
        clear_registry()
