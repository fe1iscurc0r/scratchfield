"""breeze-tts 引擎封装（与 `mcpserver/tts_api/agent.py` 同构）。

设计约束（工单 263 §1-D）：
* 本单**不下载权重**；权重目录走环境变量 ``BREEZE_TTS_MODEL_DIR``，缺失时抛可读 RuntimeError。
* 情绪标记（``[笑]`` / ``[叹气]`` / ``[咳嗽]``）由 ``parse_emotion_events`` 独立解析并从纯文本剔除。
* ``name`` / ``display_name`` / ``synthesize`` / ``list_voices`` / ``health`` 五个成员与现有
  `TTSApiAgent` 保持一致，便于上层按同一形态调用（**不自造 registry**）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

MODEL_DIR_ENV = "BREEZE_TTS_MODEL_DIR"

#: 已知情绪标记（可扩展；未知标记原样保留在文本里，不当情绪处理）
KNOWN_TAGS = ("笑", "叹气", "咳嗽", "哭", "惊讶", "生气")

_TAG_RE = re.compile(r"\[(?P<tag>[^\[\]]{1,8})\]")


@dataclass(frozen=True)
class EmotionEvent:
    """一处情绪标记：在**原始文本**中的区间 + 标签。"""

    start: int
    end: int
    tag: str


def parse_emotion_events(text: str) -> tuple[str, list[EmotionEvent]]:
    """解析情绪标记，返回 (纯文本, 事件列表)。

    * 区间基于**原始文本**下标，便于上游做对齐/字幕；
    * 只识别 ``KNOWN_TAGS`` 里的标签，其它方括号内容原样保留（避免误伤 ``[注]`` 这类标注）；
    * 纯文本里已剔除被识别的标记，可直接送 TTS。
    """
    events: list[EmotionEvent] = []
    out: list[str] = []
    cursor = 0
    for m in _TAG_RE.finditer(text):
        tag = m.group("tag")
        if tag not in KNOWN_TAGS:
            continue
        out.append(text[cursor:m.start()])
        events.append(EmotionEvent(start=m.start(), end=m.end(), tag=tag))
        cursor = m.end()
    out.append(text[cursor:])
    return "".join(out), events


class BreezeTTSAgent:
    """与 TTSApiAgent 同构的最小封装（本单不实现真实合成）。"""

    name = "breeze_tts"
    display_name = "Breeze TTS 2"

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.environ.get(MODEL_DIR_ENV)

    # ---- 与 TTSApiAgent 对齐的四个方法 ----
    def health(self) -> dict:
        return {
            "ok": bool(self.model_dir) and os.path.isdir(self.model_dir or ""),
            "engine": self.name,
            "model_dir_env": MODEL_DIR_ENV,
            "model_dir": self.model_dir,
        }

    def list_voices(self) -> list[dict]:
        # 本单不解析真实音色表：返回空列表而非伪造
        return []

    def synthesize(self, text: str, voice_id: str | None = None, speed: float = 1.0) -> bytes:
        """合成本单**未实现**：只做参数校验与权重存在性检查。

        Raises:
            RuntimeError: 权重目录未配置或不存在（可读提示，不带裸 traceback）。
            ValueError: 纯文本为空。
        """
        pure, _events = parse_emotion_events(text or "")
        if not pure.strip():
            raise ValueError("text 为空（或只含情绪标记）")
        if not self.model_dir:
            raise RuntimeError(
                f"未配置 Breeze TTS 权重：请设置环境变量 {MODEL_DIR_ENV} 指向模型目录"
            )
        if not os.path.isdir(self.model_dir):
            raise RuntimeError(f"权重目录不存在：{self.model_dir}")
        raise RuntimeError(
            "本单只做封装占位，不含推理实现：权重就绪后由二期接入 "
            "breeze-tts 的推理入口（不在此处下载权重）"
        )


def get_agent() -> BreezeTTSAgent:
    return BreezeTTSAgent()
