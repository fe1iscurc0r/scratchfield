"""mcpserver.agentic_inventory —— agent 资产盘存与风险姿态（工单249）。

方法借自 **karmine05/agentic-detector**（MIT，Go 写的 osquery 扩展）的 `ai_tools` 表设计：
**多信号 + 置信度分级**（"Name matching alone never creates a row"）、**evidence 令牌**、
**静态风险姿态**、**sha256/launch_hash 指纹**（可跨时间 diff 发现签名被改）、
以及 **detection-only**（不执行、不连接）。

本模块把它落到**本仓的 agent 资产**上（而非主机扫描）：
- `mcp_agent` 行：`mcpserver/**/agent-manifest.json` 的静态契约信号 → 置信度 + 证据 + 风险
- `instruction_file` 行：`AGENTS.md` / `CLAUDE.md` 等（提示注入面）
- `registry_gap` 行：**注册表对账**（entryPoint 能否静态落地 / 声明与派发表是否一致）

⚠️ **与 244g 守卫的边界**：那个是 **CI 闸门**（静态、无依赖、只守 manifest 可解析）；
本模块是**可反复跑的盘存**（任意目录、带置信度/风险/指纹、可跨时间 diff）。
两者不重复：一个盯"别坏"，一个答"现在是什么样、比上次变了什么"。

⚠️ **只读**：不 import 被盘对象、不执行任何二进制、不建立任何连接、**不报密钥的值**。
"""

from __future__ import annotations

# ⚠️ 函数**不叫** `inventory`：那会与同名子模块撞名 —— `from . import inventory as inv`
#    会拿到被 `__init__` 绑上去的函数而不是模块（实测踩过，报 'function' object has no
#    attribute 'inventory'）。子模块名与导出名必须错开。
from .inventory import (
    COLUMNS,
    AssetRow,
    build_inventory,
    diff_snapshots,
    reconcile,
    scan_agents,
    scan_instructions,
    snapshot,
)
from .posture import (
    MIN_EMITTED,
    QUALITY_TOKENS,
    RISK_TOKENS,
    SIGNAL_WEIGHTS,
    Posture,
    scan_text_risks,
    score,
)

__all__ = [
    "COLUMNS",
    "MIN_EMITTED",
    "QUALITY_TOKENS",
    "RISK_TOKENS",
    "SIGNAL_WEIGHTS",
    "AgenticInventoryBridge",
    "AssetRow",
    "Posture",
    "build_inventory",
    "diff_snapshots",
    "reconcile",
    "scan_agents",
    "scan_instructions",
    "scan_text_risks",
    "score",
    "snapshot",
]


def __getattr__(name: str):
    """`AgenticInventoryBridge` 惰性暴露（`server` 只在真取用时导入）。"""
    if name == "AgenticInventoryBridge":
        from .server import AgenticInventoryBridge

        return AgenticInventoryBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
