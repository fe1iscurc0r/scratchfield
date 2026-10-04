"""adaptive_reasoning_budget 测试（K17 验收：简单任务省 token ≥30%，复杂任务精度不降）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from adaptive_reasoning_budget import (
    Task,
    adaptive,
    always_long,
    budget_accuracy,
    choose_budget,
    estimate_complexity,
    expected_metrics,
    mixed_dataset,
)


def test_choose_budget_band_mapping():
    assert choose_budget(0.1) == "NoThink"
    assert choose_budget(0.5) == "Short"
    assert choose_budget(0.9) == "Long"


def test_estimate_complexity_tracks_difficulty():
    # 难度越高，估计复杂度越高（噪声不足以翻转 easy/hard 的相对顺序）
    easy = Task("e", "easy", 0.0)
    hard = Task("h", "hard", 0.0)
    assert estimate_complexity(easy) < estimate_complexity(hard)


def test_saves_at_least_30pct_tokens():
    tasks = mixed_dataset()
    base_tok, _ = always_long(tasks)
    ada_tok, _ = adaptive(tasks)
    assert ada_tok <= 0.70 * base_tok, f"省 token {(1 - ada_tok/base_tok)*100:.1f}% 不达标（要求 ≥30%）"


def test_complex_task_accuracy_not_degraded():
    tasks = mixed_dataset()
    _, base_acc = always_long(tasks)
    _, ada_acc = adaptive(tasks)
    # 复杂任务必须路由到 Long，整体正确率不显著下降（容差 1pp 内）
    assert ada_acc >= base_acc - 0.01, f"精度下降 {ada_acc - base_acc:.4f} 超出容差"


def test_complex_tasks_routed_to_long():
    # 显式验证：hard 任务被正确路由到 Long（复杂任务精度不降的机制保证）
    hard_tasks = [Task(f"h{i}", "hard", 0.0) for i in range(20)]
    budgets = [choose_budget(estimate_complexity(t)) for t in hard_tasks]
    assert all(b == "Long" for b in budgets)
