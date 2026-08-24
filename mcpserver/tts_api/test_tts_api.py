"""TTS-API MCP 封装测试（离线，mock HTTP）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from unittest import mock

import pytest

# 允许从 scratchpad 根目录 import mcpserver.tts_api.agent
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mcpserver.tts_api.agent import TTSApiAgent  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _make_agent(tmp_path, base_url="http://tts.test"):
    return TTSApiAgent(base_url=base_url, api_key="secret-key", output_dir=str(tmp_path))


def test_tts_speak_ok(tmp_path):
    agent = _make_agent(tmp_path)
    with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"\xff\xfbMP3DATA", {"Content-Type": "audio/mpeg"})) as m:
        result = agent.invoke("tts_speak", {"text": "你好", "engine": "kokoro", "voice": "zf_xiaoxiao", "speed": 1.2})

    assert result["success"] is True
    assert result["engine"] == "kokoro"
    assert result["voice"] == "zf_xiaoxiao"
    assert result["size_bytes"] == len(b"\xff\xfbMP3DATA")
    assert os.path.exists(result["path"])
    with open(result["path"], "rb") as f:
        assert f.read() == b"\xff\xfbMP3DATA"

    # 校验请求 URL 与 payload
    req = m.call_args[0][0]
    assert req.full_url == "http://tts.test/v1/audio/speech"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["input"] == "你好"
    assert payload["model"] == "kokoro"
    assert payload["voice"] == "zf_xiaoxiao"
    assert payload["speed"] == 1.2
    assert payload["response_format"] == "mp3"
    assert req.get_header("Authorization") == "Bearer secret-key"


def test_tts_speak_empty_text(tmp_path):
    agent = _make_agent(tmp_path)
    result = agent.invoke("tts_speak", {"text": "   "})
    assert result["success"] is False
    assert "text" in result["error"]


def test_tts_speak_bad_format(tmp_path):
    agent = _make_agent(tmp_path)
    result = agent.invoke("tts_speak", {"text": "hi", "response_format": "ogg"})
    assert result["success"] is False
    assert "response_format" in result["error"]


def test_tts_speak_http_error(tmp_path):
    agent = _make_agent(tmp_path)

    def _raise(*a, **k):
        raise urllib.error.HTTPError("http://tts.test/v1/audio/speech", 401, "Unauthorized", {}, None)

    with mock.patch("urllib.request.urlopen", side_effect=_raise):
        result = agent.invoke("tts_speak", {"text": "hi"})
    assert result["success"] is False
    assert "401" in result["error"]


def test_tts_list_voices(tmp_path):
    agent = _make_agent(tmp_path)
    body = json.dumps({"object": "list", "data": [{"id": "zf_xiaoxiao"}, {"id": "en-US-AvaNeural"}]}).encode("utf-8")
    with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)) as m:
        result = agent.invoke("tts_list_voices", {})
    assert result["success"] is True
    assert result["count"] == 2
    assert m.call_args[0][0].full_url == "http://tts.test/v1/audio/voices"


def test_tts_health(tmp_path):
    agent = _make_agent(tmp_path)
    body = json.dumps({"status": "engine running", "ready": True, "max_text_length": 100000}).encode("utf-8")
    with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)):
        result = agent.invoke("tts_health", {})
    assert result["success"] is True
    assert result["ready"] is True


def test_invoke_unknown_command(tmp_path):
    agent = _make_agent(tmp_path)
    result = agent.invoke("nope", {})
    assert result["success"] is False
    assert "unknown" in result["error"] or "未知" in result["error"]
    assert "tts_speak" in result["available_commands"]
