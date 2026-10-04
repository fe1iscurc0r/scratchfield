"""观察捕获层 — 内容哈希去重（03-01，claude-mem 授粉 #2691 前置）。

借鉴点：claude-mem 的 observation 内容哈希幂等——同一次观察（同一会话内同
title+narrative）不因重试 / 重放而重复入库。实现：
- compute_observation_content_hash(memory_session_id, title, narrative)：
  sha256（字段以 \x1f 单元分隔符连接，各字段先 strip），取前 16 位 hex；
- capture_observation(...)：写前校验顺序 = 来源分级（guard.pre_write_check）
  → 哈希去重（find_by_observation_hash / store.add 幂等）→ 入库。

不依赖 Claude SDK/Anthropic；纯标准库 hashlib/sqlite3。
"""
from __future__ import annotations

import hashlib
from typing import Any, Sequence

from mcpserver.memory_maas import guard
from mcpserver.memory_maas.entities import TypedMemoryStore

# 字段连接分隔符（单元分隔符，避免 "ab"+"c" 与 "a"+"bc" 拼接歧义）
_HASH_SEP = "\x1f"


def compute_observation_content_hash(memory_session_id: str, title: str,
                                     narrative: str) -> str:
    """观察内容哈希：sha256(session_id \x1f title \x1f narrative)[:16] hex。

    各字段先 strip（前后空白不参与哈希）；字段位置由分隔符固定，
    杜绝拼接歧义。返回 16 位 hex 字符串。
    """
    payload = _HASH_SEP.join(
        str(p or "").strip() for p in
        (memory_session_id, title, narrative))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# 工单签名别名（claude-mem 授粉报告用驼峰记法）
computeObservationContentHash = compute_observation_content_hash


def capture_observation(store: TypedMemoryStore,
                        memory_session_id: str, title: str,
                        narrative: str, *, type: str = "note",
                        tags: Sequence[str] | None = None,
                        pinned: bool = False,
                        source_rank: int = guard.SOURCE_USER,
                        created_at: float | None = None,
                        platform: str = "local") -> dict[str, Any]:
    """观察入库（幂等）：来源分级 → 哈希去重 → 入库（03-04 平台写时打标）。

    - 来源分级：先过 guard.pre_write_check（注入触发词/超长/低信任隔离），
      blocked 直接抛 MemoryMaasCaptureError（fail-fast，不入库）；
    - 哈希去重：同 (session_id, title, narrative) 已存在 → 返回已有 id，
      deduped=True，不重复入库不抛错；
    - 入库：content = title + "\\n" + narrative，observation_hash 落列；
      platform（weixin/qqbot/cli/local，别名 qq/wechat/wx 归一）写时打标。

    返回 {ok, id, observation_hash, deduped, guard, entity}。
    """
    title_s = str(title or "").strip()
    narrative_s = str(narrative or "").strip()
    if not title_s and not narrative_s:
        raise MemoryMaasCaptureError("title 与 narrative 不能同时为空")
    composed = "\n".join(x for x in (title_s, narrative_s) if x)
    # ① 来源分级（注入防护写前校验，与 guard.py 协同）
    decision = guard.pre_write_check(composed, source_rank=source_rank)
    if decision.blocked:
        raise MemoryMaasCaptureError(f"写前校验拦截: {decision.reason}")
    # ② 哈希去重 → ③ 入库（store.add 内部同哈希幂等返回已有 id）
    obs_hash = compute_observation_content_hash(
        memory_session_id, title_s, narrative_s)
    existing = store.find_by_observation_hash(obs_hash)
    deduped = existing is not None
    if deduped:
        eid = existing["id"]
    else:
        eid = store.add(
            composed, type=type, tags=tags, pinned=pinned,
            source_rank=decision.source_rank, isolation=decision.isolation,
            created_at=created_at, observation_hash=obs_hash,
            platform=platform)
    entity = store.get(eid)
    return {"ok": True, "id": eid, "observation_hash": obs_hash,
            "deduped": deduped, "guard": decision.to_dict(),
            "entity": entity}


class MemoryMaasCaptureError(RuntimeError):
    """捕获层错误（fail-fast：内容全空 / 写前校验拦截）。"""


__all__ = [
    "MemoryMaasCaptureError",
    "capture_observation",
    "computeObservationContentHash",
    "compute_observation_content_hash",
]
