# -*- coding: utf-8 -*-
"""tool_registry_v2 测试（W63-05 验收：缺依赖跳过不崩 + meta.yaml 可解析）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from tool_registry_v2 import ToolMeta, ToolRegistryV2, parse_meta_yaml, validate_meta


def test_validate_meta_requires_kind_and_apiversion():
    assert validate_meta(ToolMeta("t", "Function", "v1")) is True
    assert validate_meta(ToolMeta("", "Function", "v1")) is False
    assert validate_meta(ToolMeta("t", "BadKind", "v1")) is False
    assert validate_meta(ToolMeta("t", "Function", "v9")) is False


def test_missing_dep_skipped_not_crash():
    reg = ToolRegistryV2()
    reg.register(ToolMeta("a", "Function", "v1", deps=["numpy"]), {"numpy"})
    reg.register(ToolMeta("b", "Function", "v1", deps=["rdkit"]), {"numpy"})
    assert "a" in reg.tools
    assert "b" not in reg.tools
    assert "b" in reg.skipped  # 缺依赖被跳过


def test_parse_meta_yaml():
    d = parse_meta_yaml("name: x\nkind: Function\napiVersion: v2\ndeps: [numpy, scipy]")
    assert d["name"] == "x"
    assert d["kind"] == "Function"
    assert d["deps"] == ["numpy", "scipy"]


def test_parse_meta_yaml_skips_comments():
    d = parse_meta_yaml("# comment\nname: x\nkind: Function\napiVersion: v2")
    assert d["name"] == "x"
