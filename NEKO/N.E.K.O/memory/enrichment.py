"""memory enrichment — caura 式索引卡增强管线（F-02）。

授粉源：caura core-storage-api（Apache-2.0）enrichment worker——
原始记忆写入 → LLM 推断结构化字段 → 索引卡落库；LLM 不可用时
规则降级，**卡片必须仍然生成**（快速路径先落库，增强后补/降级补）。

分层（与 index_cards/enrich.py 的关系）：
  - index_cards/enrich.py：LLM 调用器（绑 NEKO config_manager + utils.llm_client）
  - 本模块：管线编排——EnrichmentService 抽象（LLM 实现 + 规则实现）、
    降级保证、落库、F-01 on_memory_write 钩子接线

契约：
  - enrich(turns) 永不抛错、永不返回 None：LLM 失败/未配置 → 规则降级
  - 输出六字段完整：title/summary/keywords/memory_type/tags/weight
    （weight∈[0,1]，memory_type ∈ index_cards.enrich.MEMORY_TYPES）
  - LLM 走现有 llm 服务：LLMEnrichmentService 包装 index_cards.enrich.llm_enrich
    （config_manager.aget_model_api_config → utils.llm_client.create_chat_llm_async），
    本模块不直接 new 客户端、不改 apiserver

License: Apache-2.0（机制同源 caura；实现独立）。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .hooks import MemoryHooks, get_memory_hooks
from .index_cards.enrich import MEMORY_TYPES, llm_enrich
from .index_cards.store import IndexCardStore, heuristic_summary

logger = logging.getLogger(__name__)

# 字段完整契约（管线输出必须六字段齐全）
ENRICHMENT_FIELDS: tuple[str, ...] = (
    "title", "summary", "keywords", "memory_type", "tags", "weight",
)

# 规则降级：memory_type 关键词模式（顺序敏感，先命中先得）
_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"偏好|喜欢|讨厌|习惯|总是|从来|prefer|like", "preference"),
    (r"决定|选型|方案定了|采用|decision|choose", "decision"),
    (r"项目|里程碑|排期|上线|project|milestone", "project"),
    (r"技能|会做|熟练|学会|skill", "skill"),
    (r"认识|同事|朋友|是.*的|relationship", "relationship"),
    (r"今天|昨天|上周|刚|时|on \d|at \d", "event"),
    (r"开心|难过|生气|焦虑|feel|情绪", "emotion"),
)
# 规则降级：类型基准权重（事实/决策高，情绪/闲聊低）
_TYPE_BASE_WEIGHT = {
    "fact": 0.7, "decision": 0.75, "preference": 0.6, "project": 0.65,
    "skill": 0.6, "relationship": 0.55, "event": 0.5, "emotion": 0.4,
}


@runtime_checkable
class EnrichmentService(Protocol):
    """LLM 增强服务抽象：turns → 结构化字段 dict；失败返回 None（由管线降级）。"""

    async def enrich(self, turns: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]: ...


class LLMEnrichmentService:
    """LLM 实现：包装 index_cards.enrich.llm_enrich（现有 llm 服务链路）。"""

    def __init__(self, config_manager: Any = None, tier: str = "summary"):
        self._config_manager = config_manager
        self._tier = tier

    async def enrich(self, turns: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return await llm_enrich(turns, self._config_manager, tier=self._tier)


class RuleBasedEnrichmentService:
    """规则实现：零依赖降级路径——启发式摘要 + 模式规则推断字段，永不失败。"""

    async def enrich(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        return rule_enrich(turns)


def rule_enrich(turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """规则降级增强（同步纯函数，无 IO 无 LLM）。"""
    summary, keywords = heuristic_summary(turns)
    text = " ".join(t.get("content", "") for t in turns)
    memory_type = "fact"
    for pattern, mtype in _TYPE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            memory_type = mtype
            break
    weight = _TYPE_BASE_WEIGHT.get(memory_type, 0.5)
    # 内容长度因子：信息量大（>120 字）+0.05，极短（<15 字，闲聊级）-0.1
    if len(text) > 120:
        weight += 0.05
    elif len(text) < 15:
        weight -= 0.10
    weight = round(max(0.0, min(1.0, weight)), 3)
    title = (keywords[0] if keywords else (text[:20] or "记忆"))
    tags = keywords[:2] + [memory_type]
    return {
        "title": title[:50],
        "summary": summary,
        "keywords": keywords,
        "memory_type": memory_type,
        "tags": tags[:4],
        "weight": weight,
    }


def _record_to_turns(record: Optional[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """record 归一为 (session_id, turns)。无有效内容返回空 turns。"""
    rec = record or {}
    session_id = str(rec.get("session_id") or "adhoc")
    turns = rec.get("turns")
    if turns:
        return session_id, list(turns)
    content = str(rec.get("content") or "").strip()
    if not content:
        return session_id, []
    return session_id, [{"role": "user", "content": content}]


class EnrichmentPipeline:
    """增强管线：LLM 优先 → 规则降级（必出结果）→ 索引卡落库。

    llm_service=None（未配置 LLM）时直接规则降级——索引卡仍生成。
    """

    def __init__(self, llm_service: Optional[EnrichmentService] = None):
        self._llm = llm_service
        self._fallback = RuleBasedEnrichmentService()
        self.stats = {"llm_hits": 0, "rule_fallbacks": 0, "cards_written": 0}

    def enrich(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """增强 turns → 六字段 dict。LLM 失败/未配置 → 规则降级；永不抛错。"""
        if self._llm is not None:
            try:
                enriched = _run_async(self._llm.enrich(turns))
            except Exception as exc:  # noqa: BLE001 — LLM 崩了走降级
                logger.warning("[enrichment] LLM 服务异常 (%s)，规则降级", exc)
                enriched = None
            if enriched is not None:
                self.stats["llm_hits"] += 1
                return _ensure_complete(enriched)
            # llm_enrich 内部失败也返回 None → 降级
        self.stats["rule_fallbacks"] += 1
        return _run_async(self._fallback.enrich(turns))

    def enrich_and_store(
        self,
        record: Optional[Dict[str, Any]],
        store: IndexCardStore,
    ) -> Optional[int]:
        """管线主入口：record（turns 或 content）→ 增强 → 建卡 + 增强字段写回。

        返回 card_id；record 无有效内容返回 None；任何失败不抛错（卡片可缺，主路径不断）。
        """
        session_id, turns = _record_to_turns(record)
        if not turns:
            return None
        try:
            fields = self.enrich(turns)

            def _summarizer(ts: List[Dict[str, Any]]):
                return fields["summary"], fields["keywords"]

            card_id = int(store.build_card(session_id, turns, summarizer=_summarizer))
            # 增强字段写回（build_card 只建基础列，topic 取的是 keywords[0]，
            # title/memory_type/tags/weight 均需后补写回）
            import json as _json
            import time as _time
            store.db.execute(
                "UPDATE index_cards SET topic=?, memory_type=?, tags=?, weight=?, enriched_at=? WHERE id=?",
                (
                    fields["title"],
                    fields["memory_type"],
                    _json.dumps(fields["tags"], ensure_ascii=False),
                    fields["weight"],
                    _time.time(),
                    card_id,
                ),
            )
            store.db.commit()
            self.stats["cards_written"] += 1
            return card_id
        except Exception as exc:  # noqa: BLE001 — 落库失败不传染写路径
            logger.warning("[enrichment] 索引卡落库失败: %s", exc)
            return None


def _ensure_complete(fields: Dict[str, Any]) -> Dict[str, Any]:
    """兜底补齐六字段（LLM 输出经 index_cards.enrich._validate 后仍可能缺 title 等）。"""
    out = dict(fields)
    keywords = out.get("keywords") or []
    out.setdefault("title", (keywords[0] if keywords else "记忆"))
    out.setdefault("summary", "")
    out.setdefault("keywords", [])
    mt = out.get("memory_type") or "fact"
    out["memory_type"] = mt if mt in MEMORY_TYPES else "fact"
    out.setdefault("tags", [])
    try:
        w = float(out.get("weight", 0.5))
    except (TypeError, ValueError):
        w = 0.5
    out["weight"] = max(0.0, min(1.0, w))
    return out


def _run_async(coro):
    """同步跑 async（独立事件循环，NEKO 主循环外安全）。"""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------- F-01 钩子接线
def install_on_write_enrichment(
    hooks: Optional[MemoryHooks] = None,
    store: Optional[IndexCardStore] = None,
    llm_service: Optional[EnrichmentService] = None,
) -> str:
    """把增强管线挂上 F-01 的 on_memory_write 钩子（幂等：同名先卸再装）。

    handler 行为 = EnrichmentPipeline.enrich_and_store：LLM 优先、规则降级必建卡。
    受 NEKO_MEMORY_HOOKS 总开关控制（默认关闭 → emit 短路，现行为不变）。
    返回登记名。
    """
    h = hooks or get_memory_hooks()
    pipeline = EnrichmentPipeline(llm_service=llm_service)
    _state: Dict[str, Any] = {"store": store}

    def _on_memory_write(record: Optional[Dict[str, Any]] = None, **_: Any) -> Optional[int]:
        if _state["store"] is None:
            _state["store"] = IndexCardStore(":memory:")
        return pipeline.enrich_and_store(record, _state["store"])

    h.unregister("on_memory_write", "enrichment_pipeline")
    h.register("on_memory_write", _on_memory_write, name="enrichment_pipeline")
    return "on_memory_write/enrichment_pipeline"


__all__ = [
    "ENRICHMENT_FIELDS",
    "EnrichmentService",
    "LLMEnrichmentService",
    "RuleBasedEnrichmentService",
    "EnrichmentPipeline",
    "rule_enrich",
    "install_on_write_enrichment",
]
