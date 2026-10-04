"""可插拔故障注入器（E-01）。

拦截 MCP 调用链，按配置注入故障，支持 once / persistent / random 三种模式。
集成方式（均不侵入 mcp_server 主流程）：

1. inject(func)：包裹一个 async 可调用，返回带故障注入的 async 可调用；
2. wrap_agent(agent)：包裹 agent 的 handle_handoff；
3. install(obj, method_name) / uninstall()：monkeypatch 临时替换对象方法，
   配合上下文管理器可安全装卸。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable

from .faults import (
    FAULT_EXCEPTIONS,
    FaultMode,
    FaultSpec,
    FaultType,
)

logger = logging.getLogger(__name__)

_PERTURB_NOISE = "[prefix_perturb]"


class FaultInjector:
    """可插拔故障注入器。"""

    def __init__(self, config: Any = None):
        self._specs: list[FaultSpec] = []
        self._enabled = True
        self._stats: dict[str, int] = {}
        self._total_calls = 0
        self._patched: list[tuple[Any, str, Any]] = []
        self._rng = random.Random()
        if config is not None:
            self.load_config(config)

    # ── 配置 ────────────────────────────────────────────────
    def load_config(self, config: Any) -> FaultInjector:
        """加载故障配置。config 可为 dict / JSON 或 YAML 字符串 / 文件路径。"""
        data = _resolve_config(config)
        if isinstance(data, dict) and "faults" in data:
            faults = data["faults"]
        else:
            faults = data
        if not isinstance(faults, list):
            raise ValueError("故障配置必须是 {'faults': [...]} 或 [...] 列表")
        for item in faults:
            self.add_fault(FaultSpec.from_dict(item))
        return self

    def add_fault(self, spec: FaultSpec) -> FaultInjector:
        if not isinstance(spec, FaultSpec):
            raise TypeError(f"add_fault 需要 FaultSpec，收到 {type(spec).__name__}")
        spec.armed_at = time.monotonic()
        self._specs.append(spec)
        return self

    def clear(self) -> FaultInjector:
        self._specs.clear()
        self._stats.clear()
        self._total_calls = 0
        return self

    def enable(self) -> FaultInjector:
        self._enabled = True
        return self

    def disable(self) -> FaultInjector:
        self._enabled = False
        return self

    @property
    def enabled(self) -> bool:
        return self._enabled

    def faults(self) -> list[FaultSpec]:
        return list(self._specs)

    # ── 注入 ────────────────────────────────────────────────
    def inject(self, func: Callable) -> Callable:
        """包裹一个 async 可调用，返回带故障注入的 async 可调用。"""
        injector = self

        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            injector._total_calls += 1
            spec = injector._select_fault()
            if spec is not None:
                args, kwargs = await injector._apply_effect(spec, args, kwargs)
            return await func(*args, **kwargs)

        _wrapped.__wrapped__ = func  # 便于回溯/恢复
        return _wrapped

    def wrap_agent(self, agent: Any, in_place: bool = False) -> Any:
        """包裹 agent 的 handle_handoff，返回代理对象（或原地替换 handle_handoff）。"""
        wrapped_handle = self.inject(agent.handle_handoff)
        if in_place:
            agent.handle_handoff = wrapped_handle
            return agent

        class _Proxy:
            def __init__(self, handle: Callable, name: str):
                self.handle_handoff = handle
                self.name = name

        return _Proxy(wrapped_handle, getattr(agent, "name", "FaultInjectedAgent"))

    def install(self, obj: Any, method_name: str = "unified_call") -> FaultInjector:
        """monkeypatch obj.method_name，把调用先经过故障注入。可多次 install 不同对象。"""
        original = getattr(obj, method_name)
        if not callable(original):
            raise TypeError(f"{obj!r}.{method_name} 不可调用")
        wrapped = self.inject(original)
        setattr(obj, method_name, wrapped)
        self._patched.append((obj, method_name, original))
        return self

    def uninstall(self) -> FaultInjector:
        """恢复所有 install 过的对象方法。"""
        for obj, method_name, original in reversed(self._patched):
            setattr(obj, method_name, original)
        self._patched.clear()
        return self

    def __enter__(self) -> FaultInjector:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.uninstall()
        return False

    # ── 统计 ────────────────────────────────────────────────
    def stats(self) -> dict[str, int]:
        """各故障类型注入次数 + 总调用次数。"""
        out = dict(self._stats)
        out["total_calls"] = self._total_calls
        return out

    # ── 内部 ────────────────────────────────────────────────
    def _select_fault(self) -> FaultSpec | None:
        if not self._enabled:
            return None
        now = time.monotonic()
        for spec in self._specs:
            if not spec.enabled:
                continue
            if spec.duration and now - spec.armed_at > spec.duration:
                spec.enabled = False
                continue
            if spec.mode == FaultMode.ONCE:
                if spec.remaining > 0:
                    spec.remaining -= 1
                    return spec
            elif spec.mode == FaultMode.PERSISTENT:
                return spec
            elif spec.mode == FaultMode.RANDOM:
                if self._rng.random() < spec.probability:
                    return spec
        return None

    async def _apply_effect(self, spec: FaultSpec, args: tuple, kwargs: dict):
        self._stats[spec.type.value] = self._stats.get(spec.type.value, 0) + 1
        if spec.type == FaultType.MCP_SLOW:
            if spec.delay:
                await asyncio.sleep(spec.delay)
            return args, kwargs
        if spec.type == FaultType.PREFIX_PERTURB:
            return self._perturb_prefix(args, kwargs, spec)
        exc_cls = FAULT_EXCEPTIONS.get(spec.type)
        if exc_cls is None:
            return args, kwargs
        raise exc_cls(spec.message or f"injected {spec.type.value}")

    def _perturb_prefix(self, args: tuple, kwargs: dict, spec: FaultSpec):
        noise = spec.message or "noise"
        prefix = f"{_PERTURB_NOISE}{noise}: "
        new_args = tuple(self._perturb_dict(a, prefix) for a in args)
        new_kwargs = {k: self._perturb_dict(v, prefix) for k, v in kwargs.items()}
        return new_args, new_kwargs

    @staticmethod
    def _perturb_dict(value: Any, prefix: str) -> Any:
        # 只扰动 dict 中的 message 字段（编排器前缀扰动），核心路由字段不动
        if isinstance(value, dict) and isinstance(value.get("message"), str):
            value = dict(value)
            value["message"] = prefix + value["message"]
        return value


def _resolve_config(config: Any) -> Any:
    """把 dict / 文件路径 / 内联 JSON·YAML 字符串统一解析为配置对象。"""
    if isinstance(config, (dict, list)):
        return config
    if isinstance(config, Path):
        return _read_config_file(config)
    if isinstance(config, str):
        path = Path(config)
        if path.exists():
            return _read_config_file(path)
        return _parse_config_text(config.strip(), "inline")
    raise ValueError(f"不支持的配置类型: {type(config).__name__}")


def _read_config_file(path: Path) -> Any:
    if not path.exists():
        raise ValueError(f"配置文件不存在: {path}")
    return _parse_config_text(path.read_text(encoding="utf-8"), str(path))


def _parse_config_text(text: str, source: str) -> Any:
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml

        data = yaml.safe_load(text)
        return [] if data is None else data
    except ImportError as exc:
        raise ValueError(f"配置解析失败（非 JSON 且未安装 PyYAML）: {source}") from exc
    except Exception as exc:  # noqa: BLE001 - 统一转成配置错误
        raise ValueError(f"配置解析失败: {source}: {exc}") from exc
