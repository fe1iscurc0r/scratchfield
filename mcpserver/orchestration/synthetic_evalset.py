"""合成评估集生成器（模板/规则 · 无 LLM · 可复现）。

授粉来源：NVIDIA/SkillEvaluator（Apache-2.0 ★399）的「合成评估集生成」设计思想，
独立实现。目的：给一个 skill 的「触发条件 + 步骤描述」自动合成 N 条测试用例
（输入场景 → 期望产出结构），供活体评估 / 单测参考，不依赖 LLM 也能跑。

实现纪律（授粉）：
- 纯标准库（random），不引新依赖。
- 模板/规则生成，确定性可复现（同输入同 seed → 同输出），供 pytest 硬线验收。
- 只生成「用例结构」，不执行 skill，不触碰任何现有模块核心。
"""
from __future__ import annotations

import random

# 场景模板（用于构造「输入场景」前缀，按序轮转，保证确定性）
_CONTEXTS = [
    "用户在对话中提出需求",
    "系统任务自动触发该技能",
    "批处理管道调用该技能",
    "用户追问细节触发该技能",
]


def generate_evalset(skill_spec: dict, n: int = 3, seed: int = 42) -> list[dict]:
    """由 skill 规格合成 N 条测试用例（可复现）。

    参数
    ----
    skill_spec : dict，需含
        - ``name``（str）：技能名
        - ``triggers``（list[str]）：触发条件描述
        - ``steps``（list[str]）：步骤描述
    n : 生成的用例条数
    seed : 随机种子（保证同输入同 seed 同输出）

    返回
    ----
    list[dict]：每条 ``{"case_id", "scenario", "expected"}``，
    其中 ``expected`` 为 ``{"type", "skill", "must_contain", "steps_count"}``。
    """
    name = skill_spec.get("name") or "unnamed_skill"
    triggers = skill_spec.get("triggers") or ["触发该技能"]
    steps = skill_spec.get("steps") or ["执行技能步骤"]

    rng = random.Random(seed)
    cases: list[dict] = []
    for i in range(n):
        trigger = triggers[rng.randrange(len(triggers))]
        context = _CONTEXTS[i % len(_CONTEXTS)]
        scenario = f"{context}：{trigger}"
        expected = {
            "type": "structured",
            "skill": name,
            # 期望产出应能体现前几个关键步骤（截断避免超长）
            "must_contain": [step[:24] for step in steps[:3]],
            "steps_count": len(steps),
        }
        cases.append({
            "case_id": f"{name}-{i + 1:02d}",
            "scenario": scenario,
            "expected": expected,
        })
    return cases
