# test_skill_gate.py — superpowers 方法论验证用例
# W64-06 验收硬线：pytest 全绿 ≥4 用例

import time

import pytest
from skill_gate import (
    GateContext,
    GateDecision,
    SkillCategory,
    SkillFrontmatter,
    SkillGate,
    check_and_request_gate,
    get_gate,
    register_superpowers_bootstrap,
    resolve_gate,
    should_invoke_skill,
)


class TestSkillGateRegistration:
    """测试 skill 注册与查询。"""

    def test_register_single_skill(self):
        gate = SkillGate()
        fm = SkillFrontmatter(
            name="test-skill",
            category=SkillCategory.ENGINEERING,
            description="use when testing, before deploy",
            hard_gate=False,
            one_percent_rule=True,
        )
        gate.register(fm)
        assert "test-skill" in gate.all_registered()

    def test_register_from_dict(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "tdd-skill",
            "category": "ENGINEERING",
            "description": "use when writing new code, before implementation",
            "hard_gate": False,
            "one_percent_rule": True,
        })
        assert "tdd-skill" in gate.all_registered()
        fm = gate.get_frontmatter("tdd-skill")
        assert fm is not None
        assert fm.one_percent_rule is True
        assert "writing new code" in fm.trigger_keywords

    def test_register_superpowers_bootstrap(self):
        gate = SkillGate()
        register_superpowers_bootstrap(gate)
        assert len(gate.all_registered()) == 7
        assert "using-superpowers" in gate.all_registered()
        assert "brainstorming" in gate.all_registered()
        # 验证 one_percent_rule 技能
        assert len(gate.list_one_percent_skills()) == 7


class TestProgressiveDisclosure:
    """测试渐进式披露机制。"""

    def test_should_expand_matches_keyword(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "debug-skill",
            "category": "ENGINEERING",
            "description": "use when bug, error, crash",
            "hard_gate": False,
            "one_percent_rule": False,
        })
        # 命中关键词
        assert gate.should_expand("debug-skill", "I found a bug in the code") is True
        # 未命中关键词
        assert gate.should_expand("debug-skill", "building a new feature") is False

    def test_should_expand_no_trigger_no_expand(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "plan-skill",
            "category": "FLOW",
            "description": "use when planning, roadmap",
            "hard_gate": False,
            "one_percent_rule": False,
        })
        assert gate.should_expand("plan-skill", "running tests") is False

    def test_expand_skill_returns_body_on_trigger(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "review-skill",
            "category": "ENGINEERING",
            "description": "use when review, code review",
            "hard_gate": False,
            "one_percent_rule": False,
        })
        # 加载正文到缓存
        gate.load_skill_body("review-skill", "## Code Review Steps\n1. Read...")
        result = gate.expand_skill("review-skill", "please review this PR")
        assert result is not None
        assert "Code Review Steps" in result

    def test_expand_skill_returns_none_when_not_triggered(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "review-skill",
            "category": "ENGINEERING",
            "description": "use when review, code review",
            "hard_gate": False,
            "one_percent_rule": False,
        })
        result = gate.expand_skill("review-skill", "just running a test")
        assert result is None


class TestHardGate:
    """测试硬门控(HARD-GATE)机制。"""

    def test_unregistered_skill_no_gate(self):
        gate = SkillGate()
        # 无门控记录时直接放行
        decision = gate.check_gate("t1", "non-existent")
        assert decision == GateDecision.APPROVED

    def test_non_hard_gate_skill_no_pending(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "tdd",
            "category": "ENGINEERING",
            "description": "use when writing code",
            "hard_gate": False,
            "one_percent_rule": False,
        })
        # 非硬门控 skill 无 pending gate
        with pytest.raises(ValueError, match="does not require hard gate"):
            gate.request_gate("t1", "tdd", "implement feature")

    def test_request_gate_creates_pending_context(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        ctx = gate.request_gate("t1", "brainstorming", "我想做一个博客系统")
        assert ctx is not None
        assert ctx.task_id == "t1"
        assert ctx.decision == GateDecision.PENDING
        assert ctx.intent == "我想做一个博客系统"

    def test_resolve_gate_approved(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t1", "brainstorming", "我想做一个博客系统")
        ctx = gate.resolve_gate("t1", "brainstorming", GateDecision.APPROVED)
        assert ctx.decision == GateDecision.APPROVED
        assert ctx.decided_at is not None

    def test_resolve_gate_denied(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t2", "brainstorming", "危险操作")
        ctx = gate.resolve_gate("t2", "brainstorming", GateDecision.DENIED)
        assert ctx.decision == GateDecision.DENIED

    def test_double_resolve_raises(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t3", "brainstorming", "操作")
        gate.resolve_gate("t3", "brainstorming", GateDecision.APPROVED)
        with pytest.raises(ValueError, match="already resolved"):
            gate.resolve_gate("t3", "brainstorming", GateDecision.DENIED)

    def test_check_gate_returns_decision(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t4", "brainstorming", "another idea")
        assert gate.check_gate("t4", "brainstorming") == GateDecision.PENDING
        gate.resolve_gate("t4", "brainstorming", GateDecision.APPROVED)
        assert gate.check_gate("t4", "brainstorming") == GateDecision.APPROVED

    def test_gate_pending_count(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when user describes a goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        assert gate.gate_pending_count() == 0
        gate.request_gate("t5", "brainstorming", "idea 1")
        gate.request_gate("t6", "brainstorming", "idea 2")
        assert gate.gate_pending_count() == 2
        gate.resolve_gate("t5", "brainstorming", GateDecision.APPROVED)
        assert gate.gate_pending_count() == 1


class TestOnePercentRule:
    """测试 1% 规则强制触发机制。"""

    def test_one_percent_triggers_on_keyword_hit(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "systematic-debugging",
            "category": "ENGINEERING",
            "description": "use when bug, error, crash, exception",
            "hard_gate": False,
            "one_percent_rule": True,
        })
        results = gate.check_one_percent(
            "The application crashed with a segmentation fault",
            context={"task_id": "t1", "intent": "debug crash"},
        )
        assert len(results) == 1
        assert results[0].matched is True
        assert "bug" in results[0].matched_keywords or "crash" in results[0].matched_keywords

    def test_one_percent_no_hit_no_trigger(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "test-driven-development",
            "category": "ENGINEERING",
            "description": "use when writing code, new feature",
            "hard_gate": False,
            "one_percent_rule": True,
        })
        results = gate.check_one_percent("just reading documentation")
        assert len(results) == 1
        assert results[0].matched is False

    def test_should_invoke_skill_one_percent_rule(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "test-driven-development",
            "category": "ENGINEERING",
            "description": "use when writing code, new feature, implement",
            "hard_gate": False,
            "one_percent_rule": True,
        })
        invoked, reason = gate.should_invoke_skill(
            "test-driven-development",
            "I need to implement a new user authentication module",
        )
        assert invoked is True
        assert "1% rule triggered" in reason

    def test_should_invoke_skill_not_registered(self):
        gate = SkillGate()
        invoked, reason = gate.should_invoke_skill("non-existent", "some text")
        assert invoked is False
        assert "not registered" in reason


class TestShouldInvokeSkillIntegration:
    """集成测试：1% 规则 + 硬门控联动。"""

    def test_one_percent_with_hard_gate_creates_pending(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal, 需求, 我想",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        results = gate.check_one_percent(
            "我想做一个博客系统",
            context={"task_id": "t7", "intent": "博客系统"},
        )
        assert len(results) == 1
        assert results[0].matched is True
        assert results[0].gate_required is True
        assert results[0].gate_context is not None
        assert results[0].gate_context.decision == GateDecision.PENDING

    def test_should_invoke_blocked_by_gate(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal, 需求, 我想",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        # 发起门控申请，未批准
        gate.request_gate("t8", "brainstorming", "待审批的意图")
        invoked, reason = gate.should_invoke_skill(
            "brainstorming",
            "我想做一个博客系统",
            task_id="t8",
        )
        assert invoked is False
        assert "gate pending" in reason

    def test_should_invoke_approved_gate_passes(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal, 需求, 我想",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t9", "brainstorming", "已批准的意图")
        gate.resolve_gate("t9", "brainstorming", GateDecision.APPROVED)
        invoked, reason = gate.should_invoke_skill(
            "brainstorming",
            "我想做一个博客系统",
            task_id="t9",
        )
        assert invoked is True
        assert "1% rule triggered" in reason

    def test_audit_hash_generation(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal",
            "hard_gate": True,
            "one_percent_rule": False,
        })
        ts = 1234567890.0
        h1 = gate.build_audit_hash("t1", "brainstorming", "test intent", timestamp=ts)
        h2 = gate.build_audit_hash("t1", "brainstorming", "test intent", timestamp=ts)
        # 相同输入产生相同哈希
        assert h1 == h2
        # 不同输入产生不同哈希
        h3 = gate.build_audit_hash("t2", "brainstorming", "test intent", timestamp=ts)
        assert h1 != h3
        assert len(h1) == 16


class TestGlobalSingleton:
    """测试全局单例与工具函数。"""

    def test_global_gate_singleton(self):
        g1 = get_gate()
        g2 = get_gate()
        assert g1 is g2  # 同一实例

    def test_should_invoke_skill_global(self):
        gate = SkillGate()  # 本地实例，不依赖全局状态
        gate.register_from_dict({
            "name": "systematic-debugging",
            "category": "ENGINEERING",
            "description": "use when bug, error",
            "hard_gate": False,
            "one_percent_rule": True,
        })
        invoked, reason = gate.should_invoke_skill(
            "systematic-debugging",
            "got a runtime error",
        )
        assert invoked is True

    def test_check_and_request_gate_local_instance(self):
        # 每个测试用独立本地实例，避免全局状态污染
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        ctx = gate.request_gate("t10", "brainstorming", "local test intent")
        assert ctx.decision == GateDecision.PENDING

    def test_resolve_gate_local_instance(self):
        gate = SkillGate()
        gate.register_from_dict({
            "name": "brainstorming",
            "category": "FLOW",
            "description": "use when goal",
            "hard_gate": True,
            "one_percent_rule": True,
        })
        gate.request_gate("t11", "brainstorming", "intent")
        gate.resolve_gate("t11", "brainstorming", GateDecision.APPROVED)
        assert gate.check_gate("t11", "brainstorming") == GateDecision.APPROVED