"""健康检查：GET 127.0.0.1:{GATEWAY_PORT}/health → {status, adapters:{qqbot: connected|down}}。

纯 stdlib http.server（线程模式），零额外依赖，供 systemd 探活。
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger("lumo_gateway.health")

_JSON_HEADERS = ("Content-Type", "application/json; charset=utf-8")


class _HealthHandler(BaseHTTPRequestHandler):
    """每请求取类属性 adapters 的快照（线程安全：只读 adapter.connected）。"""

    adapters: dict[str, Any] = {}
    server_version = "LumoGateway/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        payload = {
            "status": "ok",
            "adapters": {
                name: "connected" if _is_connected(adapter) else "down"
                for name, adapter in self.adapters.items()
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header(*_JSON_HEADERS)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: N802
        logger.debug("health %s", fmt % args)


def _is_connected(adapter: Any) -> bool:
    return bool(getattr(adapter, "connected", False))


class HealthServer:
    """127.0.0.1 绑定的健康检查服务（线程模式）。"""

    def __init__(
        self,
        host: str,
        port: int,
        adapters: dict[str, Any] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.adapters = adapters or {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        """启动服务，返回实际监听端口（port=0 时为系统分配）。"""
        handler = type("HealthHandler", (_HealthHandler,), {"adapters": self.adapters})
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="lumo-gateway-health",
            daemon=True,
        )
        self._thread.start()
        logger.info("[health] 监听 http://%s:%d/health", self.host, self.port)
        return self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
