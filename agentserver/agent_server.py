"""agentserver/agent_server.py —— 薄入口（工单204 任务一拆分后）。

原 3096 行实现已按职责拆到 `agent_server_parts/`；本文件保留对外契约
（`app` / `Modules`）并导入子模块（导入即注册路由）。
"""
from __future__ import annotations

from .agent_server_parts.common import Modules  # noqa: F401
from .agent_server_parts.lifecycle import app  # noqa: F401
from .agent_server_parts import (  # noqa: F401  导入即注册路由
    agents,
    dogtag,
    health,
    heartbeat,
    openclaw,
    search,
    travel,
    vision,
)

__all__ = ["app", "Modules"]


if __name__ == "__main__":
    import uvicorn

    from agentserver.config import AGENT_SERVER_PORT

    # 安全：仅绑定 loopback，禁止局域网直连（本服务无完整鉴权体系）
    uvicorn.run(app, host="127.0.0.1", port=AGENT_SERVER_PORT, access_log=False)
