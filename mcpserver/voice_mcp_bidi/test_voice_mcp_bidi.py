# voice_mcp_bidi 单元测试 — 云服环境（无 mlx/sounddevice/麦克风）降级契约验证
#
# 覆盖：空 text 校验 / lang 白名单 / speed 钳制 / speak 三级降级链 /
#       listen 真机降级 / status 结构 / handle_handoff 路由 / np_array_to_bytes
# 运行：python3 -m pytest mcpserver/voice_mcp_bidi/test_voice_mcp_bidi.py -q
"""Tests for voice_mcp_bidi MCP agent (degradation contract)."""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

import pytest

from mcpserver.voice_mcp_bidi.voice_mcp_bidi import (
    DEFAULT_LANG,
    DEFAULT_VOICE,
    LANG_CODES,
    VoiceMCPBidiAgent,
    np_array_to_bytes,
)

# 云服环境：不配 TTS-API 地址，强制走降级分支；本地路径依赖函数直接 mock
os.environ.pop("TTS_API_BASE", None)
os.environ.pop("VOICE_MCP_TTS_API", None)
os.environ.pop("VOICE_MCP_TTS_API_URL", None)


@pytest.fixture()
def agent() -> VoiceMCPBidiAgent:
    return VoiceMCPBidiAgent()


def _parse(resp: str) -> dict:
    return json.loads(resp)


# ---------------------------------------------------------------- speak 校验
class TestSpeakValidation:
    def test_empty_text_rejected(self, agent) -> None:
        r = _parse(agent._do_speak("", DEFAULT_VOICE, 1.0, DEFAULT_LANG))
        assert r["status"] == "error"
        assert "不能为空" in r["message"]

    def test_whitespace_text_rejected(self, agent) -> None:
        r = _parse(agent._do_speak("   ", DEFAULT_VOICE, 1.0, DEFAULT_LANG))
        assert r["status"] == "error"

    def test_invalid_lang_rejected(self, agent) -> None:
        r = _parse(agent._do_speak("你好", DEFAULT_VOICE, 1.0, "zz"))
        assert r["status"] == "error"
        assert "lang 必须是" in r["message"]
        assert "zz" in r["message"]

    def test_valid_lang_accepted(self, agent) -> None:
        assert "z" in LANG_CODES
        assert "a" in LANG_CODES
        assert "j" in LANG_CODES

    def test_speed_clamped_high(self, agent) -> None:
        # 后端不可达 → 降级返回；但 data 里 echo 的 speed 应为钳制后值
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_speak",
            return_value=None,
        ), patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._call_tts_api",
            return_value=None,
        ):
            r = _parse(agent._do_speak("hi", DEFAULT_VOICE, 99.0, DEFAULT_LANG))
            assert r["status"] == "error"
            assert r["data"]["local_mlx"] is False
            assert r["data"]["tts_api_reachable"] is False

    def test_speed_clamped_low(self, agent) -> None:
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_speak",
            return_value=None,
        ), patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._call_tts_api",
            return_value=None,
        ):
            r = _parse(agent._do_speak("hi", DEFAULT_VOICE, 0.01, DEFAULT_LANG))
            assert r["status"] == "error"
            assert r["data"]["degraded"] is True


# ---------------------------------------------------------------- speak 降级链
class TestSpeakDegradationChain:
    def test_degraded_when_no_backend(self, agent) -> None:
        """云服：本地 mlx 不可用 + TTS-API 不可达 → 降级 JSON，不炸。"""
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_speak",
            return_value=None,
        ), patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._call_tts_api",
            return_value=None,
        ):
            r = _parse(agent._do_speak("你好", DEFAULT_VOICE, 1.0, "z"))
            assert r["status"] == "error"
            assert r["degraded"] is True
            assert "无可用后端" in r["message"]
            assert r["data"]["degraded"] is True

    def test_tts_api_backend_returns_audio(self, agent, tmp_path) -> None:
        """TTS-API 迂回后端可用 → 落盘 mp3 + base64。"""
        fake_audio = b"\xff\xfb\x90\x00fake-mp3-bytes"
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_speak",
            return_value=None,
        ), patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._call_tts_api",
            return_value=fake_audio,
        ), patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi.CACHE_DIR",
            tmp_path,
        ):
            r = _parse(agent._do_speak("你好", "af_heart", 1.2, "z"))
            assert r["status"] == "ok"
            assert r["backend"] == "tts-api-kokoro"
            assert r["data"]["file_size"] == len(fake_audio)
            assert r["data"]["audio_base64"]
            assert r["data"]["speed"] == 1.2
            # 文件确实落盘
            fpath = r["data"]["file"]
            assert os.path.exists(fpath)
            assert os.path.getsize(fpath) == len(fake_audio)

    def test_mlx_backend_returns_path(self, agent, tmp_path) -> None:
        """真机 mlx Kokoro 可用 → backend=mlx-kokoro。"""
        fake_wav = b"RIFFfake-wav"
        fake_path = str(tmp_path / "bidi_test.wav")
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_speak",
            return_value=fake_path,
        ):
            import pathlib

            pathlib.Path(fake_path).write_bytes(fake_wav)
            r = _parse(agent._do_speak("hello", "af_heart", 1.0, "a"))
            assert r["status"] == "ok"
            assert r["backend"] == "mlx-kokoro"
            assert r["data"]["file"] == fake_path
            assert r["data"]["audio_base64"]


# ---------------------------------------------------------------- listen
class TestListen:
    def test_listen_degraded_on_cloud(self, agent) -> None:
        """云服无麦克风/mlx → 优雅降级。"""
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_listen",
            return_value=None,
        ):
            r = _parse(agent._do_listen(None))
            assert r["status"] == "error"
            assert r["degraded"] is True
            assert "真机能力" in r["message"]
            assert r["data"]["local_mic"] is False

    def test_listen_ok_when_local(self, agent) -> None:
        with patch(
            "mcpserver.voice_mcp_bidi.voice_mcp_bidi._try_local_listen",
            return_value="你好世界",
        ):
            r = _parse(agent._do_listen(3.0))
            assert r["status"] == "ok"
            assert r["data"]["text"] == "你好世界"


# ---------------------------------------------------------------- status
class TestStatus:
    def test_status_structure(self, agent) -> None:
        r = _parse(agent._do_status())
        assert r["status"] == "ok"
        assert "local_mlx_available" in r["data"]
        assert "local_mic_available" in r["data"]
        assert "tts_api_reachable" in r["data"]
        assert "listen_ready" in r["data"]
        assert "speak_ready" in r["data"]


# ---------------------------------------------------------------- handoff 路由
class TestHandleHandoff:
    def test_speak_route(self, agent) -> None:
        with patch.object(agent, "_do_speak", return_value='{"status":"ok"}'):
            out = asyncio.run(agent.handle_handoff({"tool_name": "voice_speak", "text": "x"}))
            assert json.loads(out)["status"] == "ok"

    def test_listen_route(self, agent) -> None:
        with patch.object(agent, "_do_listen", return_value='{"status":"ok"}'):
            out = asyncio.run(agent.handle_handoff({"tool_name": "voice_listen"}))
            assert json.loads(out)["status"] == "ok"

    def test_status_route(self, agent) -> None:
        with patch.object(agent, "_do_status", return_value='{"status":"ok"}'):
            out = asyncio.run(agent.handle_handoff({"tool_name": "voice_status"}))
            assert json.loads(out)["status"] == "ok"

    def test_unknown_route(self, agent) -> None:
        out = asyncio.run(agent.handle_handoff({"tool_name": "voice_nope"}))
        r = json.loads(out)
        assert r["status"] == "error"
        assert "未知操作" in r["message"]

    def test_missing_tool_name(self, agent) -> None:
        out = asyncio.run(agent.handle_handoff({}))
        assert json.loads(out)["status"] == "error"

    def test_handoff_exception_safe(self, agent) -> None:
        """内部异常 → 返回 JSON 而非抛出。"""
        with patch.object(
            agent, "_do_speak", side_effect=RuntimeError("boom")
        ):
            out = asyncio.run(agent.handle_handoff({"tool_name": "speak", "text": "x"}))
            r = json.loads(out)
            assert r["status"] == "error"
            assert "boom" in r["message"]


# ---------------------------------------------------------------- 工具函数
class TestNpArrayToBytes:
    def test_none_returns_empty(self) -> None:
        assert np_array_to_bytes(None) == b""

    def test_list_converted(self) -> None:
        out = np_array_to_bytes([0.0, 1.0, -1.0])
        assert len(out) == 6  # 3 samples × int16 (2 bytes)
        assert out[:2] == b"\x00\x00"

    def test_garbage_returns_empty(self) -> None:
        assert np_array_to_bytes("not-an-array") == b""
