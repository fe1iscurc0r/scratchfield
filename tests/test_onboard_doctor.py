import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
# -*- coding: utf-8 -*-
"""onboard/doctor 测试：四层检查 / 报告 / 向导流程（隔离 config 不动真身）。"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import apiserver.doctor as doctor  # noqa: E402


class TestDoctor(unittest.TestCase):
    def test_static_layers_run(self):
        """静态三层（python/deps/config）能跑且产出结构化结果。"""
        report = doctor.run_doctor(probe=False, live_ports=False)
        names = [c.name for c in report.checks]
        self.assertIn("python_version", names)
        self.assertTrue(any(n.startswith("dep:") for n in names),
                        "依赖检查应产出 dep:* 项")
        self.assertTrue(any(n.startswith("config:") for n in names))
        # 本机实跑：依赖应全过（venv 健康）
        dep_fails = [c for c in report.checks
                     if c.name.startswith("dep:") and not c.ok]
        self.assertEqual(dep_fails, [], f"本机依赖不应缺: {dep_fails}")

    def test_report_format_and_json(self):
        report = doctor.run_doctor(probe=False, live_ports=False)
        text = doctor.format_report(report)
        self.assertIn("Lumo doctor", text)
        self.assertIn("项通过", text)
        d = report.to_dict()
        self.assertEqual(d["total"], len(report.checks))
        self.assertEqual(d["passed"], report.passed)
        self.assertIsInstance(d["ok"], bool)

    def test_config_missing_detected(self):
        """config.json 缺失时 config:file 检查应失败并给修复提示。"""
        with TemporaryDirectory() as tmp:
            with patch.object(doctor, "REPO_ROOT", Path(tmp)):
                report = doctor.DoctorReport()
                doctor.check_config(report)
                cfg_check = next(c for c in report.checks if c.name == "config:file")
                self.assertFalse(cfg_check.ok)
                self.assertIn("onboard", cfg_check.hint)

    def test_config_placeholder_detected(self):
        """占位符 key 应被判未配置。"""
        with TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "config.json").write_text(json.dumps(
                {"api": {"api_key": "YOUR_API_KEY",
                         "base_url": "https://x/v1", "model": "m"}}), encoding="utf-8")
            with patch.object(doctor, "REPO_ROOT", tmp_p):
                report = doctor.DoctorReport()
                doctor.check_config(report)
                key_check = next(c for c in report.checks
                                 if c.name == "config:api.api_key")
                self.assertFalse(key_check.ok, "占位符应报未配置")


class TestOnboard(unittest.TestCase):
    def test_noninteractive_flow(self):
        """非交互模式：--api-key 等参数 → config 生成+填充+缺项提示正确。"""
        from apiserver import onboard
        with TemporaryDirectory() as tmp:
            with patch.object(onboard, "REPO_ROOT", Path(tmp)), \
                 patch.object(onboard, "CONFIG_PATH", Path(tmp) / "config.json"), \
                 patch.object(onboard, "EXAMPLE_PATH", Path(tmp) / "nope.json"):
                rc = onboard.run_onboard(["--api-key=sk-test-123",
                                          "--base-url=https://api.example.com/v1",
                                          "--model=test-model"])
            # 三项全给 → rc 0
            self.assertEqual(rc, 0)
            cfg = json.loads((Path(tmp) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["api"]["api_key"], "sk-test-123")
            self.assertEqual(cfg["api"]["model"], "test-model")
            # channels 段存在（渠道网关默认配置）
            self.assertIn("channels", cfg)

    def test_noninteractive_missing_key_flagged(self):
        """非交互但缺 key → 返回 1 且 config 里留占位。"""
        from apiserver import onboard
        with TemporaryDirectory() as tmp:
            with patch.object(onboard, "REPO_ROOT", Path(tmp)), \
                 patch.object(onboard, "CONFIG_PATH", Path(tmp) / "config.json"), \
                 patch.object(onboard, "EXAMPLE_PATH", Path(tmp) / "nope.json"):
                # onboard 内部 import doctor 用的是真 REPO_ROOT 的 config——
                # 验证步骤读得到仓库真身，但填充流程用 patched CONFIG_PATH
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = onboard.run_onboard(["--model=only-model"])
            self.assertEqual(rc, 1)
            cfg = json.loads((Path(tmp) / "config.json").read_text(encoding="utf-8"))
            self.assertIn("YOUR_", cfg["api"]["api_key"], "未提供的项应留占位")

    def test_minimal_template_skeleton(self):
        """无 example 时生成最小骨架（含 channels 默认段）。"""
        from apiserver import onboard
        with TemporaryDirectory() as tmp:
            with patch.object(onboard, "REPO_ROOT", Path(tmp)), \
                 patch.object(onboard, "CONFIG_PATH", Path(tmp) / "config.json"), \
                 patch.object(onboard, "EXAMPLE_PATH", Path(tmp) / "nope.json"):
                ok, msg = onboard._ensure_config_file()
            self.assertTrue(ok)
            cfg = json.loads((Path(tmp) / "config.json").read_text(encoding="utf-8"))
            for need in ("api", "api_server", "agent_server", "mcp_server", "channels"):
                self.assertIn(need, cfg, f"最小骨架应含 {need}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
