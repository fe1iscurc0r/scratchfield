"""工具链 · 潜在一致性蒸馏（K684）

授粉自 2608.31053v1（Identity-Conditioned Latent Consistency Distillation）：
把「多步慢速教师」蒸馏成「少步快速学生」——一致性损失让学生少步输出对齐教师
多步收敛输出（4.36× 加速，质量与教师相当）。

原型（纯 numpy，机制版）：以「迭代解线性系统 Ax=b」为任务——教师小步长多步收敛，
学生用「蒸馏学到的步长」少步即达教师精度。

验收口径：蒸馏后学生以更少步骤（≥2× 加速）达到与教师相当的精度（误差 ≤ 教师）。
"""
from __future__ import annotations

import numpy as np

__all__ = ["make_system", "refine", "distill_step", "refine_error"]


def make_system(d: int = 8, seed: int = 0, cond: float = 10.0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """构造正定系统 Ax=b：x_true 为解，x0 为带噪初始。"""
    rng = np.random.default_rng(seed)
    Q = np.linalg.qr(rng.standard_normal((d, d)))[0]
    eig = np.logspace(0, np.log10(cond), d)
    A = Q @ np.diag(eig) @ Q.T
    x_true = rng.standard_normal(d)
    b = A @ x_true
    x0 = x_true + rng.standard_normal(d) * 0.5
    return A, b, x_true, x0


def refine(x: np.ndarray, A: np.ndarray, b: np.ndarray, mu: float, steps: int) -> np.ndarray:
    """梯度下降解 Ax=b：x ← x − μ·(Ax − b)，跑 steps 步。"""
    x = np.asarray(x, dtype=float).copy()
    for _ in range(steps):
        x -= mu * (A @ x - b)
    return x


def refine_error(x: np.ndarray, x_true: np.ndarray) -> float:
    return float(np.mean((x - x_true) ** 2))


def distill_step(A: np.ndarray, b: np.ndarray, X0: np.ndarray, *, teacher_steps: int = 60,
                 student_steps: int = 15, mu_teacher: float = 0.05) -> float:
    """一致性蒸馏：学学生步长 mu，使学生 student_steps 步输出 ≈ 教师 teacher_steps 步输出。

    教师目标 = refine(X0, mu_teacher, teacher_steps)（多步收敛）。
    学生 = refine(X0, mu, student_steps)。对一维 μ 用网格搜索最小化一致性 MSE
    （线性系统下最优 μ 只取决于 A，故在 X0 上学到的 μ 对新输入泛化）。
    """
    teacher = np.stack([refine(x0, A, b, mu_teacher, teacher_steps) for x0 in X0])
    # 稳定步长上界 = 2/λ_max（梯度下降收敛条件），据此自适应网格范围（对条件数鲁棒）
    lam_max = float(np.linalg.eigvalsh(A).max())
    mu_hi = 2.0 / lam_max
    best_mu, best_err = float(mu_teacher), float("inf")
    for mu in np.linspace(mu_hi * 0.05, mu_hi, 300):
        out = np.stack([refine(x0, A, b, mu, student_steps) for x0 in X0])
        err = float(np.mean((out - teacher) ** 2))
        if err < best_err:
            best_mu, best_err = mu, err
    return best_mu
