"""X-02 验收测试：语音实验记录（ASR → ELN 草稿）。

覆盖：
  1. 智能分段（四段关键词 / 默认归操作 / 空文本）
  2. ELN 草稿生成（Markdown 含四段标题）
  3. ASR 转写（无 ASR_URL → mock / ASR 失败 → mock / ASR 成功 → 真文本）
  4. 草稿保存 + 追加（临时目录隔离）
  5. 端点集成（mock ASR）：transcribe / segment / save / drafts
  6. 空录音降级（422）

运行：python -m pytest apiserver/routes/tests/test_voice_eln.py -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth
from apiserver.routes import voice_eln as voice_eln_module
from apiserver.routes.voice_eln import (
    _MOCK_ASR_TEXT,
    build_eln_draft,
    save_draft,
    segment_text,
    transcribe_audio,
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + 隔离数据目录（草稿落临时目录）+ 清空 ASR 配置 + 真实 app。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    monkeypatch.setattr(voice_eln_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.delenv("ASR_API_URL", raising=False)
    from apiserver.api_server import app

    return TestClient(app)


# ============ 1. 智能分段 ============


def test_segment_text_four_sections():
    """含四个关键词的文本 → 正确分到四段。"""
    text = "目的是测 FT8\n操作 连接电台\n结果 解出呼号\n备注 天线偏高"
    sections = segment_text(text)
    assert "目的" in sections["purpose"]
    assert "连接电台" in sections["operation"]
    assert "解出呼号" in sections["result"]
    assert "天线偏高" in sections["remark"]


def test_segment_text_default_operation():
    """无关键词的文本默认归入操作段。"""
    sections = segment_text("打开设备\n观察波形")
    assert "打开设备" in sections["operation"]
    assert sections["purpose"] == ""
    assert sections["result"] == ""
    assert sections["remark"] == ""


def test_segment_text_empty():
    """空文本 → 四段全空（不崩溃）。"""
    sections = segment_text("")
    assert sections == {"purpose": "", "operation": "", "result": "", "remark": ""}


# ============ 2. ELN 草稿生成 ============


def test_build_eln_draft_contains_sections():
    """草稿 Markdown 含四段标题与内容。"""
    sections = {"purpose": "P", "operation": "O", "result": "R", "remark": "M"}
    draft = build_eln_draft(sections, title="FT8 测试", timestamp="2026-08-25T00:00:00+00:00")
    assert "## 目的" in draft and "P" in draft
    assert "## 操作" in draft and "O" in draft
    assert "## 结果" in draft and "R" in draft
    assert "## 备注" in draft and "M" in draft
    assert "2026-08-25T00:00:00+00:00" in draft


def test_build_eln_draft_empty_sections_placeholder():
    """空段用（无）占位。"""
    draft = build_eln_draft({"purpose": "", "operation": "", "result": "", "remark": ""})
    assert draft.count("（无）") == 4


# ============ 3. ASR 转写（降级） ============


def test_transcribe_mock_when_no_url(monkeypatch):
    """未配置 ASR_API_URL → mock 降级。"""
    monkeypatch.delenv("ASR_API_URL", raising=False)
    text, provider = transcribe_audio(b"fake-audio")
    assert provider == "mock"
    assert text == _MOCK_ASR_TEXT


def test_transcribe_fallback_when_asr_fails(monkeypatch):
    """ASR 调用抛异常 → 降级 mock（绝不静默/抛错）。"""
    monkeypatch.setenv("ASR_API_URL", "http://127.0.0.1:1/v1")

    def boom(*args, **kwargs):
        raise RuntimeError("asr down")

    monkeypatch.setattr(voice_eln_module, "_call_openai_asr", boom)
    text, provider = transcribe_audio(b"fake-audio")
    assert provider == "mock"
    assert text == _MOCK_ASR_TEXT


def test_transcribe_success_uses_asr(monkeypatch):
    """ASR 成功 → 返回真实转写文本，provider=asr。"""
    monkeypatch.setenv("ASR_API_URL", "http://127.0.0.1:5001/v1")
    monkeypatch.setattr(voice_eln_module, "_call_openai_asr", lambda *a, **k: "自定义转写文本")
    text, provider = transcribe_audio(b"fake-audio")
    assert provider == "asr"
    assert text == "自定义转写文本"


# ============ 4. 草稿保存 + 追加 ============


def test_save_draft_new_and_append(tmp_path, monkeypatch):
    """保存新建 + 追加到已有草稿。"""
    monkeypatch.setattr(voice_eln_module, "get_data_dir", lambda: tmp_path)
    r1 = save_draft("测试实验", "# 草稿一\n")
    assert r1["ok"] is True and r1["mode"] == "new"
    assert r1["draft_id"]

    r2 = save_draft("", "# 追加内容\n", draft_id=r1["draft_id"])
    assert r2["ok"] is True and r2["mode"] == "append"

    content = (tmp_path / "voice_eln" / f"{r1['draft_id']}.md").read_text(encoding="utf-8")
    assert "# 草稿一" in content
    assert "# 追加内容" in content  # 追加后同文件包含两段


# ============ 5. 端点集成（mock ASR） ============


def test_endpoint_transcribe(client):
    """上传音频（mock ASR）→ 转写 + 分段 + 草稿一步到位。"""
    resp = client.post(
        "/api/voice-eln/transcribe",
        files={"audio": ("rec.wav", b"RIFFxxxx", "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["provider"] == "mock"
    assert body["text"] == _MOCK_ASR_TEXT
    assert "## 目的" in body["draft"]
    assert body["sections"]["purpose"] != ""


def test_endpoint_segment(client):
    """对文本重新分段并生成草稿。"""
    resp = client.post("/api/voice-eln/segment", json={"text": "目的 A\n操作 B\n结果 C"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "A" in body["sections"]["purpose"]
    assert "C" in body["sections"]["result"]
    assert "## 结果" in body["draft"]


def test_endpoint_save_and_list(client):
    """保存草稿后能列出。"""
    save_resp = client.post("/api/voice-eln/save", json={"title": "端点测试", "markdown": "# 端点草稿\n"})
    assert save_resp.status_code == 200
    draft_id = save_resp.json()["draft_id"]
    assert save_resp.json()["mode"] == "new"

    list_resp = client.get("/api/voice-eln/drafts")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["count"] == 1
    assert body["drafts"][0]["draft_id"] == draft_id


# ============ 6. 空录音降级 ============


def test_endpoint_transcribe_empty(client):
    """空录音 → 422（明确报错，不静默）。"""
    resp = client.post(
        "/api/voice-eln/transcribe",
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 422
    assert "空录音" in resp.json()["detail"]
