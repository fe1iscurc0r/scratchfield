"""CLI-Anything agent 模块单元测试（WO-10）。

覆盖：
- manifest 必须含 license 字段且 entryPoint 在白名单内
- list_cli_tools / search_capabilities 真实读 vendor checkout 数据
- CliAnythingAgent.handle_handoff 路由
- mcp_registry.create_agent_instance 能从 manifest 实例化 agent（白名单路径）
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scratchpad/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MANIFEST_PATH = PROJECT_ROOT / "mcpserver" / "agent_cli_anything" / "agent-manifest.json"


class TestCliAnythingManifest(unittest.TestCase):
    def test_manifest_has_required_fields_and_license(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("name"), "cli_anything")
        self.assertEqual(manifest.get("agentType"), "mcp")
        self.assertTrue(manifest.get("license"), "manifest 必须含非空 license 字段")
        self.assertEqual(manifest.get("license"), "Apache-2.0")

    def test_manifest_entrypoint_within_module_whitelist(self):
        from mcpserver.mcp_registry import ALLOWED_MODULE_PREFIXES

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        module = manifest["entryPoint"]["module"]
        self.assertTrue(
            any(module.startswith(prefix) for prefix in ALLOWED_MODULE_PREFIXES),
            f"entryPoint.module={module} 不在白名单 {ALLOWED_MODULE_PREFIXES}",
        )
        self.assertTrue(manifest["entryPoint"]["class"])

    def test_manifest_declares_two_commands(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        commands = [c["command"] for c in manifest["capabilities"]["invocationCommands"]]
        self.assertIn("list_cli_tools", commands)
        self.assertIn("search_capabilities", commands)


class TestCliAnythingTools(unittest.TestCase):
    def test_list_cli_tools_returns_real_registry_data(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import list_cli_tools

        result = list_cli_tools()
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["data"]["total"], 10, "vendor registry 应含至少 10 个 CLI")
        for tool in result["data"]["tools"]:
            self.assertTrue(tool.get("name"), "每条工具必须含 name 字段")

    def test_list_cli_tools_query_gimp(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import list_cli_tools

        result = list_cli_tools(query="gimp")
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["data"]["total"], 1)
        self.assertTrue(any(t["name"] == "gimp" for t in result["data"]["tools"]))

    def test_list_cli_tools_category_image(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import list_cli_tools

        result = list_cli_tools(category="image")
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["data"]["total"], 1)
        for tool in result["data"]["tools"]:
            self.assertEqual(tool["category"], "image")

    def test_list_cli_tools_source_public(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import list_cli_tools

        result = list_cli_tools(source="public")
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["data"]["total"], 1)
        for tool in result["data"]["tools"]:
            self.assertEqual(tool["source"], "public")

    def test_search_capabilities_video(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import search_capabilities

        result = search_capabilities("video")
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["data"]["total"], 1)
        for hit in result["data"]["matched_capabilities"]:
            self.assertTrue(hit["capability_id"])
            self.assertTrue(hit["match_field"])

    def test_search_capabilities_requires_query(self):
        from mcpserver.agent_cli_anything.cli_anything_tools import search_capabilities

        result = search_capabilities("")
        self.assertEqual(result["status"], "error")


class TestCliAnythingAgent(unittest.TestCase):
    def test_handle_handoff_list_route(self):
        from mcpserver.agent_cli_anything import CliAnythingAgent

        agent = CliAnythingAgent()
        raw = asyncio.run(agent.handle_handoff({"tool_name": "list_cli_tools", "source": "harness"}))
        data = json.loads(raw)
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["data"]["total"], 1)

    def test_handle_handoff_search_route(self):
        from mcpserver.agent_cli_anything import CliAnythingAgent

        agent = CliAnythingAgent()
        raw = asyncio.run(agent.handle_handoff({"tool_name": "search_capabilities", "query": "audio"}))
        data = json.loads(raw)
        self.assertEqual(data["status"], "success")

    def test_handle_handoff_unknown_tool(self):
        from mcpserver.agent_cli_anything import CliAnythingAgent

        agent = CliAnythingAgent()
        raw = asyncio.run(agent.handle_handoff({"tool_name": "nope"}))
        data = json.loads(raw)
        self.assertEqual(data["status"], "error")

    def test_handle_handoff_missing_tool_name(self):
        from mcpserver.agent_cli_anything import CliAnythingAgent

        agent = CliAnythingAgent()
        raw = asyncio.run(agent.handle_handoff({}))
        data = json.loads(raw)
        self.assertEqual(data["status"], "error")


class TestRegistryInstantiation(unittest.TestCase):
    def test_create_agent_instance_from_manifest(self):
        from mcpserver import mcp_registry
        from mcpserver.agent_cli_anything import CliAnythingAgent

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        instance = mcp_registry.create_agent_instance(manifest, "agent_cli_anything")
        self.assertIsNotNone(instance, "create_agent_instance 应能按 manifest 白名单路径实例化")
        self.assertIsInstance(instance, CliAnythingAgent)


if __name__ == "__main__":
    unittest.main()
