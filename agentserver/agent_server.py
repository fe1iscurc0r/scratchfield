"""agentserver/agent_server.py —— 薄入口（工单204 任务一拆分后）。

原 3096 行实现已按职责拆到 `agent_server_parts/`；本文件保留对外契约
（`app` / `Modules`）并导入子模块（导入即注册路由）。
"""
from __future__ import annotations

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
from .agent_server_parts.common import Modules  # noqa: F401
from .agent_server_parts.lifecycle import app  # noqa: F401

__all__ = ["app", "Modules"]


if __name__ == "__main__":
    import uvicorn

    from agentserver.config import AGENT_SERVER_PORT
    from system.net_boundary import enforce_startup_policy

    # 安全：默认仅 loopback；跨机必须 NEKO_BIND_HOST + NEKO_ALLOW_REMOTE=1 +
    # NEKO_AUTH_TOKEN 三者齐备，否则 enforce_startup_policy 直接 78 退出。
    # 本服务的路由分散在 8 个 parts 模块且无完整鉴权体系，靠"记得绑 127.0.0.1"
    # 已经被证明不可靠（根启动器曾把它覆盖成 0.0.0.0）。
    bind_host = enforce_startup_policy("agentserver 独立入口")

    uvicorn.run(app, host=bind_host, port=AGENT_SERVER_PORT, access_log=False)
