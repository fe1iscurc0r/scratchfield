"""S17 验收测试：Wrong-Physics 后门基准（标签一致检测不出 + 2 种物理一致性检测方法）。

运行：python -m pytest tools/test_wrong_physics_detect.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from wrong_physics_detect import (
    backdoored_operator,
    clean_operator,
    conservation_residual,
    make_clean_input,
    make_triggered_input,
    reference_divergence,
    run_benchmark,
)


def test_clean_operator_conserves_mass():
    u = make_clean_input(seed=1)
    out = clean_operator(u)
    assert conservation_residual(u, out) < 1e-9


def test_label_consistency_undetected_by_labels():
    """核心：干净输入上后门模型与干净模型逐点一致 → 标签审计查不出后门。"""
    u = make_clean_input(seed=2)
    assert np.allclose(backdoored_operator(u), clean_operator(u), atol=1e-12)


def test_backdoor_injects_on_trigger_only():
    clean = make_clean_input(seed=3)
    trig = make_triggered_input(seed=3)
    # 干净输入：无注入（一致）
    assert np.allclose(backdoored_operator(clean), clean_operator(clean), atol=1e-12)
    # 触发输入：注入破坏守恒
    assert conservation_residual(trig, backdoored_operator(trig)) > 1.0


def test_detection_method1_residual_flags_backdoor():
    """检测方法①守恒残差：触发样本残差大、干净样本残差 ≈0。"""
    u_t = make_triggered_input(seed=4)
    u_c = make_clean_input(seed=4)
    assert conservation_residual(u_t, backdoored_operator(u_t)) > 1e-6
    assert conservation_residual(u_c, backdoored_operator(u_c)) < 1e-6


def test_detection_method2_divergence_flags_backdoor():
    """检测方法②参考偏差：触发样本偏离干净参考、干净样本零偏差。"""
    u_t = make_triggered_input(seed=5)
    u_c = make_clean_input(seed=5)
    assert reference_divergence(backdoored_operator(u_t), clean_operator(u_t)) > 1e-6
    assert reference_divergence(backdoored_operator(u_c), clean_operator(u_c)) < 1e-12


def test_benchmark_two_methods_both_detect():
    """跑基准：两种检测方法都命中全部触发样本，且干净模型不被误报。"""
    report = run_benchmark(backdoored_operator, n_probes=10, seed=0)
    assert report.residual_detected
    assert report.divergence_detected
    # 干净输入上仍逐点一致（标签一致性成立，标签审计失效）
    assert report.clean_identical


def test_clean_model_not_flagged():
    """干净模型跑基准：两种方法都不误报。"""
    report = run_benchmark(clean_operator, n_probes=10, seed=0)
    assert report.n_triggered_flagged == 0
    assert report.n_divergence_flagged == 0
