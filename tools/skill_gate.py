# skill_gate.py — superpowers 方法论落地
# 渐进式披露 + 硬门控(HARD-GATE) + 1%规则强制触发
# 参考: obra/superpowers (MIT, AGENTS.md L95 + brainstorming/SKILL.md L13-17 + using-superpowers/SKILL.md L12-18)

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

# ─────────────────────────── 内部数据类型 ────────────────────────────

class GateDecision(Enum):
    """硬门控审批结果。"""
    PENDING = auto()   # 未批准，待审
    APPROVED = auto()  # 已批准，可执行
    DENIED = auto()    # 已拒绝，禁止执行


class SkillCategory(Enum):
    """技能层级（对齐 superpowers 三层结构）。"""
    BOOTSTRAP = auto()   # 启动层：会话开始即加载
    FLOW = auto()        # 流程层：brainstorming/planning/executing/verification/finishing
    ENGINEERING = auto() # 工程层：单点技能 test-driven-debugging/code-review 等


@dataclass
class SkillFrontmatter:
    """
    Skill frontmatter — 渐进式披露的触发入口。

    description 字段是唯一触发入口：当 description 中出现
    场景关键词时，技能正文才按需展开。
    """
    name: str
    category: SkillCategory
    description: str          # 触发词列表/触发规则，逗号分隔
    trigger_keywords: list[str] = field(default_factory=list)  # 从 description 解析
    hard_gate: bool = False   # 是否需要先说明意图并获批准
    one_percent_rule: bool = False  # 是否启用 1% 规则强制触发
    source_ref: str = ""      # 参考来源，标注引用边界
    version: str = "1.0"

    def __post_init__(self):
        # 从 description 自动解析触发关键词
        # 格式1: "use when X, Y, Z" → 剥离前缀，分割关键词
        # 格式2: "X, Y, Z" 或 "X/Y/Z" → 直接分割
        if not self.description:
            self.trigger_keywords = []
            return

        desc = self.description.strip()
        # 格式1: "use when ..." — 剥离前缀后按逗号分割
        if desc.lower().startswith("use when"):
            inner = desc[len("use when"):].strip()  # "bug, error, crash" 或 "writing new code, before implementation"
            self.trigger_keywords = [
                kw.strip().lower()
                for kw in inner.split(",")
                if kw.strip()
            ]
        else:
            # 格式2: 直接分割
            self.trigger_keywords = [
                kw.strip().lower()
                for kw in re.split(r"[,;/|]", desc)
                if kw.strip()
            ]


@dataclass
class GateContext:
    """硬门控上下文——记录「先说明意图、等批准」这一仪式。"""
    task_id: str
    intent: str               # 意图描述（brainstorming 时由工具填写）
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    decision: GateDecision = GateDecision.PENDING
    approver: str = "human"   # human / auto / system


@dataclass
class SkillTriggerResult:
    """1% 规则判断结果。"""
    skill_name: str
    matched: bool
    confidence: float         # 0.0–1.0，触发置信度
    matched_keywords: list[str] = field(default_factory=list)
    gate_required: bool = False
    gate_context: GateContext | None = None


# ─────────────────────────── 核心类 ────────────────────────────

class SkillGate:
    """
    superpowers 方法论 gate keeper。

    三大机制：
    1. 渐进式披露：frontmatter.description 触发 → 正文按需展开
    2. 硬门控(HARD-GATE)：关键流程 skill 前置「先说明意图、经批准再动手」
    3. 强制触发(1% 规则)：工具函数判断某场景是否应调用某 skill
    """

    def __init__(self):
        # 注册的 skill frontmatter 清单
        self._registry: dict[str, SkillFrontmatter] = {}
        # 硬门控挂起的任务（task_id → GateContext）
        self._pending_gates: dict[str, GateContext] = {}
        # skill 正文缓存（按需加载）
        self._body_cache: dict[str, str] = {}

    # ── 注册 ──────────────────────────────────────────────────────────

    def register(self, frontmatter: SkillFrontmatter) -> None:
        """向 gate 注册一个 skill。"""
        self._registry[frontmatter.name] = frontmatter

    def register_from_dict(self, data: dict) -> None:
        """从字典（对应一个 SKILL.md frontmatter）注册 skill。"""
        cat_str = data.get("category", "ENGINEERING").upper()
        # 兼容 category: "flow" → "FLOW"
        if cat_str not in SkillCategory.__members__:
            cat_str = "ENGINEERING"
        fm = SkillFrontmatter(
            name=data["name"],
            category=SkillCategory[cat_str],
            description=data.get("description", ""),
            trigger_keywords=data.get("trigger_keywords", []),
            hard_gate=data.get("hard_gate", False),
            one_percent_rule=data.get("one_percent_rule", False),
            source_ref=data.get("source_ref", ""),
            version=data.get("version", "1.0"),
        )
        self.register(fm)

    # ── 渐进式披露 ────────────────────────────────────────────────────

    def should_expand(self, skill_name: str, scene_text: str) -> bool:
        """
        判断某场景 scene_text 是否应触发 skill_name 的正文展开。
        基于 frontmatter.description 中的关键词做匹配。
        """
        if skill_name not in self._registry:
            return False
        fm = self._registry[skill_name]
        if not fm.trigger_keywords:
            return False
        text_lower = scene_text.lower()
        # 任意一个关键词命中即展开
        return any(kw in text_lower for kw in fm.trigger_keywords)

    def expand_skill(self, skill_name: str, scene_text: str) -> str | None:
        """
        若 should_expand 返回 True，返回 skill 正文（从缓存或按需加载）。
        未触发则返回 None。
        """
        if not self.should_expand(skill_name, scene_text):
            return None
        if skill_name in self._body_cache:
            return self._body_cache[skill_name]
        # 占位：实际从 skills/ 目录加载正文
        return self._body_cache.get(skill_name)

    def load_skill_body(self, skill_name: str, body: str) -> None:
        """手动加载 skill 正文到缓存（按需展开时调用）。"""
        self._body_cache[skill_name] = body

    # ── 硬门控(HARD-GATE) ─────────────────────────────────────────────

    def check_gate(self, task_id: str, skill_name: str) -> GateDecision:
        """
        检查 task_id 是否已通过 skill_name 要求的硬门控。
        若门未批，返回 PENDING；已批准返回 APPROVED；已拒绝返回 DENIED。
        """
        gate_key = f"{task_id}:{skill_name}"
        ctx = self._pending_gates.get(gate_key)
        if ctx is None:
            return GateDecision.APPROVED  # 无门控记录，直接放行
        return ctx.decision

    def request_gate(
        self,
        task_id: str,
        skill_name: str,
        intent: str,
        approver: str = "human",
    ) -> GateContext:
        """
        为 task_id + skill_name 发起硬门控申请，返回 GateContext。
        若同 key 已存在，返回既有上下文（不重复创建）。
        """
        gate_key = f"{task_id}:{skill_name}"
        if gate_key in self._pending_gates:
            return self._pending_gates[gate_key]

        if skill_name not in self._registry:
            # 未注册的 skill 不做门控
            raise ValueError(f"Skill '{skill_name}' not registered")

        fm = self._registry[skill_name]
        if not fm.hard_gate:
            raise ValueError(f"Skill '{skill_name}' does not require hard gate")

        ctx = GateContext(task_id=task_id, intent=intent, approver=approver)
        self._pending_gates[gate_key] = ctx
        return ctx

    def resolve_gate(
        self,
        task_id: str,
        skill_name: str,
        decision: GateDecision,
    ) -> GateContext:
        """
        审批门控：填写批准/拒绝结果。
        仅允许 PENDING 状态的 gate 被 resolve。
        """
        gate_key = f"{task_id}:{skill_name}"
        if gate_key not in self._pending_gates:
            raise ValueError(f"No pending gate for task={task_id}, skill={skill_name}")

        ctx = self._pending_gates[gate_key]
        if ctx.decision != GateDecision.PENDING:
            raise ValueError(f"Gate already resolved: {ctx.decision}")

        ctx.decision = decision
        ctx.decided_at = time.time()
        return ctx

    def gate_pending_count(self) -> int:
        """返回当前 PENDING 态门控数量（用于展示）。"""
        return sum(
            1 for ctx in self._pending_gates.values()
            if ctx.decision == GateDecision.PENDING
        )

    # ── 1% 规则强制触发 ───────────────────────────────────────────────

    def check_one_percent(
        self,
        scene_text: str,
        context: dict | None = None,
    ) -> list[SkillTriggerResult]:
        """
        1% 规则判断：对所有注册为 one_percent_rule=True 的 skill，
        检查 scene_text 是否命中。

        只要有 1% 可能适用就必须调用（消除「忘记用技能」）。
        返回所有命中的 SkillTriggerResult 列表。
        """
        results: list[SkillTriggerResult] = []
        text_lower = scene_text.lower()

        for name, fm in self._registry.items():
            if not fm.one_percent_rule:
                continue

            matched_kws = [kw for kw in fm.trigger_keywords if kw in text_lower]
            # 即使只命中一个触发词也视为匹配（1% 规则）
            matched = len(matched_kws) > 0
            confidence = len(matched_kws) / max(len(fm.trigger_keywords), 1)

            result = SkillTriggerResult(
                skill_name=name,
                matched=matched,
                confidence=confidence,
                matched_keywords=matched_kws,
                gate_required=fm.hard_gate,
            )

            # 若需要硬门控，创建 gate context
            if matched and fm.hard_gate and context:
                task_id = context.get("task_id", "unknown")
                intent = context.get("intent", scene_text[:120])
                try:
                    ctx = self.request_gate(task_id, name, intent)
                    result.gate_context = ctx
                except ValueError:
                    pass  # skill 未注册硬门控

            results.append(result)

        return results

    def should_invoke_skill(
        self,
        skill_name: str,
        scene_text: str,
        task_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        工具函数判断：给定场景是否应调用指定 skill。
        返回 (should_invoke, reason)。

        规则：
        - skill 未注册 → 不调用
        - skill 有 one_percent_rule 且关键词命中 → 必须调用
        - skill 硬门控未批准 → 暂不调用（返回原因含 PENDING）
        """
        if skill_name not in self._registry:
            return False, f"skill '{skill_name}' not registered"

        fm = self._registry[skill_name]

        # 先做硬门控检查
        if fm.hard_gate and task_id:
            decision = self.check_gate(task_id, skill_name)
            if decision == GateDecision.PENDING:
                return False, f"gate pending for task={task_id}"
            if decision == GateDecision.DENIED:
                return False, f"gate denied for task={task_id}"

        # 1% 规则
        if fm.one_percent_rule:
            text_lower = scene_text.lower()
            hit = any(kw in text_lower for kw in fm.trigger_keywords)
            if hit:
                return True, f"1% rule triggered (kw={[kw for kw in fm.trigger_keywords if kw in text_lower]})"
            return False, "1% rule: no keyword hit"

        # 通用渐进式披露
        if self.should_expand(skill_name, scene_text):
            return True, "progressive disclosure triggered"

        return False, "no trigger match"

    # ── 审计/哈希链接口（对接 buzz-audit 思路）────────────────────────

    def build_audit_hash(
        self,
        task_id: str,
        skill_name: str,
        intent: str,
        timestamp: float | None = None,
    ) -> str:
        """
        生成一条审计哈希（模拟事件日志条目）。
        实际场景中应链接到前一条哈希形成哈希链。
        """
        ts = timestamp or time.time()
        payload = f"{task_id}:{skill_name}:{intent}:{ts}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ── 工具函数 ──────────────────────────────────────────────────────

    def list_skills_by_category(self, cat: SkillCategory) -> list[str]:
        return [name for name, fm in self._registry.items() if fm.category == cat]

    def list_one_percent_skills(self) -> list[str]:
        return [name for name, fm in self._registry.items() if fm.one_percent_rule]

    def get_frontmatter(self, skill_name: str) -> SkillFrontmatter | None:
        return self._registry.get(skill_name)

    def all_registered(self) -> list[str]:
        return list(self._registry.keys())


# ─────────────────────────── 全局单例（便于工具函数直接调用）────────────────

_gate_instance: SkillGate | None = None


def get_gate() -> SkillGate:
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = SkillGate()
    return _gate_instance


def should_invoke_skill(
    skill_name: str,
    scene_text: str,
    task_id: str | None = None,
) -> tuple[bool, str]:
    """
    工具函数：判断某场景是否应调用某 skill。
    对应 superpowers 「1% 规则」强制触发机制。
    """
    return get_gate().should_invoke_skill(skill_name, scene_text, task_id)


def check_and_request_gate(
    task_id: str,
    skill_name: str,
    intent: str,
    approver: str = "human",
) -> GateContext:
    """工具函数：检查并申请硬门控。"""
    gate = get_gate()
    existing = gate.check_gate(task_id, skill_name)
    if existing != GateDecision.PENDING:
        return gate._pending_gates.get(f"{task_id}:{skill_name}")
    return gate.request_gate(task_id, skill_name, intent, approver)


def resolve_gate(
    task_id: str,
    skill_name: str,
    approved: bool,
) -> GateContext:
    """工具函数：审批硬门控。"""
    decision = GateDecision.APPROVED if approved else GateDecision.DENIED
    return get_gate().resolve_gate(task_id, skill_name, decision)


# ─────────────────────────── 内置 superpowers 三层 skill 注册 ─────────────────

def register_superpowers_bootstrap(gate: SkillGate) -> None:
    """
    注册 superpowers Bootstrap 层 + 流程层 skill（演示用）。
    实际项目中 frontmatter 从各 SKILL.md 文件解析而来。
    """
    # Bootstrap: 1% 规则全局启用
    gate.register_from_dict({
        "name": "using-superpowers",
        "category": "BOOTSTRAP",
        "description": "use when starting a new task, planning, debugging, code review, or any development workflow",
        "trigger_keywords": ["task", "plan", "build", "fix", "debug", "review", "test", "implement", "design"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers using-superpowers/SKILL.md L12-18",
    })

    # 流程层: brainstorming（硬门控）
    gate.register_from_dict({
        "name": "brainstorming",
        "category": "FLOW",
        "description": "use when user describes a goal or需求, before writing any code",
        "trigger_keywords": ["我想", "我要", "帮我", "build", "create", "design", "需求", "目标", "计划", "idea"],
        "hard_gate": True,
        "one_percent_rule": True,
        "source_ref": "superpowers brainstorming/SKILL.md L13-17 HARD-GATE",
    })

    # 流程层: writing-plans
    gate.register_from_dict({
        "name": "writing-plans",
        "category": "FLOW",
        "description": "use after brainstorming approved, when creating execution plans",
        "trigger_keywords": ["计划", "plan", "步骤", "任务分解", "implementation", "roadmap"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers writing-plans/SKILL.md",
    })

    # 流程层: verification-before-completion
    gate.register_from_dict({
        "name": "verification-before-completion",
        "category": "FLOW",
        "description": "use before marking a task done or merging a PR",
        "trigger_keywords": ["完成", "done", "merge", "finish", "提交", "close", "完成前验证"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers verification-before-completion/SKILL.md",
    })

    # 工程层: test-driven-development
    gate.register_from_dict({
        "name": "test-driven-development",
        "category": "ENGINEERING",
        "description": "use when writing new code, before implementation",
        "trigger_keywords": ["写代码", "implement", "new feature", "功能开发", "tdd", "测试先行"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers test-driven-development/SKILL.md",
    })

    # 工程层: systematic-debugging
    gate.register_from_dict({
        "name": "systematic-debugging",
        "category": "ENGINEERING",
        "description": "use when encountering a bug or error",
        "trigger_keywords": ["bug", "错误", "crash", "fail", "exception", "调试", "问题", "修复"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers systematic-debugging/SKILL.md",
    })

    # 工程层: requesting-code-review
    gate.register_from_dict({
        "name": "requesting-code-review",
        "category": "ENGINEERING",
        "description": "use when code is ready for review, before merging",
        "trigger_keywords": ["review", "pr", "pull request", "代码审查", "审阅", "待审"],
        "hard_gate": False,
        "one_percent_rule": True,
        "source_ref": "superpowers requesting-code-review/SKILL.md",
    })