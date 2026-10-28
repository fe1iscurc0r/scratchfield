"""`tools/toolknit_license_audit.py` 的**离线**单测（工单244e）。

为什么要有
----------
那个审计脚本要联网跑 `npm install`，**不能进 CI**。但它的**判定逻辑**全是纯函数，
而 244b 第一版正好在这三处栽过跟头 —— 把这三条钉成离线用例，等于把踩过的坑变成回归：

1. ``OR`` 表达式误判：``(MIT OR GPL-3.0-or-later)``（jszip）被朴素子串命中判成**强 copyleft**
2. 子路径 shim 未过滤：``chart.js/auto/package.json`` 这类包内**子路径清单**
   被当成独立包，凭空多出 ``chart.js-auto@`` 这种空版本条目
3. 「已受理例外」缺失：``buffers@0.1.1`` 无许可声明 ⇒ ``--strict`` **永远红**
   ⇒ 检查没人用 ⇒ 等于没有

本文件**不联网、不调用 npm**。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "tools" / "toolknit_license_audit.py"


def _load_audit():
    """按文件路径加载审计脚本（`tools/` 不是包，不能 import 语句导入）。"""
    spec = importlib.util.spec_from_file_location("_tk_license_audit", AUDIT_PATH)
    assert spec and spec.loader, f"无法加载 {AUDIT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit_mod = _load_audit()


# ------------------------------------------------------------------ ① SPDX 分类


@pytest.mark.parametrize(("expr", "expected"), [
    ("MIT", "PERMISSIVE"),
    ("ISC", "PERMISSIVE"),
    ("Apache-2.0", "PERMISSIVE"),
    ("Apache-2.0 WITH LLVM-exception", "PERMISSIVE"),
    ("BSD-3-Clause", "PERMISSIVE"),
    ("MIT/X11", "PERMISSIVE"),
    ("0BSD", "PERMISSIVE"),
    ("Unlicense", "PERMISSIVE"),
    ("GPL-3.0-only", "STRONG-COPYLEFT"),
    ("AGPL-3.0", "STRONG-COPYLEFT"),
    ("LGPL-2.1", "WEAK-COPYLEFT"),
    ("MPL-2.0", "WEAK-COPYLEFT"),
    ("", "UNKNOWN"),
    ("SEE LICENSE IN FOO", "UNKNOWN"),
])
def test_classify_single_expression(expr, expected):
    assert audit_mod.classify(expr) == expected


def test_classify_or_with_permissive_branch_is_electable():
    """⭐ 244b 第一版的坑：`(MIT OR GPL-3.0-or-later)` 是**可选宽松分支 ⇒ 不传染**。

    朴素子串命中会把 `GPL-3.0` 判成强 copyleft —— 那会让 `--strict` 假红。
    """
    assert audit_mod.classify("(MIT OR GPL-3.0-or-later)") == "ELECTABLE-PERMISSIVE"
    assert audit_mod.classify("MIT OR GPL-3.0-only") == "ELECTABLE-PERMISSIVE"
    assert audit_mod.classify("GPL-3.0-only OR LGPL-2.1") == "STRONG-COPYLEFT"


def test_classify_and_takes_strictest():
    assert audit_mod.classify("(MIT AND Zlib)") == "PERMISSIVE"
    assert audit_mod.classify("MIT AND GPL-3.0-only") == "STRONG-COPYLEFT"


def test_classify_unknown_outranks_permissive_in_and():
    """AND 里只要有一项认不出，就不能报 PERMISSIVE（宁可保守）。"""
    assert audit_mod.classify("MIT AND SEE-LICENSE-IN-FOO") == "UNKNOWN"


# ------------------------------------------------------ ② npm 布局：只认真包


@pytest.mark.parametrize(("rel", "is_pkg"), [
    ("x/node_modules/foo/package.json", True),
    ("x/node_modules/@scope/foo/package.json", True),
    ("x/node_modules/a/node_modules/b/package.json", True),
    # ⭐ 244b 第一版的坑：包内**子路径 shim**（chart.js 会附 auto/、helpers/）
    ("x/node_modules/chart.js/auto/package.json", False),
    ("x/node_modules/chart.js/helpers/package.json", False),
    ("x/node_modules/music-tempo/docs/package.json", False),
    # 不在 node_modules 下的
    ("package.json", False),
])
def test_is_package_manifest(rel, is_pkg):
    assert audit_mod._is_package_manifest(Path(rel)) is is_pkg


# ------------------------------------------------- ③ 已受理例外让 --strict 可用


def _report(verdicts: dict[str, list[str]], *, sets_match: bool = True) -> dict:
    return {
        "verdicts": verdicts,
        "sets_match": sets_match,
        "only_on_disk": [],
        "only_in_tree": [],
    }


def test_accepted_exception_is_not_reported_as_risk():
    """⭐ 已受理的条目**不应**出现在 `risky()` 里 —— 否则 `--strict` 永远红。"""
    rep = _report({"UNKNOWN": ["buffers@0.1.1"], "PERMISSIVE": ["a@1.0.0"]})
    assert audit_mod.risky(rep) == []
    notes = audit_mod.accepted_note(rep)
    assert len(notes) == 1 and "buffers@0.1.1" in notes[0]


def test_new_unknown_is_still_reported():
    """但**新增**的未声明包必须照旧报 —— 受理清单不能变成「一劳永逸的豁免」。"""
    rep = _report({"UNKNOWN": ["buffers@0.1.1", "brand-new-pkg@9.9.9"]})
    problems = audit_mod.risky(rep)
    assert len(problems) == 1 and "brand-new-pkg@9.9.9" in problems[0]
    assert "buffers@0.1.1" not in problems[0]


def test_new_copyleft_is_reported():
    rep = _report({"STRONG-COPYLEFT": ["evil@1.0.0"]})
    assert any("STRONG-COPYLEFT" in p for p in audit_mod.risky(rep))


def test_set_mismatch_always_reported():
    """集合对不上 ⇒ 结论不可信，即使没有 copyleft 也要报。"""
    rep = _report({"PERMISSIVE": ["a@1.0.0"]}, sets_match=False)
    assert any("不一致" in p for p in audit_mod.risky(rep))


def test_accepted_list_entries_carry_reason_and_guard():
    """受理清单的每条都必须**写清理由 + 指认守着它的测试**（不能是口头豁免）。"""
    assert audit_mod.ACCEPTED_EXCEPTIONS, "受理清单不该为空（当前应含 buffers@0.1.1）"
    for key, reason in audit_mod.ACCEPTED_EXCEPTIONS.items():
        assert "@" in key, f"{key} 应写成 name@version"
        assert len(reason) > 60, f"{key} 的理由太短，写不清为什么可接受"
        assert "test_" in reason, f"{key} 的理由必须指认守着它的回归测试"


def test_audit_script_is_pure_stdlib_offline():
    """审计脚本必须纯标准库（要在干净环境里能跑），且本文件不联网。"""
    src = AUDIT_PATH.read_text(encoding="utf-8")
    for banned in ("requests", "httpx", "urllib.request"):
        assert banned not in src, f"审计脚本引用了 {banned}（应只用标准库 subprocess 驱动 npm）"
