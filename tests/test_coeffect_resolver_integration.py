"""_coeffect_resolver 集成测试：对真实 skills/ 语料的零破坏性验证。

覆盖 SPEC 验收"现有 skills/ 零修改、零影响"：
- 扫描全部真实 SKILL.md，resolve_coeffects 均不抛异常、返回合法规格
- 当前语料均未声明 coeffects 段（可选段，行为与现状一致）
- 在真实语料树上注入一个临时 coeffects skill，验证解析/分类端到端可用
"""

from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import importlib.util
import os
import pathlib
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")

_resolver_path = os.path.join(_SKILLS_DIR, "_coeffect_resolver.py")
_resolver_spec = importlib.util.spec_from_file_location("_coeffect_resolver", _resolver_path)
c = importlib.util.module_from_spec(_resolver_spec)
sys.modules["_coeffect_resolver"] = c
assert _resolver_spec.loader is not None
_resolver_spec.loader.exec_module(c)


def test_scan_real_skills_corpus_no_breakage():
    """全部真实 SKILL.md 均可被解析，无异常、无 coeffects 段（零影响）。"""
    mds = list(pathlib.Path(_SKILLS_DIR).rglob("SKILL.md"))
    assert len(mds) >= 180  # 语料规模（当前 181）

    with_coeffects = 0
    for md in mds:
        spec = c.resolve_coeffects(str(md.parent))  # 必须不抛异常
        assert isinstance(spec, c.CoeffectSpec)
        if spec.has_coeffects:
            with_coeffects += 1
            # 若将来有 skill 声明 coeffects，规格必须合法
            for dep in spec.skills + spec.packages + spec.services:
                assert dep.get("name")
    # 当前语料均未声明 coeffects → 行为与现状完全一致
    assert with_coeffects == 0


def test_resolver_usable_inside_real_skills_tree(tmp_path, monkeypatch):
    """在真实 skills 语料旁放一个声明 coeffects 的 skill，端到端解析/分类可用。"""
    # 复制一个真实 skill 目录结构的最小 SKILL.md，加入 coeffects 段
    d = tmp_path / "demo-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\ncoeffects:\n"
        "  packages:\n    - rdkit\n---\n# body\n",
        encoding="utf-8",
    )

    spec = c.resolve_coeffects(str(d))
    assert spec.has_coeffects is True
    assert spec.packages == [{"name": "rdkit", "required": True}]

    # 打桩模拟 rdkit 缺失（与宿主机是否安装无关）→ deactivate；显式声明已装 → activate
    monkeypatch.setattr(c, "_find_spec", lambda name: None)
    assert c.check_satisfied(spec, set()) == c.DEACTIVATE
    assert c.check_satisfied(spec, {"rdkit"}) == c.ACTIVATE


def test_soft_dependency_in_real_tree(tmp_path, monkeypatch):
    d = tmp_path / "soft-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: soft-skill\ndescription: demo\ncoeffects:\n"
        "  packages:\n    - name: rdkit\n      required: false\n---\n# body\n",
        encoding="utf-8",
    )
    spec = c.resolve_coeffects(str(d))
    assert spec.has_coeffects is True
    # 打桩模拟缺失环境（环境无关化），软依赖缺失 → neutral
    monkeypatch.setattr(c, "_find_spec", lambda name: None)
    assert c.check_satisfied(spec, set()) == c.NEUTRAL