"""raman_utils 验收硬线（RamanSPy 薄封装落地 · ≥8 用例）。"""
import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import raman_compat, raman_utils  # noqa: E402


def test_compat_get_cmap_patched():
    """shim1：matplotlib ≥3.9 下 get_cmap 可用。"""
    import matplotlib.cm as cm
    assert callable(cm.get_cmap)
    cmap = cm.get_cmap("viridis")
    assert cmap is not None


def test_compat_flinalg_patched():
    """shim2：scipy.linalg._flinalg.sdet_c 可用（用 np.linalg.det 实现）。"""
    import scipy.linalg
    mod = scipy.linalg._flinalg
    det, _ = mod.sdet_c(np.eye(3))
    assert abs(det - 1.0) < 1e-12


def test_compat_idempotent():
    """shim 幂等：重复 apply 不炸、不改变行为。"""
    raman_compat.apply()
    import matplotlib.cm as cm
    assert callable(cm.get_cmap)


def test_parse_raman_text_auto_delimiter():
    """两列文本（逗号/制表符）解析为 DataFrame。"""
    for text in ("550,1.0\n600,2.0\n", "550\t1.0\n600\t2.0\n"):
        df = raman_utils.parse_raman(text.encode(), fmt="text")
        assert df.shape == (2, 2)


def test_parse_raman_text_rejects_single_column():
    """单列输入明确报错。"""
    with pytest.raises(ValueError, match="至少需要两列"):
        raman_utils.parse_raman(b"1\n2\n", fmt="text")


def test_remove_spikes_kills_single_spike():
    """去尖峰：合成单点尖峰被压回邻域水平。"""
    rng = np.random.default_rng(0)
    y = np.ones(100) + rng.normal(0, 0.02, 100)
    y[50] += 100.0
    out = raman_utils.remove_spikes(y)
    assert out[50] < 10.0


def test_asls_baseline_follows_smooth_background():
    """ASLS 基线：跟随缓变背景，不吞尖峰。"""
    x = np.linspace(0, 1, 200)
    y = 30 + 10 * x + 50 * np.exp(-((x - 0.5) ** 2) / 0.002)
    base = raman_utils.asls_baseline(y)
    # 基线在峰值点远低于峰顶、贴近两端背景
    assert base[100] < y[100] * 0.6
    assert abs(base[0] - y[0]) < 5.0


def test_preprocess_raman_peak_position_preserved():
    """预处理链不挪峰位（对齐评估报告：1250 → ~1248.6 级精度）。"""
    df = raman_utils.synth_raman(seed=3)
    out = raman_utils.preprocess_raman(df)
    y = out.iloc[:, 1].to_numpy()
    peak_idx = int(np.argmax(y))
    peak_x = out.iloc[:, 0].iloc[peak_idx]
    assert 1240.0 < peak_x < 1260.0


def test_preprocess_raman_normalises_to_unit_range():
    """MinMax 归一化：处理后强度落在 [0,1]。"""
    df = raman_utils.synth_raman(seed=4)
    out = raman_utils.preprocess_raman(df)
    y = out.iloc[:, 1].to_numpy()
    assert abs(y.max() - 1.0) < 1e-9 and y.min() >= 0.0


def test_plot_raman_outputs_png():
    """绘图输出 PNG 字节流（PNG 魔数校验）。"""
    df = raman_utils.synth_raman(seed=5)
    buf = raman_utils.plot_raman(df)
    assert buf.read(8) == b"\x89PNG\r\n\x1a\n"


def test_unknown_vendor_format_rejected():
    """未知厂商格式明确报错（不静默）。"""
    with pytest.raises(ValueError, match="不支持的厂商格式"):
        raman_utils.parse_raman(b"\x00" * 16, fmt="unknown")
