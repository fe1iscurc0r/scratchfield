# voice_mcp_minimax 单元测试 — 缺凭据降级 + mock 上游契约验证
#
# 覆盖：空 text 校验 / 缺 MINIMAX_API_KEY|GROUP_ID 降级 / 缺 voice_id /
#       _call_t2a mock（成功/网络失败/上游错误/hex非法/无音频）/ status / handoff 路由 / 异常安全
# 运行：python3 -m pytest mcpserver/voice_mcp_minimax/test_voice_mcp_minimax.py -q
"""Tests for voice_mcp_minimax MCP agent (credential degradation + API contract)."""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

import pytest

from mcpserver.voice_mcp_minimax.voice_mcp_minimax import (
    MINIMAX_T2A_URL,
    VoiceMCPMinimaxAgent,
    _credentials,
    _hex_to_base64,
)

# 清掉环境变量：默认走「缺凭据降级」分支
for k in ("MINIMAX_API_KEY", "MINIMAX_GROUP_ID", "MINIMAX_VOICE_ID"):
    os.environ.pop(k, None)


@pytest.fixture()
def agent() -> VoiceMCPMinimaxAgent:
    return VoiceMCPMinimaxAgent()


def _parse(resp: str) -> dict:
    return json.loads(resp)


# ---------------------------------------------------------------- 凭据/校验
class TestCredentials:
    def test_missing_credentials(self) -> None:
        c = _credentials()
        assert c["api_key"] == ""
        assert c["group_id"] == ""
        assert c["voice_id"] == ""

    def test_credentials_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ):
            c = _credentials()
            assert c == {"api_key": "k", "group_id": "g", "voice_id": "v"}


class TestSpeakValidation:
    def test_empty_text_rejected(self, agent) -> None:
        r = _parse(agent._do_speak("", ""))
        assert r["status"] == "error"
        assert "不能为空" in r["message"]

    def test_degraded_without_credentials(self, agent) -> None:
        r = _parse(agent._do_speak("你好", ""))
        assert r["status"] == "error"
        assert r["degraded"] is True
        assert "MINIMAX_API_KEY" in r["message"]

    def test_missing_voice_id(self, agent) -> None:
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g"},
            clear=False,
        ):
            # 有 key/group 但无 voice_id 且未传参
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "error"
            assert "voice_id" in r["message"]


# ---------------------------------------------------------------- 上游契约
class TestCallT2a:
    def test_no_credentials_returns_none(self) -> None:
        assert _call_t2a_missing_creds() is None

    def test_network_failure_degraded(self, agent) -> None:
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax._call_t2a",
            return_value=None,
        ):
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "error"
            assert r["degraded"] is True
            assert "t2a" in r["message"]

    def test_upstream_error_reported(self, agent, tmp_path) -> None:
        fake = {"base_resp": {"status_code": 1004, "status_msg": "Rate limit"}}
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax._call_t2a",
            return_value=fake,
        ):
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "error"
            assert "Rate limit" in r["message"]
            assert r["data"]["status_code"] == 1004

    def test_no_audio_data(self, agent) -> None:
        fake = {"base_resp": {"status_code": 0}, "data": {}}
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax._call_t2a",
            return_value=fake,
        ):
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "error"
            assert "未返回音频" in r["message"]

    def test_success_writes_file(self, agent, tmp_path) -> None:
        # "00ff80" hex → 3 字节音频
        hex_audio = "00ff80"
        fake = {
            "base_resp": {"status_code": 0},
            "data": {"audio": hex_audio},
            "extra_info": {"audio_length": "1.5", "audio_sample_rate": "24000"},
        }
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax._call_t2a",
            return_value=fake,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax.CACHE_DIR",
            tmp_path,
        ):
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "ok"
            assert r["data"]["file_size"] == 3
            assert r["data"]["audio_base64"] == _hex_to_base64(hex_audio)
            assert r["data"]["voice_id"] == "v"
            assert r["data"]["audio_length_s"] == "1.5"
            assert os.path.exists(r["data"]["file"])

    def test_invalid_hex_rejected(self, agent) -> None:
        fake = {"base_resp": {"status_code": 0}, "data": {"audio": "zzzz-not-hex"}}
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ), patch(
            "mcpserver.voice_mcp_minimax.voice_mcp_minimax._call_t2a",
            return_value=fake,
        ):
            r = _parse(agent._do_speak("你好", ""))
            assert r["status"] == "error"
            assert "非 hex" in r["message"]


def _call_t2a_missing_creds():
    from mcpserver.voice_mcp_minimax.voice_mcp_minimax import _call_t2a

    return _call_t2a("hi", "v")


# ---------------------------------------------------------------- status
class TestStatus:
    def test_status_structure_not_ready(self, agent) -> None:
        r = _parse(agent._do_status())
        assert r["status"] == "ok"
        assert r["data"]["api_key_configured"] is False
        assert r["data"]["ready"] is False

    def test_status_ready_with_all_creds(self, agent) -> None:
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g", "MINIMAX_VOICE_ID": "v"},
            clear=False,
        ):
            r = _parse(agent._do_status())
            assert r["data"]["ready"] is True


# ---------------------------------------------------------------- handoff 路由
class TestHandleHandoff:
    def test_speak_route(self, agent) -> None:
        with patch.object(agent, "_do_speak", return_value='{"status":"ok"}'):
            out = asyncio.run(agent.handle_handoff({"tool_name": "voice_speak", "text": "x"}))
            assert json.loads(out)["status"] == "ok"

    def test_status_route(self, agent) -> None:
        with patch.object(agent, "_do_status", return_value='{"status":"ok"}'):
            out = asyncio.run(agent.handle_handoff({"tool_name": "voice_status"}))
            assert json.loads(out)["status"] == "ok"

    def test_unknown_route(self, agent) -> None:
        out = asyncio.run(agent.handle_handoff({"tool_name": "voice_nope"}))
        assert json.loads(out)["status"] == "error"

    def test_exception_safe(self, agent) -> None:
        with patch.object(
            agent, "_do_speak", side_effect=RuntimeError("boom")
        ):
            out = asyncio.run(agent.handle_handoff({"tool_name": "speak", "text": "x"}))
            assert json.loads(out)["status"] == "error"
            assert "boom" in json.loads(out)["message"]


# ---------------------------------------------------------------- 工具函数
class TestHexToBase64:
    def test_basic(self) -> None:
        assert _hex_to_base64("00ff80") == "AP+A"
        assert _hex_to_base64("ff") == "/w=="

    def test_invalid(self) -> None:
        with pytest.raises(Exception):
            _hex_to_base64("xyz")
