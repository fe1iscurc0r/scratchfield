"""最小 Ollama HTTP 客户端（靶子 A 的 VLM/LLM 推理后端）。

Ollama 未安装 / 未在运行 / 模型未拉取时，所有函数返回结构化错误而非抛异常，
保证 paper_miner 在环境不完整时也能被调用并给出可读诊断。
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Ollama 是本机推理后端，端点固定为环回字面量：不做环境变量可配，
# 避免「动态 URL 直接进入服务端请求」的 SSRF 面（安全扫描规则；本文件只服务本机 Ollama）。
DEFAULT_BASE = "http://127.0.0.1:11434"

_ALLOWED_OLLAMA_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# 本机调用绝不走系统代理：Windows 上 urllib/requests 会读注册表代理设置，
# 系统代理开启时（如 FlClash 的 127.0.0.1:7890）连 127.0.0.1 都会被送去代理，
# 实测表现为 /api/tags 返回 405 Method Not Allowed（代理拒绝本地路径）。
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _base_url() -> str:
    """返回并复核 Ollama 端点：必须是 http + 环回主机（纵深防御）。"""
    parsed = urllib.parse.urlparse(DEFAULT_BASE)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in _ALLOWED_OLLAMA_HOSTS:
        raise OllamaUnavailable(
            f"Ollama 端点必须是本机环回地址（http/https + 127.0.0.1/localhost/::1），收到：{parsed.scheme}://{host}"
        )
    return DEFAULT_BASE


class OllamaUnavailable(RuntimeError):
    """Ollama 未运行或不可达。"""


def _request(path: str, payload: dict[Any, Any], timeout: float = 120.0) -> dict[Any, Any]:
    """请求 /api/<path>，走流式逐行解析，返回合并后的 JSON。

    payload 为空 → GET，否则 POST。Ollama 的 `/api/tags`（模型列表 / 健康检查）只接受 GET，
    早先无条件 POST 会拿到 405 Method Not Allowed（实测 curl GET 同地址 200，而 healthcheck
    恒报 405 → paper_miner 一直被判定 Ollama 不可用）。
    """
    url = DEFAULT_BASE.rstrip("/") + "/api/" + path
    if payload:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
    else:
        req = urllib.request.Request(url)
    try:
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise OllamaUnavailable(f"Ollama 请求失败（{url}）: {e}") from e
    if not raw.strip():
        return {}
    # 兼容流式 NDJSON 与单对象：取最后一行完整 JSON
    last: dict[Any, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def healthcheck() -> dict[str, Any]:
    """探测 Ollama 是否可达 + 列出已拉模型。"""
    try:
        data = _request("tags", {}, timeout=10.0)
    except OllamaUnavailable as e:
        return {"ok": False, "error": str(e)}
    models = [m.get("name") for m in data.get("models", [])]
    return {"ok": True, "models": models}


def chat(
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    images: list[str] | None = None,
    format_json: bool = False,
    temperature: float = 0.1,
    timeout: float = 300.0,
) -> str:
    """调用 /api/chat（支持多模态 images=base64 列表）。返回文本内容。"""
    payload: dict[Any, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    if images:
        payload["images"] = images
    if format_json:
        payload["format"] = "json"
    data = _request("chat", payload, timeout=timeout)
    if data.get("error"):
        raise OllamaUnavailable(f"Ollama 返回错误: {data['error']}")
    return data.get("message", {}).get("content", "")


def generate(
    model: str,
    prompt: str,
    *,
    format_json: bool = False,
    temperature: float = 0.1,
    timeout: float = 300.0,
    num_ctx: int = 32768,
) -> str:
    """调用 /api/generate（文本生成）。返回文本内容。

    num_ctx 显式设为 32768：论文正文按 60000 字符截断后约 15k+ token，超过 Ollama 的
    默认上下文（2048/4096）时会被静默截断并可能返回空 response（实测：小 prompt 正常，
    整篇论文 prompt 只花 0.6s 且 response 为空 → 提取出 0 个参数）。
    """
    payload: dict[Any, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    if format_json:
        payload["format"] = "json"
    data = _request("generate", payload, timeout=timeout)
    if data.get("error"):
        raise OllamaUnavailable(f"Ollama 返回错误: {data['error']}")
    return data.get("response", "")