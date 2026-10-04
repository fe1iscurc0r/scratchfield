"""meta.py — 统一 meta.yaml 的加载 / 校验 / 索引（S-02）。

照 aci 两层结构（授粉自 aci `app.json` + `functions.json`，仅结构重写）：
- app 层：工具的资源身份（name / display_name / version / description /
  categories / families / domains / tier / origin /
  security_schemes / visibility / active / entrypoint）
- function 层：单个可调用接口（name / description / parameters[JSON Schema] / tags）

校验纪律：只做结构校验（必填字段 + 类型 + parameters 是否为 JSON Schema），
不引 jsonschema 运行时依赖——`schemas/meta_schema.json` 是同一契约的声明式副本，
供需要机器校验的上层（或测试）使用。非法输入抛 MetaValidationError，不吞错。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


class MetaValidationError(ValueError):
    """meta.yaml 结构非法（必填缺失 / 类型错误 / parameters 非 JSON Schema）。"""


@dataclass(frozen=True)
class MetaFunction:
    """function 层：单个可调用工具接口。"""
    name: str
    description: str
    parameters: dict[str, Any]            # JSON Schema（type=object + properties）
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetaApp:
    """app 层：工具的资源身份 + 其 functions 清单。"""
    name: str
    display_name: str
    version: str = ""
    description: str = ""
    categories: tuple[str, ...] = ()          # 细粒度主题词（**不放领域名**）
    families: tuple[str, ...] = ()            # 族：干什么（见 docs/总线能力标签体系）
    domains: tuple[str, ...] = ()             # 域：谁用（空 = 跨领域通用）
    tier: str = ""                            # 谁能开（read-only/local-write/process-control/offensive）
    origin: dict[str, Any] = field(default_factory=dict)  # 怎么来的（kind/upstream/upstream_license）
    security_schemes: dict[str, Any] = field(default_factory=dict)
    visibility: str = "public"
    active: bool = True
    entrypoint: dict[str, str] | None = None   # {module, class}
    functions: tuple[MetaFunction, ...] = ()

    def function(self, name: str) -> MetaFunction | None:
        """按名查 function（不存在返回 None）。"""
        for fn in self.functions:
            if fn.name == name:
                return fn
        return None


# --------------------------------------------------------------------------- #
# 加载 / 校验
# --------------------------------------------------------------------------- #

def load_meta(path: str | Path) -> dict[str, Any]:
    """读一个 meta.yaml 文件为 dict（pyyaml 标准格式）。"""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        raise MetaValidationError(f"meta.yaml 为空: {path}")
    if not isinstance(data, dict):
        raise MetaValidationError(f"meta.yaml 顶层必须是对象: {path}")
    return data


def _require_str(d: dict, key: str, where: str, allow_empty: bool = False) -> str:
    v = d.get(key)
    if v is None or not isinstance(v, str) or (not allow_empty and not v.strip()):
        raise MetaValidationError(f"{where}.{key} 必填且为非空字符串")
    return v


def _validate_function(f: Any, idx: int) -> MetaFunction:
    if not isinstance(f, dict):
        raise MetaValidationError(f"functions[{idx}] 必须是对象")
    where = f"functions[{idx}]"
    name = _require_str(f, "name", where)
    description = f.get("description")
    if description is None or not isinstance(description, str):
        raise MetaValidationError(f"{where}.description 必填且为字符串")
    parameters = f.get("parameters")
    if (not isinstance(parameters, dict)
            or parameters.get("type") != "object"
            or not isinstance(parameters.get("properties"), dict)):
        raise MetaValidationError(
            f"{where}.parameters 必须是 JSON Schema：type=object 且含 properties 对象")
    tags = tuple(str(t) for t in (f.get("tags") or []))
    return MetaFunction(name=name, description=description,
                        parameters=parameters, tags=tags)


def validate_meta(data: dict[str, Any]) -> MetaApp:
    """校验统一 meta 结构并返回 MetaApp；非法抛 MetaValidationError。"""
    if not isinstance(data, dict):
        raise MetaValidationError("meta 顶层必须是对象")

    app = data.get("app")
    if not isinstance(app, dict):
        raise MetaValidationError("缺少 app 层（对象）")
    name = _require_str(app, "name", "app")
    display_name = app.get("display_name")
    if display_name is None or not isinstance(display_name, str):
        display_name = name  # display_name 缺省回退到 name
    version = str(app.get("version") or "")
    description = app.get("description") or ""
    categories = tuple(str(c) for c in (app.get("categories") or []))
    families = tuple(str(c) for c in (app.get("families") or []))
    domains = tuple(str(c) for c in (app.get("domains") or []))
    tier = str(app.get("tier") or "")
    origin = app.get("origin") or {}
    if not isinstance(origin, dict):
        raise MetaValidationError("app.origin 必须是对象")
    security_schemes = app.get("security_schemes") or {}
    if not isinstance(security_schemes, dict):
        raise MetaValidationError("app.security_schemes 必须是对象")
    visibility = str(app.get("visibility") or "public")
    active = bool(app.get("active", True))
    entrypoint = app.get("entrypoint")
    if entrypoint is not None and not isinstance(entrypoint, dict):
        raise MetaValidationError("app.entrypoint 必须是 {module, class} 对象")

    functions_raw = data.get("functions")
    if not isinstance(functions_raw, list):
        raise MetaValidationError("缺少 functions 层（数组）")
    functions = tuple(_validate_function(f, i)
                      for i, f in enumerate(functions_raw))
    seen = set()
    for fn in functions:
        if fn.name in seen:
            raise MetaValidationError(f"function 名重复: {fn.name!r}")
        seen.add(fn.name)

    return MetaApp(
        name=name, display_name=display_name, version=version,
        description=description, categories=categories,
        families=families, domains=domains, tier=tier, origin=origin,
        security_schemes=security_schemes, visibility=visibility,
        active=active, entrypoint=entrypoint, functions=functions,
    )


def load_and_validate(path: str | Path) -> MetaApp:
    """读 + 校验一个 meta.yaml 文件。"""
    return validate_meta(load_meta(path))


# --------------------------------------------------------------------------- #
# 索引
# --------------------------------------------------------------------------- #

def build_index(apps: Iterable[MetaApp]) -> dict[str, MetaApp]:
    """app.name → MetaApp 一级索引（重复 name 抛错，防静默覆盖）。"""
    index: dict[str, MetaApp] = {}
    for app in apps:
        if app.name in index:
            raise MetaValidationError(f"app name 重复: {app.name!r}")
        index[app.name] = app
    return index
