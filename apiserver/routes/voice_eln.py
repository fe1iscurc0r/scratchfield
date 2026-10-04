"""X-02: 语音实验记录（ASR → ELN 草稿）。

职责：
  1. 录音 → ASR 转写（复用已有语音管线：OpenAI 兼容 ``/audio/transcriptions``
     文件转写接口，即 LocalVoiceClientAdapter 同款；未配置 ASR_API_URL / 调用失败
     一律降级到内置 mock ASR，绝不静默失败）
  2. 智能分段：按"目的/操作/结果/备注"关键词启发式粗分（非语义理解，有局限）
  3. ELN 模板草稿生成（Markdown），可编辑后保存 / 追加

硬约束：
  - ASR 复用现有接口，不新造 ASR 轮子
  - 分段是启发式，标注局限
  - 录音文件临时使用，转写后即丢弃，不长期保留

配置（环境变量）：
  ASR_API_URL    OpenAI 兼容转写服务基地址，如 http://127.0.0.1:5001/v1；未设置 → mock
  ASR_MODEL      转写模型，默认 koboldcpp/GLM-ASR-Nano-1.6B-2512-Q4_K
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from system.config import get_data_dir

from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/voice-eln", tags=["voice-eln"])
logger = logging.getLogger(__name__)

# ============ 分段关键词（启发式，非语义） ============

# 顺序即匹配优先级；未命中任何关键词的行归入当前段落
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "purpose": ("目的", "目标", "打算", "计划", "要验证", "要测"),
    "result": ("结果", "得到", "发现", "观察到", "测得", "输出", "显示"),
    "remark": ("备注", "注意", "补充", "提醒", "问题", "下次", "待办"),
    "operation": ("操作", "步骤", "设置", "调到", "连接", "启动", "测量", "调整", "按下"),
}

SECTION_LABELS: dict[str, str] = {
    "purpose": "目的",
    "operation": "操作",
    "result": "结果",
    "remark": "备注",
}

_MOCK_ASR_TEXT = (
    "目的是验证 7.074 MHz FT8 接收链路\n"
    "操作 连接 IC-705 USB 声卡并设置频率\n"
    "结果 解出 3 个呼号 信噪比约 20 dB\n"
    "备注 天线驻波偏高 下次检查馈线"
)

_SLUG_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+")


# ============ 智能分段 ============


def segment_text(text: str) -> dict[str, str]:
    """按"目的/操作/结果/备注"关键词把转写文本启发式粗分。

    规则：逐行检查，命中某段关键词即把该行及后续归入该段（直到命中下一关键词）；
    无关键词的行跟随当前段落；默认（首行无关键词）归入"操作"。
    """
    sections: dict[str, list[str]] = {k: [] for k in SECTION_LABELS}
    current = "operation"
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        for key in SECTION_KEYWORDS:  # 固定优先级
            if any(kw in line for kw in SECTION_KEYWORDS[key]):
                current = key
                break
        sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


# ============ ELN 草稿生成 ============


def build_eln_draft(
    sections: dict[str, str],
    title: str = "",
    timestamp: str | None = None,
) -> str:
    """把四段内容组装成 Markdown ELN 草稿。"""
    ts = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# ELN 实验记录（草稿）",
        "",
        f"- 时间: {ts}",
        "- 状态: draft",
    ]
    if title:
        lines.append(f"- 标题: {title}")
    for key, label in SECTION_LABELS.items():
        lines.append("")
        lines.append(f"## {label}")
        lines.append("")
        lines.append(sections.get(key) or "（无）")
    return "\n".join(lines) + "\n"


# ============ ASR 转写（复用现有接口 + mock 降级） ============


def _call_openai_asr(audio_bytes: bytes, base_url: str, model: str) -> str:
    """调 OpenAI 兼容 ``/audio/transcriptions`` 文件转写接口（LocalVoiceClientAdapter 同款）。"""
    import requests  # 延迟导入：mock 路径无需 requests

    url = base_url.rstrip("/") + "/audio/transcriptions"
    resp = requests.post(
        url,
        files={"file": ("recording.wav", audio_bytes, "audio/wav")},
        data={"model": model, "language": "zh"},
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("ASR 返回空文本")
    return text


def transcribe_audio(audio_bytes: bytes, sample_rate: int = 16000) -> tuple[str, str]:
    """录音字节 → 转写文本。返回 (text, provider)，provider: 'asr' | 'mock'。

    未配置 ASR_API_URL 或调用失败一律降级到 mock（绝不抛异常、绝不静默空返回）。
    """
    url = os.environ.get("ASR_API_URL", "").strip()
    if not url:
        return _MOCK_ASR_TEXT, "mock"
    model = os.environ.get("ASR_MODEL", "koboldcpp/GLM-ASR-Nano-1.6B-2512-Q4_K")
    try:
        text = _call_openai_asr(audio_bytes, url, model)
        return text, "asr"
    except Exception as exc:  # 网络/服务/空文本 → 降级
        logger.warning("[voice-eln] ASR 转写失败，降级 mock: %s", exc)
        return _MOCK_ASR_TEXT, "mock"


# ============ 草稿落盘（可编辑后保存/追加） ============


def _drafts_dir() -> Path:
    return Path(get_data_dir()) / "voice_eln"


def _slug(text: str, fallback: str = "draft") -> str:
    slug = _SLUG_RE.sub("-", str(text).strip()).strip("-")
    return slug[:48] or fallback


def save_draft(title: str, markdown: str, draft_id: str | None = None) -> dict:
    """保存 / 追加 ELN 草稿（Markdown 文件）。draft_id 存在 → 追加，否则新建。"""
    d = _drafts_dir()
    d.mkdir(parents=True, exist_ok=True)
    if draft_id:
        draft_id = _slug(draft_id, "draft")
        path = d / f"{draft_id}.md"
        with path.open("a", encoding="utf-8") as f:
            f.write("\n---\n" + markdown.rstrip("\n") + "\n")
        return {"ok": True, "draft_id": draft_id, "mode": "append", "path": str(path)}
    draft_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _slug(title)
    path = d / f"{draft_id}.md"
    path.write_text(markdown, encoding="utf-8")
    return {"ok": True, "draft_id": draft_id, "mode": "new", "path": str(path)}


def list_drafts() -> list[dict]:
    """列出已保存的草稿（按修改时间倒序）。"""
    d = _drafts_dir()
    if not d.exists():
        return []
    drafts = []
    for p in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        drafts.append(
            {
                "draft_id": p.stem,
                "path": str(p),
                "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            }
        )
    return drafts


# ============ 请求模型 ============


class SegmentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000, description="转写文本")


class SaveRequest(BaseModel):
    title: str = Field("", max_length=200, description="草稿标题")
    markdown: str = Field(..., min_length=1, max_length=200_000, description="草稿 Markdown")
    draft_id: str | None = Field(None, max_length=64, description="存在则追加到该草稿")


# ============ 端点 ============


@router.post("/transcribe")
async def transcribe(
    audio: Annotated[UploadFile, File(..., description="录音音频文件")],
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """录音 → ASR 转写 → 智能分段 → ELN 草稿（一步到位）。"""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="空录音：未检测到音频数据")
    text, provider = transcribe_audio(data)
    sections = segment_text(text)
    draft = build_eln_draft(sections)
    return {"ok": True, "text": text, "provider": provider, "sections": sections, "draft": draft}


@router.post("/segment")
async def segment(
    body: SegmentRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """对已编辑的转写文本重新分段并生成草稿（转写预览可编辑后调用）。"""
    sections = segment_text(body.text)
    draft = build_eln_draft(sections)
    return {"ok": True, "sections": sections, "draft": draft}


@router.post("/save")
async def save(
    body: SaveRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """保存 / 追加 ELN 草稿。"""
    return save_draft(body.title, body.markdown, body.draft_id)


@router.get("/drafts")
async def drafts(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """列出已保存的草稿。"""
    items = list_drafts()
    return {"ok": True, "count": len(items), "drafts": items}
