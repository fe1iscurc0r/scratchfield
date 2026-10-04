"""R58 验收测试：Omega-S 弹性惩罚 LoRA（无需 Fisher 的权重保护）。

覆盖：
  1. 保留率提升 ≥10pp（Omega-S vs 无惩罚 LoRA）
  2. Omega-S 确实保护了「被新任务破坏的重要权重」（ΔW 更小）
  3. LoRAModel：weights() == w0 + delta()，预测自洽
  4. 坏参数拒绝（rank 越界）

运行：python -m pytest tools/test_omega_lora.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.omega_lora import (
    LoRAModel,
    accuracy,
    logistic_loss_and_grad,
    overlapping_tasks,
    retention_experiment,
    train_linear,
)


def test_omega_improves_retention_by_10pp():
    """Omega-S 保留率较无惩罚 LoRA 提升 ≥10pp。"""
    Xa, ya, Xb, yb = overlapping_tasks(seed=0)
    r = retention_experiment(Xa, ya, Xb, yb, rank=2, omega_lambda=0.05, seed=0)
    assert r.plain_retention < 0.7  # 无惩罚确实发生遗忘（<70%）
    assert r.improvement_pp >= 10.0, f"保留率提升 {r.improvement_pp:.1f}pp 未达 10pp"


def test_omega_protects_flipped_weight():
    """Omega-S 对被破坏的权重（特征 1）施加了更小的改动。"""
    Xa, ya, Xb, yb = overlapping_tasks(seed=0)
    w0 = train_linear(Xa, ya, steps=300)
    plain = LoRAModel(w0, rank=2, omega_lambda=0.0, seed=0).fine_tune(Xb, yb, steps=300)
    omega = LoRAModel(w0, rank=2, omega_lambda=0.05, seed=0).fine_tune(Xb, yb, steps=300)
    # 特征 1 的权重被任务 B 翻转；Omega-S 的改动量应更小
    d_plain = abs(float(plain.weights().ravel()[1] - w0[1]))
    d_omega = abs(float(omega.weights().ravel()[1] - w0[1]))
    assert d_omega < d_plain


def test_lora_weights_and_predict_consistent():
    w0 = np.array([1.0, -0.5, 0.2])
    model = LoRAModel(w0, rank=2, omega_lambda=0.05, seed=1)
    assert np.allclose(model.weights().ravel(), w0 + model.delta().ravel())
    X = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert np.all(model.predict(X) == np.sign(X @ model.weights().ravel()))


def test_logistic_loss_and_grad_shape():
    rng = np.random.default_rng(0)
    X = rng.standard_normal((50, 6))
    y = np.sign(rng.standard_normal(50))
    loss, g = logistic_loss_and_grad(np.zeros(6), X, y)
    assert np.isfinite(loss) and g.shape == (6,)


def test_rejects_bad_rank():
    w0 = np.ones(4)
    with pytest.raises(ValueError):
        LoRAModel(w0, rank=0)
    with pytest.raises(ValueError):
        LoRAModel(w0, rank=5)
