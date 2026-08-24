"""TTS-API MCP 封装 · babutree/TTS-API (MIT)

把自托管 TTS 网关（babutree/TTS-API）封装为陆墨 MCP 工具体系的一个 agent。
走它的 OpenAI 兼容端点 POST /v1/audio/speech，双引擎：kokoro（本地）/ edge（微软云）。

许可：MIT（主仓 AGPL v3 允许直接吞 MIT 项目）。
边界：只做 HTTP 客户端封装，不内置模型权重；TTS-API 服务独立部署（默认 localhost:8880）。
不碰主流程：独立目录 mcpserver/tts_api/，仅通过 MCP 调度接入。

参考接口（来自上游 API.md）：
  POST /v1/audio/speech  {input, model(engine), voice, speed, response_format} → 二进制音频
  GET  /v1/audio/voices  → {object:"list", data:[{id,name,gender,locale,engine}]}
  GET  /                 → {status, ready, max_text_length}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from system.config import logger
except ImportError:  # 独立 pytest 时降级到标准 logging
    logger = logging.getLogger("tts_api")

# response_format → 文件扩展名
_EXT = {"mp3": "mp3", "opus": "opus", "aac": "aac", "flac": "flac", "wav": "wav", "pcm": "pcm"}


class TTSApiAgent:
    """TTS 语音合成 agent（封装 TTS-API 网关的 OpenAI 兼容接口）。"""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, output_dir: str | None = None):
        self.name = "tts_api"
        self.display_name = "TTS 语音合成"
        self.version = "1.0.0"
        self.description = "文本转语音：调用自托管 TTS-API 网关（kokoro/edge 双引擎），合成语音并落盘为音频文件"
        self.base_url = (base_url or os.environ.get("TTS_API_BASE_URL", "http://localhost:8880")).rstrip("/")
        self.api_key = api_key or os.environ.get("TTS_API_KEY", "")
        self.output_dir = output_dir or os.environ.get("TTS_OUTPUT_DIR", "/tmp/tts_api")
        self.tools = {
            "tts_speak": self._tts_speak,
            "tts_list_voices": self._tts_list_voices,
            "tts_health": self._tts_health,
        }
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"[MCP] {self.display_name} 初始化完成，共 {len(self.tools)} 个工具（base_url={self.base_url}）")

    # ---- HTTP 底层 ----

    def _get(self, path: str, timeout: int = 15) -> tuple[bytes, dict]:
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), dict(resp.headers)

    def _post_json(self, path: str, payload: dict, timeout: int = 60) -> tuple[bytes, dict]:
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), dict(resp.headers)

    # ---- 工具实现 ----

    def _tts_speak(self, params: dict) -> dict:
        text = str(params.get("text") or "").strip()
        if not text:
            return {"success": False, "error": "text 不能为空"}
        engine = params.get("engine") or "edge"
        voice = params.get("voice") or None
        speed = float(params.get("speed") or 1.0)
        fmt = params.get("response_format") or "mp3"
        if fmt not in _EXT:
            return {"success": False, "error": f"不支持的 response_format: {fmt}（可选 {sorted(_EXT)}）"}

        payload: dict[str, Any] = {
            "input": text,
            "model": engine,
            "speed": speed,
            "response_format": fmt,
        }
        if voice:
            payload["voice"] = voice

        try:
            body, headers = self._post_json("/v1/audio/speech", payload)
            if not body:
                return {"success": False, "error": "TTS-API 返回空音频"}
            ext = _EXT[fmt]
            path = os.path.join(self.output_dir, f"tts_{int(time.time() * 1000)}.{ext}")
            with open(path, "wb") as f:
                f.write(body)
            return {
                "success": True,
                "path": path,
                "size_bytes": len(body),
                "engine": engine,
                "voice": voice,
                "content_type": headers.get("Content-Type", ""),
            }
        except urllib.error.HTTPError as e:
            return {"success": False, "error": f"TTS-API HTTP {e.code}", "detail": _safe_body(e)}
        except Exception as e:
            return {"success": False, "error": f"合成失败: {e}"}

    def _tts_list_voices(self, params: dict) -> dict:
        try:
            body, _ = self._get("/v1/audio/voices")
            data = json.loads(body.decode("utf-8"))
            voices = data.get("data", [])
            return {"success": True, "count": len(voices), "voices": voices}
        except Exception as e:
            return {"success": False, "error": f"获取音色列表失败: {e}"}

    def _tts_health(self, params: dict) -> dict:
        try:
            body, _ = self._get("/")
            data = json.loads(body.decode("utf-8"))
            return {"success": True, **data}
        except Exception as e:
            return {"success": False, "error": f"健康检查失败: {e}"}

    # ---- MCP 调度接口（对齐 material_science 契约）----

    def invoke(self, command: str, params: dict | None = None) -> dict:
        if command not in self.tools:
            return {"success": False, "error": f"未知命令: {command}", "available_commands": list(self.tools.keys())}
        try:
            return self.tools[command](params or {})
        except Exception as e:
            logger.error(f"工具执行失败 [{command}]: {e}")
            return {"success": False, "error": str(e)}

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        try:
            tool_name = str(task.get("tool_name") or "").strip()
            if not tool_name:
                return json.dumps({"status": "error", "message": "缺少 tool_name 参数", "data": {}}, ensure_ascii=False)
            params = {k: v for k, v in task.items() if k not in ("service_name", "tool_name", "agentType")}
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self.invoke, tool_name, params)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TTSApi] handle_handoff 异常: {e}")
            return json.dumps({"status": "error", "message": f"调用失败: {e}", "data": {}}, ensure_ascii=False)


def _safe_body(e: urllib.error.HTTPError) -> str:
    try:
        return e.read().decode("utf-8", errors="replace")[:500]
    except Exception:
        return ""
