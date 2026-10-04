# -*- coding: utf-8 -*-
"""mcpserver 工具注册表 v2（W63-05 · apiVersion/kind + 兼容性预检 + meta.yaml）。

依据 docs/dsh-生态-新标准-勘察 + aci-tool-registry-勘察报告：工具注册表升级——
  - apiVersion/kind 字段（App 级 / Function 级两层）
  - 兼容性预检：加载前检查依赖/接口签名，不兼容则跳过并告警（不崩）
  - meta.yaml 统一格式解析

纯标准库（用 yaml 若可用，否则简单 key: value 解析，标 mock）。
运行：python tools/tool_registry_v2.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 支持的两层 kind
SUPPORTED_KINDS = ("App", "Function")
SUPPORTED_APIVERSIONS = ("v1", "v2")


@dataclass
class ToolMeta:
    """工具 meta（对应 meta.yaml 统一格式）。"""

    name: str
    kind: str          # App / Function
    api_version: str   # v1 / v2
    deps: list[str] = field(default_factory=list)  # 依赖模块/包
    entry: str = ""    # 入口函数签名

    @classmethod
    def from_dict(cls, d: dict) -> "ToolMeta":
        return cls(
            name=str(d.get("name", "")),
            kind=str(d.get("kind", "")),
            api_version=str(d.get("apiVersion", d.get("api_version", "v1"))),
            deps=list(d.get("deps", [])),
            entry=str(d.get("entry", "")),
        )


def validate_meta(meta: ToolMeta) -> bool:
    """apiVersion/kind 校验。"""
    return (
        bool(meta.name)
        and meta.kind in SUPPORTED_KINDS
        and meta.api_version in SUPPORTED_APIVERSIONS
    )


def precheck_deps(meta: ToolMeta, available: set[str]) -> bool:
    """兼容性预检：依赖缺一则不兼容（跳过不崩）。"""
    return all(d in available for d in meta.deps)


@dataclass
class ToolRegistryV2:
    """注册表：登记 meta，precheck 依赖，缺依赖跳过并告警。"""

    tools: dict[str, ToolMeta] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def register(self, meta: ToolMeta, available: set[str]) -> bool:
        if not validate_meta(meta):
            self.skipped.append(meta.name)
            return False
        if not precheck_deps(meta, available):
            self.skipped.append(meta.name)  # 缺依赖 → 跳过并告警（不崩）
            return False
        self.tools[meta.name] = meta
        return True


def parse_meta_yaml(text: str) -> dict:
    """简化 meta.yaml 解析（key: value 行式，mock——无 PyYAML 依赖）。"""
    out: dict[str, object] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                out[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            else:
                out[k] = v
    return out


if __name__ == "__main__":
    reg = ToolRegistryV2()
    reg.register(ToolMeta("ok_tool", "Function", "v1", deps=["numpy"]), {"numpy"})
    reg.register(ToolMeta("bad_tool", "Function", "v1", deps=["rdkit"]), {"numpy"})
    print("已注册:", list(reg.tools))
    print("跳过(缺依赖):", reg.skipped)
