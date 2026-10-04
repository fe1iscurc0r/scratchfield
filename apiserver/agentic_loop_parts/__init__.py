"""agentic_loop_parts —— 原 agentic_tool_loop.py 按域拆分后的聚合入口（卷190-A2）。

薄壳兼容：把各域全部公共名（**含下划线**）提到包级，使 `from apiserver.agentic_tool_loop import X` 的既有调用方继续可用。
"""

from . import (
    context,  # noqa: E402
    executor,  # noqa: E402
    executor_openclaw,  # noqa: E402
    executor_search,  # noqa: E402
    hooks,  # noqa: E402
    loop,  # noqa: E402
    markers,  # noqa: E402
    parser,  # noqa: E402
    planner,  # noqa: E402
)

_SUBMODULES = (markers, parser, planner, context, executor_openclaw, executor_search, executor, hooks, loop)
for _m in _SUBMODULES:
    for _name in dir(_m):
        if _name.startswith('__'):
            continue
        globals().setdefault(_name, getattr(_m, _name))

__all__ = sorted(
    n for m in _SUBMODULES for n in dir(m) if not n.startswith('__')
)

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
