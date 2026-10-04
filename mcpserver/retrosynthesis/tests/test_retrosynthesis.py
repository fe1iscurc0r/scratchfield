"""卷169-A 验收测试：retrosynthesis MCP 封装（import + 签名级 + 降级路径）。

工单要求：用 aizynthfinder 官方 quick-test 数据或 **mock planner** 做 import +
签名级测试；**无数据环境跑降级路径测试**（本机无模型数据 → 降级路径全覆盖）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # tests/ -> retrosynthesis/ -> mcpserver/ -> 仓库根
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load():
    spec = importlib.util.spec_from_file_location(
        "retrosynthesis_under_test", PROJECT_ROOT / "mcpserver" / "retrosynthesis" / "agent.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


agent_mod = _load()


class TestManifest:
    def test_manifest_has_classification_and_requires(self):
        mf = PROJECT_ROOT / "mcpserver" / "retrosynthesis" / "agent-manifest.json"
        d = json.loads(mf.read_text(encoding="utf-8"))
        cls = d.get("classification") or {}
        assert cls.get("families") == ["compute"]
        assert cls.get("tier") == "read-only"
        reqs = d.get("requires") or {}
        assert "aizynthfinder" in (reqs.get("python_packages") or [])
        cmds = [c["command"] for c in d["capabilities"]["invocationCommands"]]
        assert cmds == ["route_search", "stock_check", "template_lookup"]

    def test_entrypoint_module_exists(self):
        """grep -c entryPoint ≥1 且实现里类方法真实存在（工单验收）。"""
        d = json.loads(
            (PROJECT_ROOT / "mcpserver" / "retrosynthesis" / "agent-manifest.json")
            .read_text(encoding="utf-8"))
        ep = d["entryPoint"]
        assert ep["module"] == "mcpserver.retrosynthesis.agent"
        agent = _load().RetrosynthesisAgent()
        assert callable(getattr(agent, "route_search"))
        assert callable(getattr(agent, "stock_check"))
        assert callable(getattr(agent, "template_lookup"))


class TestDegradedPaths:
    """无模型数据环境 → 结构化降级（ModelDataMissingError，不裸抛）。"""

    def test_missing_data_is_structured(self):
        agent = agent_mod.RetrosynthesisAgent()
        try:
            agent.route_search("COC1=CC(=CC=C1O)C=O")
        except agent_mod.ModelDataMissingError as e:
            assert e.missing, "结构化错误应列缺失项"
            assert "aizynthfinder --download" in str(e), "应含获取路径说明"
        except agent_mod.AcademicDependencyError:
            pytest.skip("aizynthfinder 包未装（requires 已声明，装齐后走数据检查路径）")
        else:
            pytest.fail("无数据环境应抛 ModelDataMissingError")

    def test_stock_check_same_degradation(self):
        agent = agent_mod.RetrosynthesisAgent()
        try:
            agent.stock_check("CC(=O)OC1=CC=CC=C1C(=O)O")
        except agent_mod.ModelDataMissingError:
            pass  # 期望路径
        except agent_mod.AcademicDependencyError:
            pytest.skip("aizynthfinder 未装")
        else:
            pytest.fail("无数据环境应抛 ModelDataMissingError")

    def test_template_lookup_same_degradation(self):
        agent = agent_mod.RetrosynthesisAgent()
        try:
            agent.template_lookup("COC1=CC(=CC=C1O)C=O")
        except agent_mod.ModelDataMissingError:
            pass
        except agent_mod.AcademicDependencyError:
            pytest.skip("aizynthfinder 未装")
        else:
            pytest.fail("无数据环境应抛 ModelDataMissingError")


class TestValidation:
    def test_empty_smiles_raises_value_error(self):
        agent = agent_mod.RetrosynthesisAgent()
        with pytest.raises(ValueError):
            agent.route_search("")

    def test_missing_data_detector(self):
        """探测函数返回 list（缺失项），无异常。"""
        missing = agent_mod._missing_model_data()
        assert isinstance(missing, list)
