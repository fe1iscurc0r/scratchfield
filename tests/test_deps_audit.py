"""工单 228 任务二 · ``tools/deps_audit.py`` 扫描器回归测试。

全部在 ``tmp_path`` 合成沙箱上跑 —— 不依赖真实仓库内容，故不会因仓库演化而假红。
用 importlib 按路径加载脚本（与 ``tests/test_switch_llm_provider.py`` 同姿势，
避免 ``tools/tests/`` 抢顶层 ``tests`` 命名空间的老坑，见工单 225 病二）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("w228_deps_audit", ROOT / "tools" / "deps_audit.py")
D = importlib.util.module_from_spec(_spec)
sys.modules["w228_deps_audit"] = D
_spec.loader.exec_module(D)


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """合成一个最小仓：apiserver/ 三种 import 形式 + tests/ 一个 patch 点。"""
    (tmp_path / "apiserver").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "apiserver" / "a.py").write_text(
        "import pandas as pd\n"
        "from pandas import DataFrame\n"
        "import os, pandas\n"
        "import numpy as np\n"          # 无关库，不应命中
        "from pandasaurus import x\n",  # 前缀相似但不是 pandas，不应命中
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_a.py").write_text(
        "from unittest.mock import patch\n"
        "patch('pandas.read_csv')\n"
        "def test_noop():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(D, "ROOT", tmp_path)
    return tmp_path


def test_python_scanner_covers_import_forms(sandbox):
    hits = D.scan_imports_python("pandas", ("apiserver",))
    lines = sorted(h["line"] for h in hits)
    assert lines == [1, 2, 3], f"应命中三种 import 形式，实际: {hits}"
    assert all(h["file"] == "apiserver/a.py" for h in hits)


def test_python_scanner_ignores_lookalike_and_unrelated(sandbox):
    texts = [h["text"] for h in D.scan_imports_python("pandas", ("apiserver",))]
    assert not any("numpy" in t for t in texts)
    assert not any("pandasaurus" in t for t in texts), "前缀相似不得误命中"


def test_skip_dirs_are_honored(sandbox):
    """__pycache__ 等跳过集命中的目录不参与扫描。"""
    cache = sandbox / "apiserver" / "__pycache__"
    cache.mkdir()
    (cache / "b.py").write_text("import pandas\n", encoding="utf-8")
    hits = D.scan_imports_python("pandas", ("apiserver",))
    assert all("__pycache__" not in h["file"] for h in hits)


def test_mock_scanner_finds_patch_sites(sandbox):
    mocks = D.scan_mocks("pandas")
    assert len(mocks) == 1
    assert mocks[0]["file"] == "tests/test_a.py"
    assert mocks[0]["line"] == 2


def test_mock_scanner_ignores_plain_reference(sandbox):
    """只提到库名但没 mock/patch 的行不算 mock 点。"""
    (sandbox / "tests" / "test_b.py").write_text("import pandas\n", encoding="utf-8")
    files = {m["file"] for m in D.scan_mocks("pandas")}
    assert "tests/test_b.py" not in files


def test_missing_root_is_tolerated(sandbox):
    """不存在的根目录不炸，只是少一些命中。"""
    hits = D.scan_imports_python("pandas", ("apiserver", "does_not_exist"))
    assert len(hits) == 3


def test_decision_matrix_thresholds():
    assert D.decide(0).startswith("✅")
    assert D.decide(4).startswith("✅")
    assert D.decide(5).startswith("⚠️")
    assert D.decide(19).startswith("⚠️")
    assert D.decide(20).startswith("🛑")


def test_render_markdown_has_tables_and_decision(sandbox):
    imports, scanner = D.scan_imports("pandas", ("apiserver",), use_rg=False)
    mocks = D.scan_mocks("pandas")
    md = D.render_markdown("pandas", imports, mocks, scanner=scanner, roots=("apiserver",))
    assert "# 依赖落点审计 · `pandas`" in md
    assert "| # | 文件 | 行 | 原文 |" in md
    assert "## import 落点（3 处）" in md
    assert "决策（S4 矩阵）" in md
    assert scanner == "python"


def test_rg_and_python_scanners_agree(sandbox):
    """两条扫描路径对同一沙箱必须给出一致结果（否则 rg 路径不可信）。"""
    if not D.shutil.which("rg"):
        pytest.skip("本机无 ripgrep；回退路径已由上面各用例覆盖")
    rg_hits = D.scan_imports_rg("pandas", ("apiserver",))
    assert rg_hits is not None, "rg 存在却返回 None 说明调用异常"
    py_hits = D.scan_imports_python("pandas", ("apiserver",))
    assert D._dedupe(rg_hits) == D._dedupe(py_hits)


def test_cli_writes_markdown_and_json(sandbox, capsys, monkeypatch):
    monkeypatch.chdir(sandbox)
    rc = D.main(["pandas", "--roots", "apiserver", "--out-dir", "audit_out", "--no-rg"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "依赖落点审计" in out

    md_files = list((sandbox / "audit_out").glob("pandas-*.md"))
    json_files = list((sandbox / "audit_out").glob("pandas-*.json"))
    assert len(md_files) == 1 and len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["library"] == "pandas"
    assert payload["import_count"] == 3
    assert payload["mock_count"] == 1
    assert payload["scanner"] == "python"


def test_cli_no_write_leaves_no_files(sandbox, capsys):
    rc = D.main(["pandas", "--roots", "apiserver", "--out-dir", "audit_out", "--no-rg", "--no-write"])
    capsys.readouterr()
    assert rc == 0
    assert not (sandbox / "audit_out").exists()
