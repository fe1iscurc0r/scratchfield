"""F-02 外来文件接入审查门验收测试（≥6 用例）。

验收标准（源自 TRAE_WORKORDER_PROMPT_AGENT_FOXTROT.md）：
- 干净文件 PASS / 无 LICENSE WARN / 危险模式 FAIL / 大二进制标记 / 目录递归 / 报告输出
"""

from mcpserver.trace_audit.gate import run_gate
from mcpserver.trace_audit.liccheck import check_license

MIT_LICENSE = (
    "MIT License\n\n"
    "Copyright (c) 2026 Example\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    "of this software and associated documentation files (the \"Software\"), to deal\n"
    "in the Software without restriction.\n"
)


class TestLiccheck:
    def test_mit_spdx_detected(self, tmp_path):
        (tmp_path / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        lc = check_license(tmp_path)
        assert lc.found is True
        assert lc.spdx_id == "MIT"

    def test_noassertion_marked(self, tmp_path):
        (tmp_path / "LICENSE").write_text("Some custom terms, no recognizable license.", encoding="utf-8")
        lc = check_license(tmp_path)
        assert lc.found is True
        assert lc.noassertion is True


class TestGate:
    def test_clean_file_pass(self, tmp_path):
        (tmp_path / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        (tmp_path / "ok.py").write_text("x = 1\nprint(x)\n", encoding="utf-8")
        rep = run_gate(tmp_path)
        assert rep.verdict == "PASS"

    def test_no_license_warn(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        rep = run_gate(tmp_path)
        assert rep.verdict == "WARN"
        assert any(r.kind == "license" for r in rep.risks)

    def test_dangerous_pattern_fail(self, tmp_path):
        (tmp_path / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        (tmp_path / "bad.py").write_text("import subprocess\nsubprocess.run(['id'])\n", encoding="utf-8")
        rep = run_gate(tmp_path)
        assert rep.verdict == "FAIL"
        assert any(r.kind == "danger" for r in rep.risks)

    def test_large_binary_marked(self, tmp_path):
        (tmp_path / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02" * 1000)
        rep = run_gate(tmp_path)
        assert any(r.kind == "binary" for r in rep.risks)

    def test_directory_recursive(self, tmp_path):
        (tmp_path / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        sub = tmp_path / "nested" / "deep"
        sub.mkdir(parents=True)
        (sub / "evil.py").write_text("import os\nos.system('echo hi')\n", encoding="utf-8")
        rep = run_gate(tmp_path)
        assert rep.verdict == "FAIL"
        assert any("evil.py" in (r.path or "") for r in rep.risks)

    def test_report_output(self, tmp_path):
        (tmp_path / "bad.py").write_text("eval('1')\n", encoding="utf-8")
        rep = run_gate(tmp_path)
        text = rep.to_text()
        assert "GATE VERDICT" in text
        assert rep.verdict in {"PASS", "WARN", "FAIL"}
        assert any(r.kind == "danger" for r in rep.risks)
