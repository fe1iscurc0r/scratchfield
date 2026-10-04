"""R68 验收测试：射频链路自动优化（扩散变异核 + 数字孪生 BER 验证）。

覆盖：
  1. 优化循环：探索到优于基线 BER 的配置 ≥1 组
  2. config_loss：匹配滤波/纠错码降低实现损耗、提高编码增益
  3. ber_bpsk：BER 随 Eb/N0 单调下降
  4. 基线配置确实差（BER 高于最优配置）

运行：python -m pytest mcpserver/rf_brain/test_rf_link_optimizer.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import rf_link_optimizer as rlo


def test_optimizer_finds_better_config():
    """配置变异 + 仿真验证循环探索到优于基线 BER 的配置。"""
    result = rlo.optimize_rf_link(eb_n0_db=5.0, iterations=300, seed=0)
    assert result.best_ber < result.baseline_ber
    assert result.improvement > 1.0  # 基线/最优 > 1
    # 至少探索并验证过若干配置
    assert len(result.explored) == 300


def test_config_loss_reflects_design():
    """匹配滤波 + 好纠错码 → 更低损耗/更高增益。"""
    base = rlo.config_loss(rlo.baseline_config())
    opt = rlo.config_loss({"pulse": "rrc", "rolloff": 0.35, "matched": True, "code": "hamming"})
    base_loss = base[0] - base[1]       # 净损耗
    opt_loss = opt[0] - opt[1]
    assert opt_loss < base_loss


def test_ber_bpsk_monotonic():
    """BER 随 Eb/N0 单调下降（Q 函数语义正确）。"""
    assert rlo.ber_bpsk(0.0) > rlo.ber_bpsk(10.0)
    assert 0.0 < rlo.ber_bpsk(0.0) < 0.5


def test_baseline_is_worse_than_optimal():
    """基线（rect/无匹配/无纠错）BER 高于最优（rrc/匹配/Hamming）配置。"""
    base_cfg = rlo.baseline_config()
    base_ber = rlo.ber_bpsk(5.0, *rlo.config_loss(base_cfg))
    opt_ber = rlo.ber_bpsk(5.0, *rlo.config_loss({"pulse": "rrc", "rolloff": 0.35, "matched": True, "code": "hamming"}))
    assert base_ber > opt_ber
