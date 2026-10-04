"""卷176-A 验收测试：论文 digest 对账逻辑（构造数据，零网络）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> tools/ -> 仓库根
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load():
    spec = importlib.util.spec_from_file_location(
        "paper_reconcile_under_test", PROJECT_ROOT / "tools" / "paper_reconcile.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _load()


def _make_data(tmp_path: Path, failed_lines: list[str], landed: list[str]) -> Path:
    data = tmp_path / "papers"
    (data / "digests" / "full").mkdir(parents=True)
    (data / "failed.txt").write_text("\n".join(failed_lines) + "\n", encoding="utf-8")
    for pid in landed:
        (data / "digests" / "full" / f"{pid}.md").write_text("x", encoding="utf-8")
    return data


class TestParse:
    def test_parse_formats(self):
        assert pr.parse_failed_line("2609.09033v1") == ("2609.09033v1", "")
        assert pr.parse_failed_line("2609.1 | 429 rate limit") == ("2609.1", "429 rate limit")
        assert pr.parse_failed_line("2609.2,content 过短") == ("2609.2", "content 过短")
        assert pr.parse_failed_line("") is None
        assert pr.parse_failed_line("# 注释") is None

    def test_classify(self):
        assert pr.classify("content 过短") == "permanent"
        assert pr.classify("content=72 字") == "permanent"
        assert pr.classify("429 rate limit") == "active"
        assert pr.classify("502 bad gateway") == "active"
        assert pr.classify("403 forbidden") == "active"  # IP/单篇级由调用方探测，不在此归类
        assert pr.classify("未知原因") == "active"       # 未知不静默归类为永久


class TestReconcile:
    def test_already_landed_is_removed(self, tmp_path):
        data = _make_data(tmp_path, ["a.1", "b.2"], ["a.1"])
        r = pr.reconcile(data / "failed.txt", data / "digests" / "full")
        assert r["stats"]["total"] == 2
        assert r["stats"]["already"] == 1
        assert [p for p, _ in r["active"]] == ["b.2"]

    def test_permanent_and_active_split(self, tmp_path):
        data = _make_data(tmp_path,
                          ["p.1\t429 rate limit", "p.2\tcontent 过短", "p.3\t502 bad gateway"],
                          [])
        r = pr.reconcile(data / "failed.txt", data / "digests" / "full")
        s = r["stats"]
        assert s["active"] == 2 and s["permanent"] == 1
        assert s["self_consistent"] is True
        assert s["total"] == s["already"] + s["active"] + s["permanent"]

    def test_outputs_written_with_self_consistency(self, tmp_path):
        data = _make_data(tmp_path, ["x.1\t429", "x.2\tcontent=5 字"], ["x.0"])
        # 注意 x.0 未在 failed 里 → total 只数 failed 行
        r = pr.reconcile(data / "failed.txt", data / "digests" / "full")
        out = pr.write_outputs(r, data, today="2026-09-30")
        assert out.name == "reconcile-report-2026-09-30.md"
        text = out.read_text(encoding="utf-8")
        assert "自洽校验" in text and "✓" in text
        active = (data / "failed_active.txt").read_text(encoding="utf-8")
        permanent = (data / "failed_permanent.txt").read_text(encoding="utf-8")
        assert "x.1" in active and "x.2" in permanent
        assert "x.2" not in active


class TestCli:
    def test_missing_data_dir_returns_2_with_guidance(self, tmp_path, capsys):
        rc = pr.main(["--data-dir", str(tmp_path / "nowhere")])
        assert rc == 2
        err = capsys.readouterr().err
        assert "阻塞" in err or "流水线主机" in err

    def test_check_returns_0_when_consistent(self, tmp_path):
        data = _make_data(tmp_path, ["y.1\t429"], [])
        rc = pr.main(["--data-dir", str(data), "--check"])
        assert rc == 0
