"""判决书自动打标管线（卷164 · 法学管线二期）。

把卷163 入库的判例喂给 Von 决策模型，自动产出案由/程序/焦点等标签，
人工只复核低置信项。

喂料策略（关键）
----------------
Von 的 state 上限 4k tokens，判决书全文塞不下。因此**只用卷163 已抽取的
结构化字段**拼接喂料，而非整篇判决书：

1. **当事人段**（``parties``）
2. **案由**（``cause_of_action``）
3. **诉讼请求段**（在正文中定位「诉讼请求 / 诉称 / 请求判令」等段落）
4. **本院认为段**（裁判要旨，定位「本院认为 / 本院经审理认为」）

拼成 ``context`` 后按字符预算截断（默认 4000 token ≈ 6000 汉字，保守取 4000
汉字），超长**截断不炸**。

结果落库
--------
- ``papers.tags``：``案由:合同纠纷|程序:二审`` 键值对格式（零 schema 改动）
- ``papers.tag_confidence``：JSON（question → {value, confidence, source}）
- **低置信（choice 类 <0.6）不入库**，进 ``_queue/`` 待人工复核
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 本包目录（domains/law/）。
PACK_DIR = Path(__file__).resolve().parent.parent

#: 待复核队列目录（与卷163 复用同一队列）。
QUEUE_DIR = PACK_DIR / "_queue"

#: 喂料字符预算（≈4000 tokens，保守取 4000 汉字；超长截断）。
MAX_CONTEXT_CHARS = 4000

#: 低置信阈值：choice 类低于此值的标签不入库，进队列待人工复核。
LOW_CONFIDENCE_THRESHOLD = 0.6

#: 人工确认后的置信度标记。
HUMAN_CONFIRMED_CONFIDENCE = 1.0
HUMAN_CONFIRMED_SOURCE = "人工"

#: 诉讼请求段定位。
CLAIM_ANCHORS = (
    "诉讼请求", "诉称", "请求判令", "起诉称", "原告请求", "上诉请求",
    "请求本院", "再审请求", "申请再审称",
)
#: 裁判要旨（本院认为）段定位。
HOLDING_ANCHORS = (
    "本院认为", "本院经审理认为", "本院查明", "经审理查明", "本院经审查认为",
)
#: 段落结束标志（遇到这些则停止采集该段）。
_SECTION_STOP = re.compile(
    r"^(?:依照|据此|综上|判决如下|裁定如下|特此|如不服|审判长|审判员|书记员|"
    r"本院认为|本院经审理认为|本院查明|经审理查明|本院经审查认为)"
)


@dataclass
class TagResult:
    """单个判例的打标结果。"""

    value: Any
    confidence: float = 0.0
    probs: dict[str, float] = field(default_factory=dict)
    source: str = "von"  # von | 人工
    accepted: bool = False
    """是否达到置信阈值、可入库。"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": round(float(self.confidence), 4),
            "probs": {k: round(float(v), 4) for k, v in (self.probs or {}).items()},
            "source": self.source,
            "accepted": self.accepted,
        }


@dataclass
class CaseTagging:
    """一个判例的全部标签。"""

    case_no: str
    tags: dict[str, TagResult] = field(default_factory=dict)
    low_confidence: dict[str, TagResult] = field(default_factory=dict)
    context_chars: int = 0
    truncated: bool = False

    def accepted_tags(self) -> dict[str, TagResult]:
        return {k: v for k, v in self.tags.items() if v.accepted}

    def tags_list(self) -> list[str]:
        """生成 ``papers.tags`` 的标签列表（``["案由:合同纠纷", "审理程序:二审"]``）。

        ``papers.tags`` 在存储层是 JSON 数组（``_JSON_ARRAY_FIELDS``），
        因此这里返回列表，而非 ``|`` 拼接串，避免破坏既有类型契约。
        布尔标签只在为 true 时写入（如 ``指导性案例:是``）。
        """
        parts: list[str] = []
        for key, res in self.tags.items():
            if not res.accepted:
                continue
            if isinstance(res.value, bool):
                if res.value:
                    parts.append(f"{key}:是")
                continue
            parts.append(f"{key}:{res.value}")
        return parts

    def tags_field(self) -> str | None:
        """兼容旧调用的 ``|`` 拼接形式（供展示/日志）。"""
        parts = self.tags_list()
        return "|".join(parts) or None

    def confidence_field(self) -> str:
        """生成 ``papers.tag_confidence`` 的 JSON 字符串。"""
        payload = {
            "questions": {k: v.to_dict() for k, v in self.tags.items()},
            "low_confidence": {k: v.to_dict() for k, v in self.low_confidence.items()},
            "threshold": LOW_CONFIDENCE_THRESHOLD,
            "context_chars": self.context_chars,
            "truncated": self.truncated,
            "tagged_at": datetime.now().isoformat(timespec="seconds"),
        }
        return json.dumps(payload, ensure_ascii=False)


# ===========================================================================
# 喂料构建
# ===========================================================================


def _extract_section(text: str, anchors: tuple[str, ...], max_chars: int) -> str:
    """在正文中定位以 ``anchors`` 之一起始的段落，采到段落结束标志为止。"""
    if not text:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(a) or a in stripped[:20] for a in anchors):
            buf: list[str] = []
            for j in range(i, min(i + 40, len(lines))):
                cur = lines[j].strip()
                if j > i and _SECTION_STOP.match(cur):
                    break
                buf.append(cur)
                if sum(len(x) for x in buf) >= max_chars:
                    break
            return "\n".join(buf)[:max_chars]
    return ""


def build_feed_context(
    *,
    parties: list[str] | None = None,
    cause_of_action: str = "",
    court: str = "",
    trial_level: str = "",
    content: str = "",
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, bool]:
    """拼接 Von 喂料上下文；返回 ``(context, truncated)``。

    组成：当事人段 + 案由 + 诉讼请求段 + 本院认为段。
    总量超 ``max_chars`` 时截断（**不抛异常**）。
    """
    chunks: list[str] = []

    if parties:
        chunks.append("【当事人】" + "；".join(parties))
    meta = []
    if cause_of_action:
        meta.append(f"案由：{cause_of_action}")
    if court:
        meta.append(f"法院：{court}")
    if trial_level:
        meta.append(f"程序：{trial_level}")
    if meta:
        chunks.append("【基本信息】" + " ".join(meta))

    claim = _extract_section(content, CLAIM_ANCHORS, max_chars // 2)
    if claim:
        chunks.append("【诉讼请求】" + claim)

    holding = _extract_section(content, HOLDING_ANCHORS, max_chars // 2)
    if holding:
        chunks.append("【本院认为】" + holding)

    # 兜底：以上皆空则取正文前 1/2（仍受总预算约束）
    if not claim and not holding and content:
        chunks.append(content[: max_chars // 2])

    context = "\n".join(chunks)
    truncated = len(context) > max_chars
    if truncated:
        context = context[:max_chars]
    return context, truncated


def questions_from_pack(pack: Any) -> dict[str, dict[str, Any]]:
    """把领域包的 ``tagging_questions`` 转成 Von 的 ``questions`` 结构。"""
    out: dict[str, dict[str, Any]] = {}
    for q in getattr(pack, "tagging_questions", []) or []:
        spec: dict[str, Any] = {"type": q.type}
        if q.options:
            spec["options"] = list(q.options)
        out[q.key] = spec
    return out


# ===========================================================================
# 打标执行
# ===========================================================================


def tag_case(
    *,
    parties: list[str] | None = None,
    cause_of_action: str = "",
    court: str = "",
    trial_level: str = "",
    content: str = "",
    case_no: str = "",
    questions: dict[str, dict[str, Any]] | None = None,
    client: Any = None,
) -> CaseTagging:
    """对单个判例打标（调用 Von）。

    :raises VonError: Von 调用失败（由调用方决定降级/入队）。
    """
    if questions is None:
        from apiserver.domain_pack import get_pack

        pack = get_pack("law")
        questions = questions_from_pack(pack)

    if client is None:
        from apiserver.von_client import get_von_client

        client = get_von_client()

    context, truncated = build_feed_context(
        parties=parties, cause_of_action=cause_of_action,
        court=court, trial_level=trial_level, content=content,
    )
    result = client.ask({"context": context}, questions)
    answers = result.get("answers") or {}

    tagging = CaseTagging(
        case_no=case_no, context_chars=len(context), truncated=truncated
    )
    for key, spec in questions.items():
        ans = answers.get(key)
        if not isinstance(ans, dict):
            continue
        value = ans.get("value")
        try:
            confidence = float(ans.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        probs_raw = ans.get("probs")
        probs = probs_raw if isinstance(probs_raw, dict) else {}

        qtype = spec.get("type")
        # 低置信判定：choice 类 < 阈值；boolean/score 不参与（boolean 无中间态）
        accepted = True
        if qtype == "choice":
            accepted = confidence >= LOW_CONFIDENCE_THRESHOLD
            # 值不在选项内 → 拒绝
            if value not in (spec.get("options") or []):
                accepted = False

        res = TagResult(
            value=value, confidence=confidence, probs=probs,
            source="von", accepted=accepted,
        )
        tagging.tags[key] = res
        if not accepted:
            tagging.low_confidence[key] = res
    return tagging


# ===========================================================================
# 低置信入队（复用卷163 队列机制）
# ===========================================================================


def enqueue_low_confidence(tagging: CaseTagging, filename: str = "") -> Path | None:
    """把低置信标签对应的判例写入待人工复核队列。"""
    if not tagging.low_confidence:
        return None
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe = re.sub(r'[\\/:*?"<>|\r\n]+', "_", filename or tagging.case_no or "case").strip(" .")
    base = f"{stamp}__tag__{safe or 'case'}"
    meta = {
        "case_no": tagging.case_no,
        "filename": filename,
        "enqueued_at": datetime.now().isoformat(timespec="seconds"),
        "reason": "低置信标签待人工复核",
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "low_confidence": {k: v.to_dict() for k, v in tagging.low_confidence.items()},
        "all_tags": {k: v.to_dict() for k, v in tagging.tags.items()},
    }
    path = QUEUE_DIR / f"{base}.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "[tagging] 低置信入队: %s (%s)",
        tagging.case_no, ", ".join(tagging.low_confidence),
    )
    return path


def list_low_confidence_queue() -> list[dict[str, Any]]:
    """列出待人工复核的标签项。"""
    if not QUEUE_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(QUEUE_DIR.glob("*__tag__*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            logger.warning("[tagging] 复核队列元数据损坏: %s (%s)", p.name, e)
    return out


# ===========================================================================
# 人工复核
# ===========================================================================


def human_confirm(
    tags_json: str | None,
    question: str,
    value: Any,
) -> str:
    """人工确认/改选某个标签：置信度改记 ``1.0(人工)``，返回更新后的 JSON。"""
    payload: dict[str, Any] = {}
    if tags_json:
        try:
            payload = json.loads(tags_json)
        except (TypeError, ValueError):
            payload = {}
    questions = payload.setdefault("questions", {})
    q = questions.setdefault(question, {})
    q["value"] = value
    q["confidence"] = HUMAN_CONFIRMED_CONFIDENCE
    q["source"] = HUMAN_CONFIRMED_SOURCE
    q["accepted"] = True
    # 从低置信集合移除
    low = payload.get("low_confidence")
    if isinstance(low, dict):
        low.pop(question, None)
    return json.dumps(payload, ensure_ascii=False)
