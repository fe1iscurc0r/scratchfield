"""Prompt→RF 工程工作流 · SDR 工具集（工单242 · 漏斗 2.0 轻量猎手第 2 单）。

把「自然语言 prompt → RF 仿真脚本 → 受限执行 → 结果解释 → 下一轮建议」做成一条
可跑的 MCP 工作流。模块划分：

- :mod:`lora_phy`         LoRa 物理层数值（**纯标准库**；脚本与解释器的唯一真值源）
- :mod:`prompt_to_script` 目标/prompt → 可跑仿真脚本（LLM 优先，规则兜底）
- :mod:`sim_runner`       受限子进程执行 + 日志/指标收集 + sandbox 目录收敛
- :mod:`explainer`        结果解释 + 下一步建议（LLM 优先，规则兜底）
- :mod:`server`           MCP 入口（``RfWorkflowBridge``，三接口 + 状态查询）

许可与依赖边界：**不引入任何第三方 RF 库作为硬依赖**；`numpy` 仅在
``rf_lib="numpy"`` 时由**沙箱脚本自己**尝试导入，缺失即降级并在产物里标注，不静默。
"""

from .server import RfWorkflowBridge

__all__ = ["RfWorkflowBridge"]
