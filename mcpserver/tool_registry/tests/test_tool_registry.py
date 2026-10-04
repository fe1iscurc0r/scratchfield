"""S-02 Lumo 工具统一 meta.yaml 验收测试。

覆盖：
  1. meta.yaml 校验（合法 → MetaApp；缺 app.name / 缺 function.parameters → 报错）
  2. 索引构建（app.name → MetaApp；function 按名查找）
  3. 三库发现（bofire / pycalphad / smiles_transformer 三个 meta.yaml）
  4. 旧 manifest 兼容转换（agent-manifest.json → 统一 meta，参数升级为 JSON Schema）
  5. 参数 schema 校验（parameters 为 type=object + properties；整体过 JSON Schema）

运行：python -m pytest mcpserver/tool_registry/tests/ -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcpserver.tool_registry.meta import (
    MetaApp,
    MetaValidationError,
    build_index,
    load_and_validate,
    load_meta,
    validate_meta,
)
from mcpserver.tool_registry.registry import (
    convert_manifest_to_meta,
    discover_meta_files,
    scan_manifest_dir,
)

_REPO = Path(__file__).resolve().parents[3]          # scratchpad/
_REGISTRY_DIR = Path(__file__).resolve().parents[1]  # mcpserver/tool_registry/

_LEGACY_MANIFEST = {
    "name": "demo",
    "displayName": "演示工具",
    "version": "1.0.0",
    "description": "兼容转换演示",
    "entryPoint": {"module": "mcpserver.demo.agent", "class": "DemoAgent"},
    "capabilities": {
        "invocationCommands": [
            {"command": "demo_hello", "description": "打招呼",
             "params": {"name": "要问候的名字"}},
            {"command": "demo_add", "description": "求和",
             "params": {"a": "加数", "b": "加数"}},
        ]
    },
}


# --------------------------------------------------------------------------- #
# 1. meta.yaml 校验
# --------------------------------------------------------------------------- #

def test_validate_meta_ok():
    app = load_and_validate(_REGISTRY_DIR / "bofire.yaml")
    assert isinstance(app, MetaApp)
    assert app.name == "bofire" and app.display_name == "BoFire 实验设计"
    assert len(app.functions) == 3
    names = [f.name for f in app.functions]
    assert names == ["bofire_define_domain", "bofire_ask_candidates",
                     "bofire_tell_results"]


def test_validate_meta_missing_app_name():
    with pytest.raises(MetaValidationError):
        validate_meta({"app": {"display_name": "无 name"}, "functions": []})


def test_validate_meta_function_missing_parameters():
    with pytest.raises(MetaValidationError):
        validate_meta({
            "app": {"name": "x"},
            "functions": [{"name": "fn", "description": "缺 parameters"}],
        })


def test_validate_meta_function_bad_parameters_schema():
    # parameters 缺 properties / type != object → 报错
    with pytest.raises(MetaValidationError):
        validate_meta({
            "app": {"name": "x"},
            "functions": [{"name": "fn", "description": "d",
                           "parameters": {"type": "string"}}],
        })


# --------------------------------------------------------------------------- #
# 2. 索引构建 + 3. 三库发现
# --------------------------------------------------------------------------- #

def test_discover_three_metas():
    apps = discover_meta_files(_REGISTRY_DIR)
    names = {a.name for a in apps}
    assert {"bofire", "pycalphad", "smiles_transformer"} <= names
    assert len(apps) >= 3


def test_build_index_and_lookup():
    apps = discover_meta_files(_REGISTRY_DIR)
    index = build_index(apps)
    assert "bofire" in index and "pycalphad" in index
    fn = index["bofire"].function("bofire_ask_candidates")
    assert fn is not None and fn.name == "bofire_ask_candidates"
    assert index["bofire"].function("no_such_fn") is None


# --------------------------------------------------------------------------- #
# 4. 旧 manifest 兼容转换
# --------------------------------------------------------------------------- #

def test_convert_old_manifest():
    app = convert_manifest_to_meta(_LEGACY_MANIFEST)
    assert isinstance(app, MetaApp)
    assert app.name == "demo" and app.display_name == "演示工具"
    assert app.entrypoint == {"module": "mcpserver.demo.agent",
                              "class": "DemoAgent"}
    assert [f.name for f in app.functions] == ["demo_hello", "demo_add"]


def test_convert_manifest_params_upgrade_to_json_schema():
    app = convert_manifest_to_meta(_LEGACY_MANIFEST)
    hello = app.function("demo_hello")
    assert hello is not None
    schema = hello.parameters
    assert schema["type"] == "object"
    assert schema["properties"]["name"] == {
        "type": "string", "description": "要问候的名字"}
    assert schema["required"] == []
    assert schema["additionalProperties"] is False


def test_scan_real_manifests_finds_i_line_three():
    apps = scan_manifest_dir(_REPO)
    names = {a.name for a in apps}
    # I 线已封装三库（bofire/chembl/scikit_fingerprints）应能被统一转换发现
    assert {"bofire", "chembl", "scikit_fingerprints"} <= names


# --------------------------------------------------------------------------- #
# 5. 参数 schema 校验（整体过 JSON Schema）
# --------------------------------------------------------------------------- #

def test_meta_files_pass_json_schema():
    from jsonschema import Draft7Validator

    from mcpserver.tool_registry.schemas import META_SCHEMA_PATH
    schema = json.loads(META_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    for yaml_file in _REGISTRY_DIR.glob("*.yaml"):
        data = load_meta(yaml_file)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        assert not errors, f"{yaml_file.name} 未过 schema: {errors}"


if __name__ == "__main__":
    test_validate_meta_ok()
    test_validate_meta_missing_app_name()
    test_validate_meta_function_missing_parameters()
    test_validate_meta_function_bad_parameters_schema()
    test_discover_three_metas()
    test_build_index_and_lookup()
    test_convert_old_manifest()
    test_convert_manifest_params_upgrade_to_json_schema()
    test_scan_real_manifests_finds_i_line_three()
    test_meta_files_pass_json_schema()
    print("\n🎉 S-02 tool_registry 全部自测通过")
