"""W124-05 验收：Skills 技能加载循环（命中/未命中/校验/回写/角色白名单）。

覆盖：frontmatter 解析与校验（缺 name/description 拒绝）/ 意图命中注入 / 未命中零注入 /
token 预算截断 / 使用回写事件 / 角色技能白名单（Scope）/ 库概览含非法技能 / loop 注入与 SSE。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
from pathlib import Path

import pytest

from apiserver import skill_loader
from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间

SKILL_MD = """---
name: material-query
description: Query material properties and structure data from the local material science database for materials research tasks.
trigger: 材料, 材料性质, band gap, 带隙
---

# 材料性质查询

步骤：
1. 用 material_science 工具按化学式查询；
2. 报告带隙/结构/来源，不确定就说不确定。
"""

SKILL_BAD = """---
description: 没有 name 的技能
---

正文
"""

SKILL_SYNTAX = "没有 frontmatter 的技能正文"


@pytest.fixture()
def lib(tmp_path):
    """构造临时技能库：一个合法技能 + 一个非法技能。"""
    public = tmp_path / "public"
    (public / "material-query").mkdir(parents=True)
    (public / "material-query" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (public / "broken").mkdir(parents=True)
    (public / "broken" / "SKILL.md").write_text(SKILL_BAD, encoding="utf-8")
    (public / "no-frontmatter").mkdir(parents=True)
    (public / "no-frontmatter" / "SKILL.md").write_text(SKILL_SYNTAX, encoding="utf-8")
    return public


class _SkillCfg:
    def __init__(self, **kw):
        self.enabled = kw.get("enabled", True)
        self.max_skills = kw.get("max_skills", 2)
        self.threshold = kw.get("threshold", 2)
        self.max_chars_per_skill = kw.get("max_chars_per_skill", 1200)
        self.extra_dirs = kw.get("extra_dirs", [])


@pytest.fixture()
def cfg(lib, monkeypatch):
    def _set(**kw):
        c = _SkillCfg(**kw)
        monkeypatch.setattr(skill_loader, "_cfg", lambda: c)
        monkeypatch.setattr(skill_loader, "search_dirs", lambda: [lib])
        return c

    return _set


# ---------------------------------------------------------------------------
# 解析与校验
# ---------------------------------------------------------------------------


def test_frontmatter_parse_and_validate():
    meta, body = skill_loader.parse_frontmatter(SKILL_MD)
    assert meta["name"] == "material-query"
    assert "band gap" in meta["trigger"] and "材料" in meta["trigger"]
    assert body.strip().startswith("# 材料性质查询")

    ok, reason = skill_loader.validate_frontmatter(meta)
    assert ok, reason
    assert skill_loader.validate_frontmatter({"name": "x"})[0] is False
    assert skill_loader.validate_frontmatter({"description": "有描述但没名字"})[0] is False
    ok, reason = skill_loader.validate_frontmatter({"name": "x", "description": "短"})
    assert not ok and "过短" in reason

    # 无 frontmatter → 校验不通过（正文照常返回）
    meta2, body2 = skill_loader.parse_frontmatter(SKILL_SYNTAX)
    assert meta2 == {} and body2 == SKILL_SYNTAX
    assert skill_loader.validate_frontmatter(meta2)[0] is False


def test_load_library_skips_invalid(cfg, lib):
    cfg()
    skills = skill_loader.load_library()
    assert [s.name for s in skills] == ["material-query"], "非法技能被跳过"
    summary = skill_loader.library_summary()
    assert summary["count"] == 1
    assert len(summary["invalid"]) == 2, summary["invalid"]
    assert summary["budget"]["max_skills"] == 2


def test_validate_skill_file_for_import(cfg, lib):
    cfg()
    ok, _ = skill_loader.validate_skill_file(lib / "material-query" / "SKILL.md")
    assert ok is True
    bad_ok, bad_reason = skill_loader.validate_skill_file(lib / "broken" / "SKILL.md")
    assert bad_ok is False and "name" in bad_reason
    assert skill_loader.validate_skill_file(lib / "nope" / "SKILL.md") == (False, "文件不存在")


# ---------------------------------------------------------------------------
# 命中 / 未命中 / 预算
# ---------------------------------------------------------------------------


def test_match_and_inject_on_intent(cfg):
    cfg()
    context, records = skill_loader.build_skill_context("帮我查一下 BaTiO3 的材料性质和带隙")
    assert records and records[0]["skill"] == "material-query"
    assert records[0]["score"] >= 2 and records[0]["injected_chars"] > 0
    assert "〔可用技能〕" in context and "# 材料性质查询" in context
    assert "不确定就说不确定" in context, "正文要点应注入"


def test_no_hit_injects_nothing(cfg):
    cfg()
    context, records = skill_loader.build_skill_context("今天天气怎么样")
    assert context == "" and records == [], "未命中必须零注入"
    assert skill_loader.match_skills("") == []
    assert skill_loader.match_skills("随便聊聊别的") == []


def test_threshold_and_budget(cfg):
    cfg(threshold=10)
    assert skill_loader.build_skill_context("材料性质")[0] == "", "低于阈值不注入"
    cfg(threshold=1, max_chars_per_skill=60)
    context, records = skill_loader.build_skill_context("查材料性质")
    assert records and "截断" in context
    assert records[0]["injected_chars"] <= 60 + 20


def test_role_whitelist_filters_skills(cfg, monkeypatch):
    """角色技能白名单（Scope W124-01）生效。"""
    cfg()
    from mcpserver import scope as scope_mod

    monkeypatch.setattr(scope_mod, "is_skill_visible",
                        lambda name, role=None: role != "桌宠")
    assert skill_loader.match_skills("材料性质", role="科研"), "科研角色可见"
    assert skill_loader.match_skills("材料性质", role="桌宠") == [], "桌宠角色被白名单挡住"


# ---------------------------------------------------------------------------
# 回写与 loop 接线
# ---------------------------------------------------------------------------


def test_record_usage_emits_event(cfg, monkeypatch):
    cfg()
    events: list[tuple[str, dict]] = []

    class _Bus:
        def emit(self, topic, event):
            events.append((topic, event))

    monkeypatch.setattr("apiserver.event_bus.get_bus", lambda: _Bus())
    _, records = skill_loader.build_skill_context("材料性质怎么查", session_id="s1")
    skill_loader.record_usage(records)
    assert events and events[0][0] == "lumo.skill.invoked"
    assert events[0][1]["skill"] == "material-query" and events[0][1]["session_id"] == "s1"
    skill_loader.record_usage([])  # 空记录不炸


def test_loop_injects_skill_context(cfg, monkeypatch):
    from tests.test_agentic_loop_flow import _collect, _events, _FakeLLM, _ScriptedCalls

    cfg()
    emitted: list = []
    monkeypatch.setattr(skill_loader, "record_usage", lambda records: emitted.extend(records))

    llm = _FakeLLM(["按材料技能规范查过了", "结论如上"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls([[], []]))

    messages = [{"role": "system", "content": "你是陆墨"},
                {"role": "user", "content": "帮我查下材料性质与带隙"}]
    chunks = asyncio.run(_collect(atl.run_agentic_loop(messages, "s-skill", max_rounds=1)))
    events = _events(chunks)

    assert llm.calls[0][0]["role"] == "system"
    assert "〔可用技能〕" in llm.calls[0][0]["content"], "技能应并入首条 system"
    assert "material-query" in llm.calls[0][0]["content"]
    assert any(e.get("type") == "skills" for e in events)
    assert emitted and emitted[0]["skill"] == "material-query"

    # 未命中：零注入
    llm2 = _FakeLLM(["好的"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm2)
    asyncio.run(_collect(atl.run_agentic_loop(
        [{"role": "system", "content": "你是陆墨"}, {"role": "user", "content": "今天几号"}],
        "s-skill", max_rounds=1,
    )))
    assert "〔可用技能〕" not in llm2.calls[0][0]["content"]
