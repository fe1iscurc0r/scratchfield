"""W61-01 验收测试：AirMoE 空中聚合协议模拟。

覆盖：
  1. 三种方案输出结构完整
  2. AirComp 时隙数 < TDMA 时隙数（核心收益）
  3. AirComp 聚合精度不低于任一单节点方案
  4. TDMA 精度有定义（不是 NaN）
  5. 节点数扩展性（3/5/8 节点均成立）

运行：python -m pytest tools/test_airmoe_aggregation.py -q
"""
from __future__ import annotations

# 路径：scratchpad/mcpserver/rf_brain/prototypes/airmoe_aggregation.py
# tools/test_airmoe_aggregation.py → 向上 3 级到 scratchpad/
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mcpserver.rf_brain.prototypes.airmoe_aggregation import (
    aircomp_upload,
    compare_schemes,
    local_independent,
    synthesize_node_detection,
    tdma_upload,
    true_spectrum_map,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def node_results():
    return synthesize_node_detection(n_nodes=5, seed=42)


@pytest.fixture(scope="module")
def true_map():
    return true_spectrum_map()


# ---------------------------------------------------------------------------
# 验收硬线 1：AirComp 用时隙 < TDMA 用时隙
# ---------------------------------------------------------------------------

def test_aircomp_slots_lt_tdma(node_results, true_map):
    """AirComp 时隙数（固定=1）必须小于 TDMA 时隙数（N 节点）。"""
    tdma = tdma_upload(node_results, true_map)
    ac   = aircomp_upload(node_results, true_map)
    assert ac.slots_used < tdma.slots_used, (
        f"AirComp 时隙({ac.slots_used}) ≥ TDMA 时隙({tdma.slots_used})，违反核心收益"
    )


def test_aircomp_slots_always_one(node_results, true_map):
    """AirComp 无论节点数多少，时隙恒为 1（单次空中叠加）。"""
    ac = aircomp_upload(node_results, true_map)
    assert ac.slots_used == 1


# ---------------------------------------------------------------------------
# 验收硬线 2：聚合精度不低于单节点
# ---------------------------------------------------------------------------

def test_aircomp_accuracy_gte_single_node(node_results, true_map):
    """AirComp 聚合精度 >= 本地独立单节点精度（协作有收益）。"""
    ac    = aircomp_upload(node_results, true_map)
    local = local_independent(node_results, true_map)
    assert ac.accuracy >= local.accuracy - 1e-6, (
        f"AirComp 精度({ac.accuracy:.4f}) < Local 精度({local.accuracy:.4f})，协作无收益"
    )


def test_aircomp_accuracy_gte_tdma(node_results, true_map):
    """AirComp 聚合精度 >= TDMA 精度（精度不因空中叠加而损失）。"""
    tdma = tdma_upload(node_results, true_map)
    ac   = aircomp_upload(node_results, true_map)
    # AirComp 精度允许轻微损失（对齐误差），但方向应一致
    assert ac.accuracy >= tdma.accuracy - 0.05, (
        f"AirComp 精度({ac.accuracy:.4f}) 明显低于 TDMA({tdma.accuracy:.4f})"
    )


# ---------------------------------------------------------------------------
# 基本结构完整性
# ---------------------------------------------------------------------------

def test_tdma_structure(node_results, true_map):
    """TDMA 报告结构完整且字段类型正确。"""
    tdma = tdma_upload(node_results, true_map)
    assert isinstance(tdma.slots_used, int)
    assert isinstance(tdma.freq_occupancy, float)
    assert isinstance(tdma.accuracy, float)
    assert 0.0 <= tdma.accuracy <= 1.0
    assert tdma.slots_used > 0


def test_aircomp_structure(node_results, true_map):
    """AirComp 报告结构完整。"""
    ac = aircomp_upload(node_results, true_map)
    assert isinstance(ac.slots_used, int)
    assert isinstance(ac.accuracy, float)
    assert 0.0 <= ac.accuracy <= 1.0
    assert ac.slots_used == 1


def test_local_structure(node_results, true_map):
    """Local 报告结构完整。"""
    local = local_independent(node_results, true_map)
    assert isinstance(local.slots_used, int)
    assert local.slots_used == 0  # 无上行
    assert isinstance(local.accuracy, float)


# ---------------------------------------------------------------------------
# 扩展性
# ---------------------------------------------------------------------------

def test_compare_schemes_multiple_nodes():
    """compare_schemes 对 3/5/8 节点均返回有效结果，验收断言成立。"""
    for n in [3, 5, 8]:
        r = compare_schemes(n_nodes=n, seed=42)
        assert r["n_nodes"] == n
        assert r["验收断言"]["aircomp_slots_lt_tdma"] is True
        assert r["验收断言"]["aircomp_accuracy_gte_single"] is True
        # 精度应为有效数
        assert 0.0 <= r["AirComp"]["accuracy"] <= 1.0


# ---------------------------------------------------------------------------
# 功率对齐误差合理性
# ---------------------------------------------------------------------------

def test_aircomp_align_error_reasonable(node_results, true_map):
    """功率对齐误差应在合理范围内（< 10 dB）。"""
    ac = aircomp_upload(node_results, true_map)
    assert ac.power_align_error_db < 10.0, (
        f"功率对齐误差({ac.power_align_error_db:.2f} dB)过大，同步精度不足"
    )