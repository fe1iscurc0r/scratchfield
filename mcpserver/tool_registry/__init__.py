"""Lumo 材料工具统一注册中心（S 线）。

「工具即资源」：BoFire / pycalphad / smiles-transformer 等材料实验工具，
用统一 meta.yaml（aci 两层：app 元数据 + function 调用接口）登记，
可被统一发现、索引、按 JSON Schema 校验参数。

核心模块：
- meta.py      加载 / 校验 / 索引 meta.yaml（两层结构）
- registry.py  旧 agent-manifest.json 兼容转换 + 目录发现
- schemas/     统一 meta.yaml 的 JSON Schema（声明式契约）
"""
from mcpserver.tool_registry.meta import (  # noqa: F401
    MetaApp,
    MetaFunction,
    MetaValidationError,
    build_index,
    load_and_validate,
    load_meta,
    validate_meta,
)
from mcpserver.tool_registry.registry import (  # noqa: F401
    convert_manifest_to_meta,
    discover_meta_files,
    scan_manifest_dir,
)

__all__ = [
    "MetaApp",
    "MetaFunction",
    "MetaValidationError",
    "load_meta",
    "validate_meta",
    "load_and_validate",
    "build_index",
    "convert_manifest_to_meta",
    "discover_meta_files",
    "scan_manifest_dir",
]
