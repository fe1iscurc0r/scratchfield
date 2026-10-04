"""mcpserver.mcp_registry.verify_entrypoint 单元测试 + 修复 agent 契约冒烟。

背景：GET /mcp/services 的 available 曾只做 import-only 检查——entryPoint.class
写错也显示可用，与注册表运行时（create_agent_instance）语义不一致。
verify_entrypoint 对齐两层语义：解析 → 白名单 → import → getattr →
handle_handoff 契约，零实例化（services 列表会对每个 agent 调用）。

覆盖：
- 全仓 manifest 深检全过（环境含全部已声明依赖，uv sync 后应保持绿）
- 缺 entryPoint / 模块不存在 / 类不存在 / 缺契约 / 白名单外 五种失败路径
- 本轮修复的 6 个 agent：handle_handoff 总线边界行为（错误落 JSON 不崩调用方）
- rf_brain：manifest 指向修正（run_loop 纯函数 → RfBrainAgent）+ 闭环真实路径
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.smoke, pytest.mark.core]

import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _manifest(rel: str) -> dict:
    return json.loads((PROJECT_ROOT / "mcpserver" / rel).read_text(encoding="utf-8"))


def _handoff(rel_manifest: str, task: dict) -> dict:
    """实例化 manifest 指向的 agent 并跑一轮 handle_handoff，返回解析后的 dict。"""
    from mcpserver.mcp_registry import create_agent_instance

    inst = create_agent_instance(_manifest(rel_manifest))
    assert inst is not None, rel_manifest
    return json.loads(asyncio.run(inst.handle_handoff(task)))


class TestVerifyEntrypoint(unittest.TestCase):
    def test_all_builtins_pass(self):
        """全仓 manifest 深检全过。

        例外：agent 的 requires 声明了 python 依赖但运行环境未装（uv sync 后
        manifest 依赖不进主 lock 是既定状态），深检在 import 步失败——这是
        诚实行为（available=False + 预检提示），单测对这类 agent SKIP；
        其余任何失败（类名错/缺契约/白名单外）一律 FAIL。
        """
        import re as _re

        from mcpserver.mcp_registry import verify_entrypoint

        root = PROJECT_ROOT / "mcpserver"
        fails: list[str] = []
        for mp in root.glob("**/agent-manifest.json"):
            m = json.loads(mp.read_text(encoding="utf-8"))
            ok, reason = verify_entrypoint(m, mp.parent.name)
            if ok:
                continue
            decl = {e.get("name") if isinstance(e, dict) else e
                    for e in (m.get("requires") or {}).get("python_packages") or []}
            mm = _re.search(r"No module named '([\w.]+)'", reason or "")
            if mm and mm.group(1).split(".")[0] in decl:
                self.skipTest(f"{m.get('name')}: 缺已声明依赖 {mm.group(1)}（uv sync 后属预期）")
            fails.append(f"{m.get('name')}: {reason}")
        self.assertEqual(fails, [])

    def test_missing_entrypoint(self):
        """无 entryPoint → Format D 按目录名推导 mcpserver.<name>.<name>，
        模块不存在时在导入步失败（不会静默通过）。"""
        from mcpserver.mcp_registry import verify_entrypoint

        ok, reason = verify_entrypoint({"name": "no_such_agent_xx"}, "no_such_agent_xx")
        self.assertFalse(ok)
        self.assertTrue("模块导入失败" in reason or "缺少 entryPoint" in reason, reason)

    def test_module_not_importable(self):
        from mcpserver.mcp_registry import verify_entrypoint

        m = {"name": "x", "entryPoint": {"module": "mcpserver.no_such_mod_xx", "class": "X"}}
        ok, reason = verify_entrypoint(m, "x")
        self.assertFalse(ok)
        self.assertIn("模块导入失败", reason)

    def test_class_not_found(self):
        from mcpserver.mcp_registry import verify_entrypoint

        m = {"name": "agent_trivy",
             "entryPoint": {"module": "mcpserver.agent_trivy.agent_trivy", "class": "NoSuchClass"}}
        ok, reason = verify_entrypoint(m, "agent_trivy")
        self.assertFalse(ok)
        self.assertIn("不存在", reason)

    def test_missing_handoff_contract(self):
        """类存在但无 handle_handoff → 契约失败（本轮修的正是这类谎报）。"""
        from mcpserver.mcp_registry import verify_entrypoint

        mod = types.ModuleType("mcpserver._tmp_no_contract")

        class Bare:  # noqa: D401  合成模块：只有类，无契约
            pass

        mod.Bare = Bare  # type: ignore[attr-defined]
        sys.modules["mcpserver._tmp_no_contract"] = mod
        try:
            m = {"name": "x", "entryPoint": {"module": "mcpserver._tmp_no_contract", "class": "Bare"}}
            ok, reason = verify_entrypoint(m, "x")
            self.assertFalse(ok)
            self.assertIn("handle_handoff", reason)
        finally:
            del sys.modules["mcpserver._tmp_no_contract"]

    def test_module_outside_whitelist(self):
        from mcpserver.mcp_registry import verify_entrypoint

        m = {"name": "x", "entryPoint": {"module": "os.path", "class": "join"}}
        ok, reason = verify_entrypoint(m, "x")
        self.assertFalse(ok)
        self.assertIn("允许列表", reason)


class TestFixedAgentsSmoke(unittest.TestCase):
    """本轮修复的 6 个 agent + rf_brain：总线边界行为（错误落 JSON 不崩）。"""

    def test_invoke_family_unknown_tool_returns_json_error(self):
        """bofire / chembl / scikit_fingerprints：invoke fail-fast 抛 ValueError，
        handle_handoff 兜住落 JSON。"""
        for rel in ("bofire/agent-manifest.json",
                    "chembl/agent-manifest.json",
                    "scikit_fingerprints/agent-manifest.json"):
            with self.subTest(rel=rel):
                out = _handoff(rel, {"tool": "__nope__", "params": {}})
                self.assertEqual(out["status"], "error")
                self.assertIn("__nope__", out["error"])

    def test_dispatch_family_unknown_tool_lists_available(self):
        """firecrawl / graph_memory / semantic_web：按 tool 分发，未知工具列可用项。"""
        cases = {
            "firecrawl_adapter/agent-manifest.json": ["firecrawl_scrape_to_md"],
            "graph_memory_adapter/agent-manifest.json": ["graph_memory_remember"],
            "adapters/semantic_web/agent-manifest.json": ["load", "query_semantic"],
        }
        for rel, must_contain in cases.items():
            with self.subTest(rel=rel):
                out = _handoff(rel, {"tool": "__nope__", "params": {}})
                self.assertEqual(out["status"], "error")
                for tool in must_contain:
                    self.assertIn(tool, out["available"])

    def test_firecrawl_health_tool_runs(self):
        """分发型真实路径：health 不发抓取请求，应落 status。"""
        out = _handoff("firecrawl_adapter/agent-manifest.json",
                       {"tool": "firecrawl_health", "params": {}})
        self.assertIn("status", out)

    def test_semantic_web_default_is_query(self):
        """semantic_web 空 tool 默认走 query_semantic（未加载 → 空答案但不崩）。"""
        out = _handoff("adapters/semantic_web/agent-manifest.json", {"params": {}})
        self.assertEqual(out["status"], "ok")
        self.assertIn("answer", out)

    def test_rf_brain_manifest_points_to_agent_class(self):
        m = _manifest("rf_brain/agent-manifest.json")
        self.assertEqual(m["entryPoint"],
                         {"module": "mcpserver.rf_brain.agent", "class": "RfBrainAgent"})

    def test_rf_brain_missing_iq_path(self):
        out = _handoff("rf_brain/agent-manifest.json", {"tool": "run_loop", "params": {}})
        self.assertEqual(out, {"status": "error", "error": "missing_iq_path"})

    def test_rf_brain_loop_end_to_end(self):
        """闭环真实路径：合成正弦 IQ 赑感知→特征→决策→解调→反馈全链，
        断言链路通与 JSON 结构（不锁具体调制判决）。"""
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - venv 必有 numpy，防御性跳过
            self.skipTest("numpy 未安装")
        tmp = Path(tempfile.gettempdir()) / "rfbrain_test_iq.npy"
        sr = 48000.0
        t = np.arange(int(sr * 0.2)) / sr
        np.save(tmp, (0.6 * np.exp(2j * np.pi * 1200.0 * t)).astype(np.complex64))
        try:
            out = _handoff("rf_brain/agent-manifest.json", {
                "tool": "run_loop",
                "params": {"iq_path": str(tmp), "sample_rate": sr, "center_freq": 0},
            })
            self.assertEqual(out["status"], "ok")
            self.assertIn("modulation", out)
            self.assertIn("history", out)
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
