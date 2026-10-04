"""U-03 验收：bo_optim MCP 桥（BoOptimBridge）测试。

验收点（工单）：
1. recommend 返回参数空间内配方（数据不足退化随机不报错）
2. record 回填闭环（观测计数递增，坏参数报错）
3. get_params 输出与参数空间同源
4. register_bo_tools 注入 material_science agent，manifest 追加命令齐备
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcpserver.material_science.bo_optim.bridge import (
    BoOptimBridge,
    register_bo_tools,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST = REPO_ROOT / "mcpserver" / "material_science" / "agent-manifest.json"

_NEW_TOOLS = {"bo_recommend", "bo_record", "bo_get_params"}


@pytest.fixture()
def bridge() -> BoOptimBridge:
    return BoOptimBridge(seed=7)


def test_recommend_within_space(bridge):
    """推荐配方必须落在参数空间范围内（封装不重写，值域由 space 决定）。"""
    r = bridge.recommend(k=3)
    assert r["status"] == "ok" and r["count"] == 3
    space = bridge._loop.space  # noqa: SLF001 — 测试同源校验
    for recipe in r["recipes"]:
        for name, (lo, hi) in space.continuous.items():
            assert lo <= recipe[name] <= hi, f"{name} 越界: {recipe[name]}"


def test_record_closed_loop(bridge):
    """record 回填 → observed 递增 → recommend 仍可消费。"""
    assert bridge.get_params()["observed"] == 0
    rec = bridge.recommend(k=1)["recipes"][0]
    r = bridge.record(rec, metrics={"yield": 0.42})
    assert r["status"] == "ok" and r["observed"] == 1
    # 失败回填同样入训练集
    rec2 = bridge.recommend(k=1)["recipes"][0]
    r = bridge.record(rec2, failed=True)
    assert r["status"] == "ok" and r["observed"] == 2
    assert bridge.recommend(k=1)["count"] == 1


def test_record_bad_recipe_errors(bridge):
    assert bridge.record(None)["status"] == "error"
    assert bridge.record({})["status"] == "error"
    assert bridge.record("not-a-dict")["status"] == "error"


def test_get_params_matches_space(bridge):
    r = bridge.get_params()
    assert r["status"] == "ok"
    # 木质素水热空间四连续参数（与 params.py 同源）
    assert set(r["continuous"]) == {"T", "t", "C", "R"}
    assert r["continuous"]["T"] == [140.0, 220.0]
    assert r["observed"] == 0 and r["pending"] == 0


def test_register_into_agent_stub():
    """register_bo_tools 注入 agent.tools（与 biopred/duckdb 同模式）。"""

    class _Stub:
        tools: dict = {}

    stub = _Stub()
    register_bo_tools(stub)
    assert set(stub.tools) >= _NEW_TOOLS
    out = stub.tools["bo_recommend"]({"k": 2})
    assert out["status"] == "ok" and out["count"] == 2
    out = stub.tools["bo_record"]({"recipe": {"T": 180.0, "t": 6.0,
                                               "C": 5.0, "R": 3.0,
                                               "S": "纯水", "pH": "中性",
                                               "L": "碱木质素"},
                                    "metrics": {"yield": 0.4}})
    assert out["status"] == "ok" and out["observed"] == 1
    assert stub.tools["bo_get_params"]({})["status"] == "ok"


def test_manifest_appends_bo_commands():
    """manifest 追加 3 个 bo 命令且保留全部旧条目（增量不破坏）。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commands = [c["command"] for c in manifest["capabilities"]["invocationCommands"]]
    assert set(commands) >= _NEW_TOOLS
    # 旧条目原样保留（原有 13 个 + 新增 6 个 = 19）
    assert "literature_search" in commands and "biopred_suggest" in commands
    assert len(commands) == 19


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
