"""index_cards enrichment — LLM 索引卡增强（授粉自 caura enrichment 模式）。

授粉源：caura core-storage-api（Apache-2.0）的 enrichment worker——写入时 LLM
异步推断 memory_type/title/summary/tags/status/weight，快速路径先落库、
enrichment 后台补齐（embedding_pending/enrichment_pending 标记）。

落地：作为 index_cards.build_card 的 summarizer 替换点（P2）。
  - 同步接口 llm_summarizer(turns) -> (summary, keywords)：给 build_card 直接注入
  - 异步接口 enrich_card(card_id, turns)：落库后后台增强 memory_type/title/tags/weight
  - JSON 契约：{"title", "summary", "keywords": [...], "memory_type", "tags": [...], "weight"}
  - 失败降级：LLM 不可用/超时/JSON 解析失败 → 回退启发式，绝不抛异常
  - 遵守项目铁律：不传 temperature；tier 用 'summary'；模型来自 aget_model_api_config

License: Apache-2.0（机制同源 caura；实现独立）。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.llm_client import create_chat_llm_async  # noqa: E402  # NEKO 包路径

from .store import IndexCardStore, heuristic_summary

logger = logging.getLogger(__name__)

# 记忆类型枚举（对齐 NEKO 事实类型 + caura memory_type 语义）
MEMORY_TYPES = (
    "fact", "preference", "event", "relationship",
    "skill", "decision", "project", "emotion",
)

_JSON_PROMPT = """你是记忆索引卡生成器。根据会话片段生成结构化记忆卡。

要求：
- title：一句话主题（≤30字）
- summary：≤100字中文摘要
- keywords：3-6个关键词（中文词或技术名词）
- memory_type：从 {types} 选一个最贴切的
- tags：1-4个标签
- weight：0.0-1.0 重要度（事实/决策偏高，闲聊偏低）

只输出 JSON，不要解释，不要 markdown 代码块。

会话片段：
{transcript}
"""


def _format_turns(turns: List[Dict[str, Any]], max_chars: int = 1500) -> str:
    """把 turns 压成 LLM 可读文本（截断防超长）。"""
    parts = []
    budget = max_chars
    for t in turns:
        role = t.get("role", "user")
        content = (t.get("content") or "").strip()
        if not content:
            continue
        line = f"[{role}] {content}"
        if len(line) > budget:
            parts.append(line[:budget])
            break
        parts.append(line)
        budget -= len(line)
    return "\n".join(parts)


def _parse_json_response(raw: str) -> Optional[Dict[str, Any]]:
    """宽容解析：剥 code fence / 截断 JSON 尾部。"""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 截断修复：找到最后一个完整 JSON 对象
        for end in range(len(raw), 0, -1):
            if raw[end - 1] == "}":
                try:
                    return json.loads(raw[:end])
                except json.JSONDecodeError:
                    continue
        return None


def _validate(data: Dict[str, Any]) -> Dict[str, Any]:
    """校验/规范化 LLM 输出字段。"""
    summary = str(data.get("summary") or "").strip()[:300]
    keywords = data.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if str(k).strip()][:6]
    title = str(data.get("title") or "").strip()[:50]
    mtype = str(data.get("memory_type") or "fact").strip().lower()
    if mtype not in MEMORY_TYPES:
        mtype = "fact"
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()][:4]
    try:
        weight = float(data.get("weight", 0.5))
    except (TypeError, ValueError):
        weight = 0.5
    weight = max(0.0, min(1.0, weight))
    return {
        "title": title or keywords[0] if keywords else "会话",
        "summary": summary,
        "keywords": keywords,
        "memory_type": mtype,
        "tags": tags,
        "weight": weight,
    }


async def llm_enrich(
    turns: List[Dict[str, Any]],
    config_manager=None,
    tier: str = "summary",
) -> Optional[Dict[str, Any]]:
    """LLM 生成索引卡增强数据。失败返回 None（调用方降级启发式）。

    config_manager 需提供 aget_model_api_config(tier) -> {model, base_url, api_key}。
    """
    transcript = _format_turns(turns)
    if not transcript.strip():
        return None
    try:
        if config_manager is None:
            logger.warning("llm_enrich: 未提供 config_manager，降级启发式")
            return None
        api_config = await config_manager.aget_model_api_config(tier)
        if not api_config.get("model"):
            logger.warning("llm_enrich: tier=%s 未配置模型，降级启发式", tier)
            return None
        llm = await create_chat_llm_async(
            api_config["model"],
            api_config["base_url"],
            api_config["api_key"],
            timeout=30,
            max_retries=1,
            max_completion_tokens=400,
            extra_body=None,
            provider_type=api_config.get("provider_type"),
        )
        try:
            resp = await llm.ainvoke(_JSON_PROMPT.format(
                types="/".join(MEMORY_TYPES),
                transcript=transcript,
            ))
        finally:
            await llm.aclose()
        parsed = _parse_json_response(resp.content if hasattr(resp, "content") else str(resp))
        if parsed is None:
            logger.warning("llm_enrich: JSON 解析失败，降级启发式")
            return None
        return _validate(parsed)
    except Exception as exc:  # noqa: BLE001 - 任何失败降级启发式
        logger.warning("llm_enrich: 调用失败 (%s: %s)，降级启发式", type(exc).__name__, exc)
        return None


def llm_summarizer(config_manager=None):
    """build_card 可注入的 summarizer 回调（同步包装，LLM 失败回退启发式）。

    用法：store.build_card(sid, turns, summarizer=llm_summarizer(cfg))
    """
    def _summarize(turns: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
        enriched = _run_sync(turns, config_manager)
        if enriched:
            return enriched["summary"], enriched["keywords"]
        return heuristic_summary(turns)
    return _summarize


def _run_sync(turns, config_manager) -> Optional[Dict[str, Any]]:
    """同步包装 async llm_enrich（给 build_card 的同步回调用）。"""
    try:
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(llm_enrich(turns, config_manager))
        finally:
            loop.close()
    except Exception:
        return None


async def enrich_card(
    card_id: int,
    turns: List[Dict[str, Any]],
    store: IndexCardStore,
    config_manager=None,
) -> bool:
    """落库后异步增强：写 memory_type/tags/weight 回 index_cards。

    对齐 caura enrichment_pending 模式：先快速落库（启发式），后台 LLM 补齐。
    返回 True=增强成功，False=降级（卡片保持启发式值，不失败）。
    """
    enriched = await llm_enrich(turns, config_manager)
    if not enriched:
        return False
    try:
        store.db.execute(
            "UPDATE index_cards SET memory_type=?, tags=?, weight=?, enriched_at=? WHERE id=?",
            (
                enriched["memory_type"],
                json.dumps(enriched["tags"], ensure_ascii=False),
                enriched["weight"],
                __import__("time").time(),
                card_id,
            ),
        )
        store.db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrich_card: 写回失败 %s", exc)
        return False
