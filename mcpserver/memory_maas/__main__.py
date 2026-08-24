"""记忆 MaaS sidecar 启动入口：python -m mcpserver.memory_maas [port]。

端口：MEMORY_MAAS_PORT（默认 48919，接 NEKO 段位 48911-48918 之后）。
仅绑 127.0.0.1（本机 sidecar，与 memory_server 48912 同安全水位）。
"""
from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    port = int(os.environ.get("MEMORY_MAAS_PORT", "48919"))
    uvicorn.run("mcpserver.memory_maas.app:app",
                host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
