"""故障注入 + 鲁棒性回归框架（ECHO 线 E-01/E-02）。

子模块：
- faults: 故障类型/模式枚举、FaultSpec 配置模型、故障异常
- injector: FaultInjector 可插拔故障注入器
- scenario: 预置场景（单个/组合/渐进恶化）
- robustness: RobustCaller 重试/退避/重连/降级 + MockMCPAgent（E-02）
"""

from .faults import (
    DisconnectError,
    FaultInjectionError,
    FaultMode,
    FaultSpec,
    FaultType,
    OrchestratorInterruptError,
    RateLimitError,
    ToolError,
    ToolTimeoutError,
)
from .injector import FaultInjector
from .scenario import SCENARIOS, apply_scenario, build_scenario, load_scenario

__all__ = [
    "FaultInjector",
    "FaultMode",
    "FaultSpec",
    "FaultType",
    "DisconnectError",
    "FaultInjectionError",
    "OrchestratorInterruptError",
    "RateLimitError",
    "ToolError",
    "ToolTimeoutError",
    "SCENARIOS",
    "apply_scenario",
    "build_scenario",
    "load_scenario",
]
