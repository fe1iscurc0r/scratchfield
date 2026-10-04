"""统一 meta.yaml 的 JSON Schema 契约（声明式副本）。

meta.py 的 validate_meta 是自包含结构校验（不依赖 jsonschema 运行时）；
本目录的 meta_schema.json 是同一契约的 JSON Schema 表述，供机器校验
（jsonschema / 生成文档 / CI 门禁）复用。二者必须保持一致。
"""
from pathlib import Path

META_SCHEMA_PATH = Path(__file__).with_name("meta_schema.json")

__all__ = ["META_SCHEMA_PATH"]
