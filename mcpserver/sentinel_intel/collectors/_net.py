"""collectors/_net.py — 采集器公共网络层（纯 stdlib）。

三个原语都收 timeout 参数、可被 unittest.mock.patch 替换（离线可测）：
- tcp_query：WHOIS 协议文本查询（socket TCP:43，RFC 3912）
- udp_query：DNS 二进制查询（socket UDP:53）
- http_get ：HTTPS JSON 抓取（urllib）

分工照 context7.py：本层只做 IO 原样抛异常，由上层采集器统一
catch 降级为 ok=False —— 网络细节不泄漏到业务判断里。
"""
from __future__ import annotations

import socket
import urllib.request


def tcp_query(host: str, port: int, payload: str, timeout: float = 8.0) -> str:
    """RFC 3912 WHOIS 文本查询：发送请求 → 读至对端关闭。

    对端可能不关闭连接（部分 whois 服务器），timeout 兜底。
    """
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(payload.encode("latin-1"))
        sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("latin-1", errors="replace")


def udp_query(host: str, port: int, payload: bytes, timeout: float = 8.0) -> bytes:
    """DNS 二进制查询：发请求 → 收首个响应包（超时由 socket 兜底）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (host, port))
        data, _ = sock.recvfrom(65535)
    return data


def http_get(url: str, timeout: float = 8.0, max_bytes: int = 1_000_000) -> str:
    """HTTPS GET；收满 max_bytes+1 即截断（防大响应拖垮进程）。"""
    req = urllib.request.Request(
        url, headers={"User-Agent": "sentinel-intel-collector/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(max_bytes + 1).decode("utf-8", errors="replace")
