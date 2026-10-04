"""注入防护层 — 记忆写时校验 + 来源分级 + 流策略。

设计依据三篇论文授粉点（weekly_pollination 8-26 轮）：
- InjecMEM（2608.23471）：一次交互定向污染记忆检索输出 → 写前校验 + 隔离区
- SkillBloat（2608.21929）：技能文件 token 放大攻击 → 内容长度上限
- AgentFlow（2608.22868）：流策略语言把注入妥协率 33%→0% → 实体→工具白名单

触发词只用基础模式（不引 LLM 判断，防误伤优先）；低信任（source_rank≥2）条目进隔离区，
默认不参与检索，可查可审可 promote 升级。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcpserver.memory_maas.entities import (
    EntityValidationError,
    TypedMemoryStore,
)

# source_rank 分级：0=用户显式 / 1=agent 自产 / 2=外部导入 / 3=未验证
SOURCE_USER = 0
SOURCE_AGENT = 1
SOURCE_IMPORTED = 2
SOURCE_UNVERIFIED = 3
LOW_TRUST_THRESHOLD = 2

SOURCE_LABELS: dict[int, str] = {
    SOURCE_USER: "用户显式",
    SOURCE_AGENT: "agent 自产",
    SOURCE_IMPORTED: "外部导入",
    SOURCE_UNVERIFIED: "未验证",
}

MAX_CONTENT_LEN = 20000

# 基础注入触发词（大小写不敏感子串匹配；防误伤优先，不引 LLM 判断）
INJECTION_TRIGGERS: tuple[str, ...] = (
    "忽略之前指令",
    "忽略之前的指令",
    "忽略以上指令",
    "你现在的角色是",
    "你现在的身份是",
    "现在你是",
    "重新定义你的角色",
    "以上内容无效",
    "忘记之前的",
    "作为大语言模型",
    "ignore previous instructions",
    "ignore all previous",
    "disregard prior instructions",
    "you are now",
    "system prompt",
    "jailbreak",
    "override your",
)

DEFAULT_POLICY_PATH = Path(__file__).with_name("tools_policy.json")


@dataclass
class GuardDecision:
    """写前校验结论：blocked=拒绝写入；isolation=低信任进隔离区。"""

    ok: bool
    blocked: bool
    isolation: bool
    source_rank: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "blocked": self.blocked,
                "isolation": self.isolation, "source_rank": self.source_rank,
                "reason": self.reason}


def classify_source(rank: int) -> str:
    return SOURCE_LABELS.get(int(rank), f"未知({rank})")


def pre_write_check(content: Any, source_rank: int = SOURCE_USER,
                    max_len: int = MAX_CONTENT_LEN) -> GuardDecision:
    """写前校验：类型 / 长度上限 / 注入触发词 / 来源分级。"""
    if not isinstance(content, str):
        return GuardDecision(ok=False, blocked=True, isolation=False,
                             source_rank=int(source_rank),
                             reason="content 必须是字符串")
    if len(content) > max_len:
        return GuardDecision(ok=False, blocked=True, isolation=False,
                             source_rank=int(source_rank),
                             reason=f"内容超长（>{max_len} 字符）")
    lowered = content.lower()
    for trig in INJECTION_TRIGGERS:
        if trig.lower() in lowered:
            return GuardDecision(ok=False, blocked=True, isolation=True,
                                 source_rank=int(source_rank),
                                 reason=f"命中注入触发词: {trig!r}")
    isolation = int(source_rank) >= LOW_TRUST_THRESHOLD
    return GuardDecision(ok=True, blocked=False, isolation=isolation,
                         source_rank=int(source_rank),
                         reason="低信任来源，进入隔离区" if isolation else "")


def promote(store: TypedMemoryStore, entity_id: str) -> dict[str, Any]:
    """隔离条目升级：source_rank 回到 agent 自产（1），解除隔离。"""
    entity = store.get(entity_id)
    if entity is None:
        raise EntityValidationError(f"实体不存在: {entity_id!r}")
    store.update(entity_id, source_rank=SOURCE_AGENT, isolation=False)
    return {"ok": True, "id": entity_id, "entity": store.get(entity_id)}


def list_isolated(store: TypedMemoryStore) -> list[dict[str, Any]]:
    """列出隔离区条目（source_rank≥2），供审查。"""
    return store.list_entities(source_rank_min=LOW_TRUST_THRESHOLD)


class FlowPolicy:
    """流策略：实体类型 → 可流向的工具白名单（参照 AgentFlow，可热加载）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_POLICY_PATH
        self._policy: dict[str, Any] = {}
        self._mtime_ns: int | None = None
        self.reload()

    def reload(self) -> None:
        self._policy = {}
        self._mtime_ns = None
        if self.path.is_file():
            self._policy = json.loads(self.path.read_text(encoding="utf-8"))
            self._mtime_ns = self.path.stat().st_mtime_ns

    def _maybe_reload(self) -> None:
        if self.path.is_file():
            mtime = self.path.stat().st_mtime_ns
            if mtime != self._mtime_ns:
                self.reload()

    def allow(self, entity_type: str, tool: str) -> bool:
        """entity_type 的实体能否流向 tool。deny 优先；无该类型规则走 default_tools。"""
        self._maybe_reload()
        rules = self._policy.get("entities", {}).get(entity_type)
        if rules:
            if tool in rules.get("deny", []):
                return False
            allow = rules.get("allow")
            if allow is None:
                return True
            return tool in allow
        return tool in self._policy.get("default_tools", [])

    def check(self, entity_type: str, tool: str) -> dict[str, Any]:
        allowed = self.allow(entity_type, tool)
        return {"ok": allowed, "entity_type": entity_type, "tool": tool,
                "allowed": allowed,
                "reason": "" if allowed else
                f"{entity_type} 不允许流向 {tool}"}
