"""academic 16 项目调用桥（SPEC-02 Phase 1）。

- registry: 16 项目元数据（许可/安装/文档）
- bridge: 5 项本地调用包装（thermo/coolprop/chemformula/affine_gaps/pynite）
- academic_tools: MCP 工具注册入口

接口文档在仓库根目录 academic/<项目>/MODEL_INTERFACE.md。
"""

from .academic_tools import register_academic_tools
from .bridge import academic_call
from .registry import PROJECTS, doc_path, is_installed

__all__ = [
    "register_academic_tools",
    "academic_call",
    "PROJECTS",
    "doc_path",
    "is_installed",
]
