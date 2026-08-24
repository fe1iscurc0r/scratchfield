"""_coeffect_resolver Skill 依赖声明解析/分类的单元测试。

覆盖 SPEC 验收：
- 声明 packages:[rdkit] 的 skill，无 rdkit 环境返回 deactivate、有 rdkit 返回 activate
- 无 coeffects 段的 skill 返回 neutral
- 软依赖缺失返回 neutral、硬依赖缺失返回 deactivate
- 现有 skills/ 零修改（仅新增本解析器）
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
# 用 importlib 加载，避免把 skills/ 加进 sys.path（否则 skill 子目录会变成命名空间包，
# 干扰 importlib.util.find_spec 对真实 pip 包的检测）
_resolver_path = os.path.join(_SKILLS_DIR, "_coeffect_resolver.py")
_resolver_spec = importlib.util.spec_from_file_location("_coeffect_resolver", _resolver_path)
c = importlib.util.module_from_spec(_resolver_spec)
sys.modules["_coeffect_resolver"] = c  # dataclass 需要注册到 sys.modules
assert _resolver_spec.loader is not None
_resolver_spec.loader.exec_module(c)


def _write_skill(tmp_path, frontmatter: str) -> str:
    d = pathlib.Path(str(tmp_path))
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n# body\n", encoding="utf-8")
    return str(d)


def test_resolve_bare_strings(tmp_path):
    d = _write_skill(tmp_path, "name: x\ndescription: d\ncoeffects:\n  packages:\n    - rdkit\n")
    spec = c.resolve_coeffects(d)
    assert spec.has_coeffects is True
    assert spec.packages == [{"name": "rdkit", "required": True}]


def test_resolve_skills_and_services(tmp_path):
    d = _write_skill(tmp_path,
                     "name: x\ncoeffects:\n  skills:\n    - datamol\n  services:\n    - neo4j\n")
    spec = c.resolve_coeffects(d)
    assert spec.skills == [{"name": "datamol", "required": True}]
    assert spec.services == [{"name": "neo4j", "required": True}]


def test_resolve_required_flag(tmp_path):
    d = _write_skill(tmp_path,
                     "name: x\ncoeffects:\n  packages:\n    - name: rdkit\n      required: false\n")
    spec = c.resolve_coeffects(d)
    assert spec.has_coeffects is True
    assert spec.packages == [{"name": "rdkit", "required": False}]


def test_no_coeffects_returns_neutral(tmp_path):
    d = _write_skill(tmp_path, "name: x\ndescription: d\n")
    spec = c.resolve_coeffects(d)
    assert spec.has_coeffects is False
    assert c.check_satisfied(spec, set()) == c.NEUTRAL


def test_missing_rdkit_deactivate(tmp_path):
    """沙箱无 rdkit → 硬依赖缺失 → deactivate。"""
    d = _write_skill(tmp_path, "name: x\ncoeffects:\n  packages:\n    - rdkit\n")
    spec = c.resolve_coeffects(d)
    assert c._find_spec("rdkit") is None  # 前置条件：当前环境确实无 rdkit
    assert c.check_satisfied(spec, set()) == c.DEACTIVATE


def test_rdkit_present_activate(tmp_path):
    d = _write_skill(tmp_path, "name: x\ncoeffects:\n  packages:\n    - rdkit\n")
    spec = c.resolve_coeffects(d)
    assert c.check_satisfied(spec, {"rdkit"}) == c.ACTIVATE


def test_soft_missing_returns_neutral(tmp_path):
    d = _write_skill(tmp_path,
                     "name: x\ncoeffects:\n  packages:\n    - name: rdkit\n      required: false\n")
    spec = c.resolve_coeffects(d)
    # 缺 rdkit 但声明为软依赖 → neutral（启用但降级）
    assert c.check_satisfied(spec, set()) == c.NEUTRAL


def test_skills_dependency(tmp_path):
    d = _write_skill(tmp_path, "name: x\ncoeffects:\n  skills:\n    - datamol\n")
    spec = c.resolve_coeffects(d)
    assert c.check_satisfied(spec, {"datamol"}) == c.ACTIVATE
    assert c.check_satisfied(spec, set()) == c.DEACTIVATE


def test_services_declarative_no_effect(tmp_path):
    d = _write_skill(tmp_path, "name: x\ncoeffects:\n  services:\n    - neo4j\n")
    spec = c.resolve_coeffects(d)
    # services 只声明不 ping → 不因缺服务去激活
    assert c.check_satisfied(spec, set()) == c.ACTIVATE