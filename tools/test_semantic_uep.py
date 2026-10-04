"""W58-03 验收测试：语义 UEP（≥4 用例）。

运行：python -m pytest tools/test_semantic_uep.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from semantic_uep import UEP_TABLE, protection_strength, uep_params


def test_importance_monotonicity():
    """语义重要性越高，保护强度越高（单调）。"""
    s0 = protection_strength(uep_params(0))
    s1 = protection_strength(uep_params(1))
    s2 = protection_strength(uep_params(2))
    assert s0 > s1 > s2


def test_table_lookup():
    """查表返回正确三元组。"""
    assert uep_params(0) == {"code_rate": 1 / 3, "retx": 2, "power_bias_db": 6.0}
    assert uep_params(2)["retx"] == 0


def test_override_params():
    """可调覆盖：显式覆盖查表默认值。"""
    p = uep_params(2, code_rate=1 / 2, retx=1, power_bias_db=3.0)
    assert p == {"code_rate": 0.5, "retx": 1, "power_bias_db": 3.0}


def test_invalid_importance_raises():
    """未知语义等级抛错。"""
    try:
        uep_params(9)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_protection_increases_with_retx_and_power():
    """保护强度随重传次数 / 功率偏置单调增加。"""
    base = {"code_rate": 0.5, "retx": 0, "power_bias_db": 0.0}
    more_retx = {"code_rate": 0.5, "retx": 2, "power_bias_db": 0.0}
    more_power = {"code_rate": 0.5, "retx": 0, "power_bias_db": 6.0}
    assert protection_strength(more_retx) > protection_strength(base)
    assert protection_strength(more_power) > protection_strength(base)
