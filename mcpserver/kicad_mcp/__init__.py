"""mcpserver.kicad_mcp —— KiCAD PCB/原理图 离线读取核（工单245）。

本模块把上游 `mixelpixx/KiCAD-MCP-Server`（MIT，2728★）那条「AI 辅助 PCB 设计」的路
在**本仓可验证的前提下**接进来：不依赖 KiCAD 安装、不依赖第三方包，
只用纯 Python 把 KiCAD 的文本文件读成结构化视图，供 agent 线做
**布局布线进度判断 / 原理图-PCB 对账 / 嘉立创制造前预检**。

模块边界（刻意）
----------------
- **读**而不是写：写原理图/PCB 需要 UUID 与实例路径的完整语义，属上游工具链的强项，
  本 PoC 不做（见 `README.md` §边界）。
- **零第三方依赖**：与 `mcpserver/toolknit_mcp` 同纪律；上游用 `sexpdata`，本模块自研
  状态机解析（`sexpr.py`），因而能在任何解释器上跑。
- **不装作能做的事**：Gerber/DRC 真跑需要 KiCAD，本模块对这些只给**明确不可用**的回答。

对外入口
--------
:class:`~mcpserver.kicad_mcp.server.KicadBridge` —— 实现 MCP agent 的
``handle_handoff`` 契约，供 `mcpserver/mcp_registry` 注册（与 241/242/243/244 同构）。
"""

from __future__ import annotations

from .board import Board, Footprint, Pad, Segment, Via
from .schematic import PlacedSymbol, Schematic
from .sexpr import SExpr, SExprError, parse_all, parse_one

__all__ = [
    "Board",
    "Footprint",
    "KicadBridge",
    "Pad",
    "PlacedSymbol",
    "SExpr",
    "SExprError",
    "Schematic",
    "Segment",
    "Via",
    "parse_all",
    "parse_one",
]


def __getattr__(name: str):
    """`KicadBridge` 惰性暴露 —— 只在真取用时才导入 `server`（它较重且带注册副作用）。

    刻意**不做模块级 `from .server import KicadBridge`**：那会让 `import mcpserver.kicad_mcp`
    也把 server 拉起来。⚠️ 不定义模块级 `__getattr__` 的反面教材见
    `apiserver/litellm_lazy.py` 的注释（那里是"不能定义"，这里是"可以用"——
    区别在于本模块**不**被 `from X import *` 的语义依赖）。
    """
    if name == "KicadBridge":
        from .server import KicadBridge

        return KicadBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
