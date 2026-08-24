# voice_mcp_minimax.py — garan0613/voice-mcp 的 MCP 桥接 agent
#
# 耦合目标：https://github.com/garan0613/voice-mcp (MIT)
# 上游形态：TypeScript + Cloudflare Workers 的 SSE MCP server（/mcp 端点），
#           核心能力 = 调用 MiniMax t2a_v2 API 做语音克隆合成（speak 工具）。
# 接入评估：上游是 TS/Workers 形态，无法直接注册进 scratchpad 的 Python
#           MCP 注册表（Format A: module + class + handle_handoff）。故「改造
#           接入」：用 Python 复刻其核心合成逻辑（同一 MiniMax API 契约），
#           不部署 Worker，工具语义与上游 speak 对齐。
#
# 契约（对齐 mcp_registry Format A）：
#   class VoiceMCPMinimaxAgent 实现 async handle_handoff(task) -> str
#
# 运行态降级（对齐 omnilimb_face 降级契约）：
#   缺 MINIMAX_API_KEY / MINIMAX_GROUP_ID → 返回 {"status":"error",
#   "degraded":true,...}，不炸注册流程。
#
# 仅用标准库（urllib + base64 + binascii），不新增第三方依赖。

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(
    os.environ.get("MINIMAX_CACHE_DIR", str(Path(__file__).resolve().parent / ".cache"))
)
MINIMAX_T2A_URL = "https://api.minimaxi.com/v1/t2a_v2"
_SYNTH_TIMEOUT_S = 60


def _env(name: str, default: str = "") -> str:
    """调用时读取环境变量（避免模块导入时固化，便于测试注入/运行时改配）。"""
    return os.environ.get(name, default)


def _credentials() -> Dict[str, str]:
    return {
        "api_key": _env("MINIMAX_API_KEY"),
        "group_id": _env("MINIMAX_GROUP_ID"),
        "voice_id": _env("MINIMAX_VOICE_ID"),
    }


def _hex_to_base64(hex_str: str) -> str:
    """上游 data.audio 是 hex 字符串 → 解码为字节 → base64。"""
    raw = binascii.unhexlify(hex_str)
    return base64.b64encode(raw).decode("ascii")


def _call_t2a(text: str, voice_id: str) -> Optional[Dict[str, Any]]:
    """调用 MiniMax t2a_v2（对齐上游 src/index.ts:332-384 的请求契约）。

    返回解析后的 JSON；任何失败返回 None（供调用方降级）。
    """
    creds = _credentials()
    if not (creds["api_key"] and creds["group_id"]):
        return None
    url = f"{MINIMAX_T2A_URL}?GroupId={urllib.parse.quote(creds['group_id'])}"
    payload = {
        "model": "speech-2.8-hd",
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "format": "mp3"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {creds['api_key']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_SYNTH_TIMEOUT_S) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 降级契约
        logger.warning("MiniMax t2a 调用失败: %s", exc)
        return None


class VoiceMCPMinimaxAgent:
    """garan0613/voice-mcp 的 MCP agent（Python 改造接入）。

    提供两个工具：
    - ``voice_speak`` — MiniMax 语音克隆合成，落盘 mp3 + 返回 base64 + 元数据
    - ``voice_status`` — 配置健康检查（API Key / GroupId / Voice ID 是否就绪）
    """

    name = "voice-mcp (MiniMax) Agent"

    def __init__(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------
    def _do_speak(self, text: str, voice_id: str) -> str:
        if not text.strip():
            return json.dumps(
                {"status": "error", "message": "text 不能为空", "data": {}},
                ensure_ascii=False,
            )
        creds = _credentials()
        if not (creds["api_key"] and creds["group_id"]):
            return json.dumps(
                {
                    "status": "error",
                    "degraded": True,
                    "message": "缺少 MINIMAX_API_KEY 或 MINIMAX_GROUP_ID 环境变量，语音合成不可用（降级）",
                    "data": {"degraded": True},
                },
                ensure_ascii=False,
            )
        vid = voice_id or creds["voice_id"]
        if not vid:
            return json.dumps(
                {
                    "status": "error",
                    "message": "未配置 MINIMAX_VOICE_ID，且未传入 voice_id 参数",
                    "data": {},
                },
                ensure_ascii=False,
            )
        data = _call_t2a(text, vid)
        if data is None:
            return json.dumps(
                {
                    "status": "error",
                    "degraded": True,
                    "message": "MiniMax t2a API 调用失败（网络或上游错误）",
                    "data": {"degraded": True},
                },
                ensure_ascii=False,
            )
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            return json.dumps(
                {
                    "status": "error",
                    "message": f"MiniMax 上游返回错误: {base_resp.get('status_msg')}",
                    "data": {"status_code": base_resp.get("status_code")},
                },
                ensure_ascii=False,
            )
        audio_hex = (data.get("data") or {}).get("audio")
        if not audio_hex:
            return json.dumps(
                {
                    "status": "error",
                    "message": "MiniMax 未返回音频数据",
                    "data": {},
                },
                ensure_ascii=False,
            )
        try:
            audio_b64 = _hex_to_base64(audio_hex)
        except (binascii.Error, ValueError):
            return json.dumps(
                {"status": "error", "message": "MiniMax 返回的音频数据非 hex", "data": {}},
                ensure_ascii=False,
            )
        raw = binascii.unhexlify(audio_hex)
        fname = f"minimax_{vid}_{int(time.time() * 1000)}.mp3"
        fpath = CACHE_DIR / fname
        fpath.write_bytes(raw)
        extra = data.get("extra_info") or {}
        return json.dumps(
            {
                "status": "ok",
                "message": "语音合成完成",
                "data": {
                    "voice_id": vid,
                    "file": str(fpath),
                    "file_size": len(raw),
                    "audio_base64": audio_b64,
                    "audio_length_s": extra.get("audio_length"),
                    "sample_rate": extra.get("audio_sample_rate"),
                },
            },
            ensure_ascii=False,
        )

    def _do_status(self) -> str:
        creds = _credentials()
        return json.dumps(
            {
                "status": "ok",
                "message": "voice-mcp (MiniMax) 配置状态",
                "data": {
                    "api_key_configured": bool(creds["api_key"]),
                    "group_id_configured": bool(creds["group_id"]),
                    "voice_id_configured": bool(creds["voice_id"]),
                    "ready": bool(creds["api_key"] and creds["group_id"] and creds["voice_id"]),
                },
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # MCP 统一入口
    # ------------------------------------------------------------------
    async def handle_handoff(self, task: Dict[str, Any]) -> str:
        """MCP 调度入口：task 含 tool_name，对齐 agent_weather_time 协议。"""
        tool_name = (task.get("tool_name") or "").strip()
        try:
            if tool_name in ("voice_speak", "speak"):
                return self._do_speak(
                    text=str(task.get("text") or ""),
                    voice_id=str(task.get("voice_id") or ""),
                )
            if tool_name in ("voice_status", "status"):
                return self._do_status()
            return json.dumps(
                {
                    "status": "error",
                    "message": f"未知操作: {tool_name}",
                    "data": {},
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001 - 工具调用异常返回 JSON 而非抛出
            return json.dumps(
                {
                    "status": "error",
                    "message": f"工具调用失败: {exc}",
                    "data": {},
                },
                ensure_ascii=False,
            )
