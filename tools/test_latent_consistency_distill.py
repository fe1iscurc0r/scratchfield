"""K684 验收测试：潜在一致性蒸馏（少步学生对齐多步教师）。"""
from __future__ import annotations

import numpy as np

from tools.latent_consistency_distill import (
    distill_step,
    make_system,
    refine,
    refine_error,
)


def test_distilled_student_matches_teacher_with_fewer_steps():
    A, b, x_true, x0 = make_system(seed=0)
    # 教师：60 步小步长（慢速收敛）
    teacher = refine(x0, A, b, mu=0.05, steps=60)
    teacher_err = refine_error(teacher, x_true)

    # 学生：20 步（3× 更少），用蒸馏学到的步长
    X0 = np.array([make_system(seed=s)[3] for s in range(20)])
    mu_student = distill_step(A, b, X0, teacher_steps=60, student_steps=20)
    student = refine(x0, A, b, mu=mu_student, steps=20)
    student_err = refine_error(student, x_true)

    # 20 步 vs 60 步 = 3× 加速；误差不劣于教师（≤ 1.5× 教师误差）
    assert student_err <= 1.5 * teacher_err, f"学生误差 {student_err:.4f} 未达教师 {teacher_err:.4f}"


def test_more_steps_lower_error():
    A, b, x_true, x0 = make_system(seed=0)
    e1 = refine_error(refine(x0, A, b, mu=0.05, steps=5), x_true)
    e2 = refine_error(refine(x0, A, b, mu=0.05, steps=60), x_true)
    assert e2 < e1
