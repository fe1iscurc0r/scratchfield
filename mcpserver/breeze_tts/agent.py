"""breeze-tts 引擎封装（与 `mcpserver/tts_api/agent.py` 同构）。

设计约束（工单 263 §1-D）：
* 本单**不下载权重**；权重目录走环境变量 ``BREEZE_TTS_MODEL_DIR``，缺失时抛可读 RuntimeError。
* 情绪标记（``[笑]`` / ``[叹气]`` / ``[咳嗽]``）由 ``parse_emotion_events`` 独立解析并从纯文本剔除。
* ``name`` / ``display_name`` / ``synthesize`` / ``list_voices`` / ``health`` 五个成员与现有
  `TTSApiAgent` 保持一致，便于上层按同一形态调用（**不自造 registry**）。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

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

    # ---- MCP 交接入口 ----
    # ⚠️ 与 tts_api 同形：**必须有**，否则 mcp_registry.verify_entrypoint 判契约不完整，
    # 注册表会按目录名推导 mcpserver.<name>.<name>（breeze_tts 的实现在 agent.py，
    # 推导出来的模块名根本不存在）→ 整条内置能力清单都跟着红。
    def invoke(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """同步工具分发。不做推理；合成在本单只会返回可读错误。"""
        if tool_name == "breeze_health":
            return {"status": "ok", "data": self.health()}
        if tool_name == "breeze_list_voices":
            return {"status": "ok", "data": self.list_voices()}
        if tool_name == "breeze_synthesize":
            audio = self.synthesize(
                str(params.get("text") or ""),
                params.get("voice_id"),
                float(params.get("speed") or 1.0),
            )
            # 本单到不了这里（synthesize 恒抛）；真接上推理后按 base64 回传，别塞原始字节
            return {"status": "ok",
                    "data": {"bytes": len(audio),
                             "encoding": "base64",
                             "audio": base64.b64encode(audio).decode("ascii")}}
        return {"status": "error",
                "message": f"未知工具 {tool_name}，可用: breeze_synthesize / breeze_list_voices / breeze_health"}

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 交接：只回 JSON 字符串，任何异常都转成可读 error（不抛裸 traceback）。"""
        try:
            tool_name = str((task or {}).get("tool_name") or "").strip()
            if not tool_name:
                return json.dumps(
                    {"status": "error", "message": "缺少 tool_name 参数", "data": {}},
                    ensure_ascii=False)
            params = {k: v for k, v in (task or {}).items()
                      if k not in ("service_name", "tool_name", "agentType")}
            result = self.invoke(tool_name, params)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001 —— 交接层必须兜住一切，不能把异常抛回调度器
            logger.error("[BreezeTTS] handle_handoff 异常: %s", e)
            return json.dumps(
                {"status": "error", "message": f"调用失败: {e}", "data": {}},
                ensure_ascii=False)


def get_agent() -> BreezeTTSAgent:
    return BreezeTTSAgent()
