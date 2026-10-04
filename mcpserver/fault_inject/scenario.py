"""预置故障场景（E-01）。

提供单个故障 / 组合故障 / 渐进恶化三类预置场景，配置为标准 JSON 格式，
由 FaultSpec.from_dict 解析。
"""

from __future__ import annotations

from .faults import FaultSpec
from .injector import FaultInjector

# 预置场景：每个场景是一组故障配置 dict
SCENARIOS: dict[str, list[dict]] = {
    "single_timeout": [{"type": "tool_timeout", "mode": "persistent"}],
    "single_rate_limit": [{"type": "mcp_rate_limit", "mode": "persistent"}],
    "single_disconnect": [{"type": "mcp_disconnect", "mode": "persistent"}],
    "single_error": [{"type": "tool_error", "mode": "persistent"}],
    "single_slow": [{"type": "mcp_slow", "mode": "persistent", "delay": 0.05}],
    "single_prefix_perturb": [{"type": "prefix_perturb", "mode": "persistent"}],
    "single_interrupt": [{"type": "orchestrator_interrupt", "mode": "persistent"}],
    # 组合故障：慢调用 + 限流 + 断连 + 工具错误，逐次触发
    "combined": [
        {"type": "mcp_slow", "mode": "once", "delay": 0.05},
        {"type": "mcp_rate_limit", "mode": "once"},
        {"type": "mcp_disconnect", "mode": "once"},
        {"type": "tool_error", "mode": "once"},
    ],
    # 渐进恶化：延迟递增 → 断连（一次）→ 断连（持续）
    "progressive": [
        {"type": "mcp_slow", "mode": "once", "delay": 0.01},
        {"type": "mcp_slow", "mode": "once", "delay": 0.03},
        {"type": "mcp_slow", "mode": "once", "delay": 0.06},
        {"type": "mcp_disconnect", "mode": "once"},
        {"type": "mcp_disconnect", "mode": "persistent"},
    ],
}


def build_scenario(name: str) -> list[FaultSpec]:
    """按名称构建场景的 FaultSpec 列表。"""
    if name not in SCENARIOS:
        raise ValueError(f"未知场景: {name!r}（合法值: {sorted(SCENARIOS)}）")
    return [FaultSpec.from_dict(item) for item in SCENARIOS[name]]


def apply_scenario(injector: FaultInjector, name: str) -> FaultInjector:
    """把场景加载进已有注入器。"""
    for spec in build_scenario(name):
        injector.add_fault(spec)
    return injector


def load_scenario(name: str) -> FaultInjector:
    """构建一个已加载指定场景的 FaultInjector。"""
    injector = FaultInjector()
    apply_scenario(injector, name)
    return injector
