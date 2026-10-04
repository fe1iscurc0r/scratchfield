"""litellm 懒加载代理（卷191-B2）。

背景：`litellm` 首次 import 约 **8.9 秒**（占 apiserver 启动 11.8s 的 75%），
但它只在**真正发起 LLM 调用**时才需要。模块顶层直接 `import litellm`
会让整个 apiserver 冷启动被它拖住。

用法（与原 `import litellm` + `from litellm import acompletion` 等价）：
    from apiserver.litellm_lazy import acompletion, litellm
    litellm.api_key = "..."                     # 配置写入延迟到真模块加载后回放
    except litellm.AuthenticationError: ...     # 异常类型同样惰性解析

`litellm` 是惰性代理对象：访问任何属性（含异常类型、配置字段）才触发
真实 import，之后缓存。`acompletion` 是 async 包装函数，首次调用时解析实现。

⚠️ 本模块**刻意不定义模块级 `__getattr__`**：那会让 `from X import litellm`
在导入期就触发代理求值，懒加载失效（实测踩过）。
"""

from __future__ import annotations

import threading
from typing import Any

_litellm_module: Any = None
_lock = threading.Lock()


def get_litellm():
    """返回真实的 litellm 模块（首次调用时 import，之后缓存）。

    加载后会回放此前通过代理写入的配置（api_key / api_base 等），
    避免"先赋配置、后加载"的顺序导致配置丢失。
    """
    global _litellm_module
    if _litellm_module is None:
        with _lock:
            if _litellm_module is None:
                import litellm as _m  # noqa: PLC0415  延迟导入是本模块存在的唯一理由
                _litellm_module = _m
                # 回放代理上暂存的配置
                _proxy = globals().get("litellm")
                _pending = getattr(_proxy, "_pending", None) if _proxy is not None else None
                if _pending:
                    for k, v in _pending.items():
                        setattr(_m, k, v)
    return _litellm_module


class _LiteLLMProxy:
    """惰性代理：属性访问 / 赋值 / 调用全部转发到真模块。"""

    def __init__(self) -> None:
        object.__setattr__(self, "_pending", {})

    def __getattr__(self, name: str) -> Any:
        pending = object.__getattribute__(self, "_pending")
        if name in pending:
            return pending[name]
        return getattr(get_litellm(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        pending = object.__getattribute__(self, "_pending")
        pending[name] = value
        mod = _litellm_module
        if mod is not None:
            setattr(mod, name, value)

    def __delattr__(self, name: str) -> None:
        pending = object.__getattribute__(self, "_pending")
        pending.pop(name, None)
        mod = _litellm_module
        if mod is not None:
            delattr(mod, name)


# 代理实例：可用于 `litellm.api_key = ...` / `except litellm.AuthenticationError`
litellm = _LiteLLMProxy()

__all__ = ["litellm", "acompletion", "get_litellm"]


async def acompletion(*args: Any, **kwargs: Any) -> Any:
    """转发 litellm.acompletion —— 首次调用时导入真实实现。"""
    real = get_litellm().acompletion
    return await real(*args, **kwargs)
