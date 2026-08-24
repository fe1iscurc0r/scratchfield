"""最小 Ollama HTTP 客户端（靶子 A 的 VLM/LLM 推理后端）。

Ollama 未安装 / 未在运行 / 模型未拉取时，所有函数返回结构化错误而非抛异常，
保证 paper_miner 在环境不完整时也能被调用并给出可读诊断。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


class OllamaUnavailable(RuntimeError):
    """Ollama 未运行或不可达。"""


def _request(path: str, payload: dict[Any, Any], timeout: float = 120.0) -> dict[Any, Any]:
    """POST /api/<path>，走流式逐行解析，返回合并后的 JSON。"""
    url = DEFAULT_BASE.rstrip("/") + "/api/" + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
) -> str:
    """调用 /api/generate（文本生成）。返回文本内容。"""
    payload: dict[Any, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if format_json:
        payload["format"] = "json"
    data = _request("generate", payload, timeout=timeout)
    if data.get("error"):
        raise OllamaUnavailable(f"Ollama 返回错误: {data['error']}")
    return data.get("response", "")