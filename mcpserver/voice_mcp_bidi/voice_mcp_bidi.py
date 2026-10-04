# voice_mcp_bidi.py — shreyaskarnik/voice-mcp 的 MCP 桥接 agent
#
# 耦合目标：https://github.com/shreyaskarnik/voice-mcp (Apache-2.0)
# 上游形态：FastMCP stdio server（Claude Code 双向语音），核心工具：
#   - listen()  — 麦克风 + webrtcvad(VAD) + Voxtral Realtime STT → 文本
#   - speak()   — Kokoro TTS（82M 参数，9 语言 / 54 音色）→ 扬声器播放
# 上游依赖：mlx-audio（仅 Apple Silicon）、sounddevice、webrtcvad —— 真机硬件能力。
#
# 接入评估：上游是「真机双向语音」服务器，无法直接注册进 scratchpad 的
#           Python MCP 注册表（Format A: module + class + handle_handoff）。
#           故「改造接入」：复刻 listen/speak 工具语义。
#           - speak 后端可切换：真机 mlx Kokoro（待联调）→ 云服 TTS-API 的
#             kokoro 引擎（同源模型，迂回路径）→ 降级。
#           - listen 是真机能力（麦克风 + STT 模型），云服优雅降级。
#
# 契约（对齐 mcp_registry Format A）：
#   class VoiceMCPBidiAgent 实现 async handle_handoff(task) -> str
#
# 运行态降级（对齐 omnilimb_face / voice_mcp_minimax 降级契约）：
#   后端不可用 → 返回 {"status":"error","degraded":true,...}，不炸注册流程。
#
# 仅用标准库（urllib + base64 + json）；mlx/sounddevice 均惰性导入，云服缺依赖不炸。

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(
    os.environ.get("VOICE_MCP_CACHE_DIR", str(Path(__file__).resolve().parent / ".cache"))
)

# 上游 Kokoro 语言码（对齐 README.md:62-67 / server.py 指令块）：
#   a=美英 b=英英 e=西 f=法 h=印 i=意 j=日 p=葡 z=普通话
LANG_CODES = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}
DEFAULT_VOICE = "af_heart"  # 上游默认音色（美国女声）
DEFAULT_LANG = "a"

# 迂回后端：scratchpad 已封装的 TTS-API（babutree，kokoro 引擎与上游同源）
TTS_API_BASE = os.environ.get("TTS_API_BASE_URL", "http://127.0.0.1:8880").rstrip("/")

# 真机 STT/TTS 模型（上游 HuggingFace 仓库）
STT_MODEL_REPO = "mlx-community/Voxtral-Mini-4B-Realtime-2602-int4"
TTS_MODEL_REPO = "mlx-community/Kokoro-82M-bf16"
MIC_SAMPLE_RATE = 16_000
SPEAKER_SAMPLE_RATE = 24_000


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# 真机能力探测（惰性导入，云服返回 False）
# ---------------------------------------------------------------------------

def _local_mlx_available() -> bool:
    """是否可导入 mlx-audio（真机 Apple Silicon 才有）。"""
    try:
        import mlx_audio  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - 探测失败视为不可用
        return False


def _local_mic_available() -> bool:
    """是否可导入 sounddevice + webrtcvad（真机麦克风才有）。"""
    try:
        import sounddevice  # noqa: F401
        import webrtcvad  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - 探测失败视为不可用
        return False


def _try_local_speak(text: str, voice: str, speed: float, lang: str) -> str | None:
    """真机路径：mlx Kokoro TTS → 落盘 wav，返回文件路径；失败返回 None。

    仅 Apple Silicon + mlx-audio 可用（待联调）。对齐上游 server.py:229-267。
    """
    if not _local_mlx_available():
        return None
    try:
        from mlx_audio.tts import load as load_tts

        model = load_tts(TTS_MODEL_REPO)
        segs = list(model.generate(text=text, voice=voice, speed=speed, lang_code=lang))
        # 合并各 segment 的音频为一段 wav
        import wave

        audio = b"".join(
            bytes(np_array_to_bytes(getattr(seg, "audio", None))) for seg in segs
        )
        fname = f"bidi_kokoro_{voice}_{int(time.time() * 1000)}.wav"
        fpath = CACHE_DIR / fname
        with wave.open(str(fpath), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SPEAKER_SAMPLE_RATE)
            w.writeframes(audio)
        return str(fpath)
    except Exception as exc:  # noqa: BLE001 - 真机路径失败降级到下一后端
        logger.warning("local mlx speak 失败: %s", exc)
        return None


def np_array_to_bytes(arr: Any) -> bytes:
    """把 numpy ndarray（float32 音频）转 int16 字节。无 numpy 时返回 b''。"""
    if arr is None:
        return b""
    try:
        import numpy as np

        a = np.asarray(arr)
        return (a * 32767).astype(np.int16).tobytes()
    except Exception:  # noqa: BLE001
        return b""


def _try_local_listen(duration: float | None) -> str | None:
    """真机路径：麦克风 + webrtcvad + Voxtral STT → 文本；失败返回 None。

    仅 Apple Silicon + 麦克风可用（待联调）。对齐上游 server.py:204-226。
    """
    if not (_local_mic_available() and _local_mlx_available()):
        return None
    try:
        import numpy as np
        import sounddevice as sd
        import webrtcvad

        # 简化：固定时长录音（真机联调时再补 VAD 自动停止，对齐上游 record_until_silence）
        dur = duration if duration and duration > 0 else 3.0
        raw = sd.rec(int(MIC_SAMPLE_RATE * dur), samplerate=MIC_SAMPLE_RATE,
                     channels=1, dtype="int16")
        sd.wait()
        audio = np.asarray(raw).flatten().astype(np.float32) / 32768.0

        import mlx.core as mx
        from mlx_audio.stt import load as load_stt

        model = load_stt(STT_MODEL_REPO)
        result = model.generate(mx.array(audio))
        text = (getattr(result, "text", None) or "").strip()
        return text or "(no speech detected)"
    except Exception as exc:  # noqa: BLE001 - 真机路径失败降级
        logger.warning("local mic listen 失败: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 迂回后端：TTS-API（kokoro 引擎，与上游 Kokoro 同源）
# ---------------------------------------------------------------------------

def _tts_api_reachable(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(TTS_API_BASE, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _call_tts_api(text: str, voice: str, speed: float) -> bytes | None:
    """TTS-API /api/tts（engine=kokoro）→ mp3 字节；失败返回 None。

    契约对齐 babutree/TTS-API app.py:2814(api_tts)，请求体
    {text, engine, voice, speed}，响应头 Content-Type: audio/mpeg。
    """
    if not _tts_api_reachable():
        return None
    payload = {
        "text": text,
        "engine": "kokoro",
        "voice": voice,
        "speed": speed,
    }
    req = urllib.request.Request(
        f"{TTS_API_BASE}/api/tts",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - 降级契约
        logger.warning("TTS-API speak 失败: %s", exc)
        return None


class VoiceMCPBidiAgent:
    """shreyaskarnik/voice-mcp 的 MCP agent（改造接入）。

    提供三个工具：
    - ``voice_speak`` — Kokoro 语音合成（真机 mlx 或迂回 TTS-API），落盘 + base64
    - ``voice_listen`` — 麦克风录音 + STT（真机能力，云服降级）
    - ``voice_status`` — 后端可用性健康检查
    """

    name = "voice-mcp (Bidi) Agent"

    def __init__(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------
    def _do_speak(self, text: str, voice: str, speed: float, lang: str) -> str:
        if not text.strip():
            return json.dumps(
                {"status": "error", "message": "text 不能为空", "data": {}},
                ensure_ascii=False,
            )
        vid = voice or DEFAULT_VOICE
        if lang and lang not in LANG_CODES:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"lang 必须是 {sorted(LANG_CODES)} 之一，收到 '{lang}'",
                    "data": {"lang": lang},
                },
                ensure_ascii=False,
            )
        lang = lang or DEFAULT_LANG
        spd = max(0.5, min(3.0, float(speed or 1.0)))

        # ① 真机 mlx Kokoro（待联调）
        local_path = _try_local_speak(text, vid, spd, lang)
        if local_path:
            raw = Path(local_path).read_bytes()
            return json.dumps(
                {
                    "status": "ok",
                    "backend": "mlx-kokoro",
                    "message": "语音合成完成（真机 mlx Kokoro）",
                    "data": {
                        "voice": vid,
                        "lang": lang,
                        "speed": spd,
                        "file": local_path,
                        "file_size": len(raw),
                        "audio_base64": base64.b64encode(raw).decode("ascii"),
                    },
                },
                ensure_ascii=False,
            )

        # ② 迂回 TTS-API kokoro（云服同源引擎）
        audio = _call_tts_api(text, vid, spd)
        if audio:
            fname = f"bidi_kokoro_{vid}_{int(time.time() * 1000)}.mp3"
            fpath = CACHE_DIR / fname
            fpath.write_bytes(audio)
            return json.dumps(
                {
                    "status": "ok",
                    "backend": "tts-api-kokoro",
                    "message": "语音合成完成（TTS-API kokoro 迂回后端）",
                    "data": {
                        "voice": vid,
                        "lang": lang,
                        "speed": spd,
                        "file": str(fpath),
                        "file_size": len(audio),
                        "audio_base64": base64.b64encode(audio).decode("ascii"),
                    },
                },
                ensure_ascii=False,
            )

        # ③ 降级
        return json.dumps(
            {
                "status": "error",
                "degraded": True,
                "message": (
                    "voice_speak 无可用后端：真机 mlx-audio 不可用，且 TTS-API "
                    f"({TTS_API_BASE}) 不可达。云服请先部署 TTS-API；真机请装 mlx-audio。"
                ),
                "data": {
                    "degraded": True,
                    "local_mlx": _local_mlx_available(),
                    "tts_api_reachable": _tts_api_reachable(),
                },
            },
            ensure_ascii=False,
        )

    def _do_listen(self, duration: float | None) -> str:
        # 真机路径（待联调）
        text = _try_local_listen(duration)
        if text is not None:
            return json.dumps(
                {"status": "ok", "message": "录音转写完成", "data": {"text": text}},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "error",
                "degraded": True,
                "message": (
                    "voice_listen 是真机能力（麦克风 + STT 模型），当前环境不可用。"
                    "需要 Apple Silicon + sounddevice/webrtcvad + mlx STT 模型。"
                ),
                "data": {"degraded": True, "local_mic": _local_mic_available(),
                         "local_mlx": _local_mlx_available()},
            },
            ensure_ascii=False,
        )

    def _do_status(self) -> str:
        return json.dumps(
            {
                "status": "ok",
                "message": "voice-mcp (Bidi) 后端可用性",
                "data": {
                    "local_mlx_available": _local_mlx_available(),
                    "local_mic_available": _local_mic_available(),
                    "tts_api_reachable": _tts_api_reachable(),
                    "listen_ready": _local_mic_available() and _local_mlx_available(),
                    "speak_ready": _local_mlx_available() or _tts_api_reachable(),
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
                    voice=str(task.get("voice") or ""),
                    speed=float(task.get("speed") or 1.0),
                    lang=str(task.get("lang") or ""),
                )
            if tool_name in ("voice_listen", "listen"):
                d = task.get("duration")
                return self._do_listen(float(d) if d not in (None, "") else None)
            if tool_name in ("voice_status", "status"):
                return self._do_status()
            return json.dumps(
                {"status": "error", "message": f"未知操作: {tool_name}", "data": {}},
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001 - 工具调用异常返回 JSON 而非抛出
            return json.dumps(
                {"status": "error", "message": f"工具调用失败: {exc}", "data": {}},
                ensure_ascii=False,
            )
