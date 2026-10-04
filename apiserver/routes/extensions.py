"""extensions 路由 —— **薄壳**（卷190-A1）。

原 2932 行巨石已按域拆到同目录 ``extensions_parts/``：

| 模块 | 内容 |
|---|---|
| `extensions_parts/openclaw.py` | /openclaw/* + agent_browser 运行时 |
| `extensions_parts/mcp.py` | /mcp/* + mcporter 存储与装配 |
| `extensions_parts/skills.py` | /skills/* + 技能目录读写 |
| `extensions_parts/market.py` | /hub/*（安装）+ skillhub/mcpso/clawhub |
| `extensions_parts/upload.py` | /upload/* |
| `extensions_parts/travel.py` | /travel/* |
| `extensions_parts/memory.py` | /memory/* |
| `extensions_parts/search.py` | 搜索代理 |
| `extensions_parts/common.py` | 路径常量 / 子进程 / 遥测（无路由） |

**本文件保留同名 re-export，外部 import 路径与名字全部不变**（纯搬移，行为零变化）。
分域依据见 `docs/extensions-域边界勘察-2026-10-02.md`。
"""
from apiserver.routes.extensions_parts import *  # noqa: F401,F403
from apiserver.routes.extensions_parts import router  # noqa: F401

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
