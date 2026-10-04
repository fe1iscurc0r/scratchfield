"""故障注入 MCP 桥 — FaultInjectBridge（agent-manifest.json entryPoint）。

U-02（UNIFORM 总装线）：把 ECHO 线交付的故障注入器挂成 MCP 工具。
本桥只封装 injector/faults/scenario/robustness 现有接口，不重写任何注入逻辑。

工具（4 个）：
- inject(specs|scenario, calls)：按配置/预置场景注入故障并调用 mock agent，统计触发情况
- run_robustness(trials)：全故障类型鲁棒性回归（重试/退避/重连/降级指标）
- list_scenarios()：预置场景与故障类型枚举
- check(spec)：校验单条故障配置（FaultSpec.from_dict 同源）
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcpserver.fault_inject.faults import (
    FaultInjectionError,
    FaultSpec,
    FaultType,
)
from mcpserver.fault_inject.injector import FaultInjector
from mcpserver.fault_inject.robustness import MockMCPAgent, run_robustness_suite
from mcpserver.fault_inject.scenario import SCENARIOS, build_scenario

logger = logging.getLogger(__name__)

# 调度层注入的路由键（分发前必须全部剥离，避免污染具名参数）
_ROUTING_KEYS = frozenset({
    "service_name", "tool_name", "agentType", "_tool_call_id",
    "message", "callback_url", "params", "arguments",
})


def _build_injector(specs: list[dict] | None, scenario: str | None) -> FaultInjector:
    """按 specs / 预置场景名构建注入器（二者至少其一）。"""
    injector = FaultInjector()
    if scenario:
        for spec in build_scenario(scenario):
            injector.add_fault(spec)
    for item in specs or []:
        injector.add_fault(FaultSpec.from_dict(item))
    return injector


class FaultInjectBridge:
    """故障注入 MCP 服务实例（无状态：每次调用新建注入器）。"""

    # ---- 工具实现（封装，不重写）----

    def inject(self, specs: list[dict] | None = None,
               scenario: str | None = None,
               calls: int = 1) -> dict[str, Any]:
        """注入故障并调用 mock agent：统计成功/被注入异常次数与类型。

        同步版（测试/CLI 用）；事件循环内请走 handle_handoff。
        """
        if _in_event_loop():
            raise RuntimeError(
                "inject 同步版不可在事件循环内调用，请走 handle_handoff")
        try:
            calls = max(1, min(int(calls), 100))  # 硬上限，防调度层滥用
        except (TypeError, ValueError):
            calls = 1
        injector = _build_injector(specs, scenario)
        if not injector.faults():
            return {"status": "error",
                    "error": "未提供任何故障配置（需 specs 或 scenario）"}
        agent = MockMCPAgent(service_name="fault_inject_probe")
        wrapped = injector.inject(agent.handle_handoff)
        ok = 0
        injected: dict[str, int] = {}

        async def _run() -> None:
            nonlocal ok
            for _ in range(calls):
                try:
                    await wrapped({"tool_name": "echo", "message": "probe"})
                    ok += 1
                except FaultInjectionError as e:
                    injected[e.fault_type] = injected.get(e.fault_type, 0) + 1

        asyncio.run(_run())
        return {"status": "ok", "calls": calls, "success": ok,
                "injected": injected, "stats": injector.stats()}

    async def run_robustness(self, trials: int = 20) -> dict[str, Any]:
        """全故障类型鲁棒性回归（封装 run_robustness_suite）。"""
        try:
            trials = max(1, min(int(trials), 100))
        except (TypeError, ValueError):
            trials = 20
        rows = await run_robustness_suite(trials=trials)
        return {"status": "ok", "trials": trials, "rows": rows}

    def list_scenarios(self) -> dict[str, Any]:
        """预置场景与故障类型枚举（与代码同源，不重复维护清单）。"""
        return {"status": "ok",
                "scenarios": sorted(SCENARIOS),
                "fault_types": [t.value for t in FaultType]}

    def check(self, spec: dict | None = None) -> dict[str, Any]:
        """校验单条故障配置（FaultSpec.from_dict 同源，非法即报错）。"""
        if not isinstance(spec, dict):
            return {"status": "error", "error": "spec 必须是 JSON 对象"}
        parsed = FaultSpec.from_dict(spec)  # 非法配置抛 ValueError（由分发层捕获）
        return {"status": "ok",
                "spec": {"type": parsed.type.value, "mode": parsed.mode.value,
                         "probability": parsed.probability, "delay": parsed.delay,
                         "duration": parsed.duration, "count": parsed.count}}

    # ---- MCP 分发 ----

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """MCP 标准入口：按 tool_name 分发，剥离全部调度层路由键。"""
        tool_name = str(tool_call.get("tool_name") or "").strip()
        inner = tool_call.get("params") or tool_call.get("arguments") or {}
        if isinstance(inner, dict):
            params = {k: v for k, v in inner.items() if k not in _ROUTING_KEYS}
        else:
            params = {}
        for k, v in tool_call.items():
            if k not in _ROUTING_KEYS and k not in params:
                params[k] = v
        try:
            if tool_name == "inject":
                result = await self._inject_async(
                    params.get("specs"), params.get("scenario"),
                    params.get("calls", 1))
            elif tool_name == "run_robustness":
                result = await self.run_robustness(params.get("trials", 20))
            elif tool_name == "list_scenarios":
                result = self.list_scenarios()
            elif tool_name == "check":
                result = self.check(params.get("spec"))
            else:
                raise ValueError(
                    f"fault_inject 不支持的工具: {tool_name!r}（可用: "
                    "inject/run_robustness/list_scenarios/check）")
        except Exception as e:
            logger.exception("[fault_inject] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "fault_inject",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        return json.dumps({"service": "fault_inject", "tool": tool_name,
                           **result}, ensure_ascii=False)

    async def _inject_async(self, specs: Any, scenario: Any,
                            calls: Any) -> dict[str, Any]:
        """inject 的异步实现（事件循环内安全，供分发层调用）。"""
        try:
            calls = max(1, min(int(calls), 100))
        except (TypeError, ValueError):
            calls = 1
        injector = _build_injector(specs if isinstance(specs, list) else None,
                                   scenario if isinstance(scenario, str) else None)
        if not injector.faults():
            return {"status": "error",
                    "error": "未提供任何故障配置（需 specs 或 scenario）"}
        agent = MockMCPAgent(service_name="fault_inject_probe")
        wrapped = injector.inject(agent.handle_handoff)
        ok = 0
        injected: dict[str, int] = {}
        for _ in range(calls):
            try:
                await wrapped({"tool_name": "echo", "message": "probe"})
                ok += 1
            except FaultInjectionError as e:
                injected[e.fault_type] = injected.get(e.fault_type, 0) + 1
        return {"status": "ok", "calls": calls, "success": ok,
                "injected": injected, "stats": injector.stats()}


def _in_event_loop() -> bool:
    """当前线程是否已运行事件循环（asyncio.run 会冲突，返回 True）。"""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


__all__ = ["FaultInjectBridge"]
