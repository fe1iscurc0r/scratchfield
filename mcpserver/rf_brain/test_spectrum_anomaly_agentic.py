"""R49 验收测试：Agentic 主动学习频谱异常筛选（隔离森林 → 规则评审 → 共识过滤）。

覆盖：
  1. embed_spectrum / embed_spectra：归一化 [0,1]、降采样、批量形状、坏参数拒绝
  2. IsolationForest：fit 后可复现、异常分 ∈ (0,1]、异常样本分数显著高于正常样本
  3. RuleReviewer：空/常数/平坦谱过滤；多峰/宽带标注保留
  4. screen_candidates：合成异常注入下候选命中率 ≥80%，筛选量较全量扫描降 ≥10×

运行：python -m pytest mcpserver/rf_brain/test_spectrum_anomaly_agentic.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import spectrum_anomaly_agentic as saa

N_BINS = 128


def _gaussian(n: int, center: float, width: float) -> np.ndarray:
    i = np.arange(n, dtype=float)
    return np.exp(-0.5 * ((i - center) / width) ** 2)


def _normal_spectrum(rng: np.random.Generator, n: int = N_BINS) -> np.ndarray:
    """正常：单载波（单个高斯峰）+ 低底噪。"""
    center = float(rng.uniform(8, n - 8))
    width = float(rng.uniform(1.5, 3.0))
    amp = float(rng.uniform(0.7, 1.0))
    x = amp * _gaussian(n, center, width)
    x += 0.02 * rng.random(n)
    return x


def _anomaly_spectrum(rng: np.random.Generator, n: int = N_BINS, kind: str | None = None) -> np.ndarray:
    """异常：结构上与单载波不同的谱形状（多载波/谐波梳/宽带/主峰+边带）。"""
    kind = kind or rng.choice(["multitone", "comb", "wideband", "sideband"])
    floor = 0.02 * rng.random(n)
    if kind == "multitone":
        # 3 个明显分离的峰（强制最小间隔，避免随机峰重叠退化成单峰）
        positions: list[float] = []
        while len(positions) < 3:
            c = float(rng.uniform(8, n - 8))
            if all(abs(c - p) >= 12 for p in positions):
                positions.append(c)
        x = floor.copy()
        for c in positions:
            x += float(rng.uniform(0.5, 0.9)) * _gaussian(n, c, float(rng.uniform(1.0, 2.0)))
        return x
    if kind == "comb":
        x = floor.copy()
        base = float(rng.uniform(6, n * 0.5))
        for k in range(7):
            c = base + k * (n // 16)
            if c < n - 1:
                x += float(rng.uniform(0.4, 0.7)) * _gaussian(n, c, 0.8)
        return x
    if kind == "wideband":
        x = floor.copy()
        x += 0.8 * _gaussian(n, n / 2.0, float(rng.uniform(n / 6.0, n / 4.0)))
        return x
    # sideband：主峰 + 强边带（干扰）
    x = floor.copy()
    c = float(rng.uniform(8, n - 8))
    x += 0.9 * _gaussian(n, c, 2.0)
    x += 0.7 * _gaussian(n, c + float(rng.uniform(15, 25)), 1.5)
    return x


# ============ 1. 嵌入 ============


def test_embed_normalizes_to_unit_interval():
    x = _gaussian(N_BINS, 64, 2.0) + 0.05
    e = saa.embed_spectrum(x, n_bins=48)
    assert e.shape == (48,)
    assert float(e.min()) >= 0.0 and float(e.max()) <= 1.0 + 1e-9
    assert float(e.max()) > 0.9  # 有峰，非平坦


def test_embed_flat_returns_zeros():
    assert np.allclose(saa.embed_spectrum(np.full(64, 3.0), 32), 0.0)


def test_embed_spectra_batch_shape():
    rng = np.random.default_rng(0)
    specs = [_normal_spectrum(rng) for _ in range(5)]
    X = saa.embed_spectra(specs, n_bins=32)
    assert X.shape == (5, 32)


def test_embed_rejects_bad_input():
    with pytest.raises(ValueError):
        saa.embed_spectrum(np.zeros(0))
    with pytest.raises(ValueError):
        saa.embed_spectrum(np.zeros((2, 10)))


# ============ 2. 隔离森林 ============


def test_isolation_forest_scores_and_reproducible():
    rng = np.random.default_rng(0)
    normals = np.stack([_normal_spectrum(rng) for _ in range(80)])
    X = saa.embed_spectra(normals, n_bins=32)
    f1 = saa.IsolationForest(n_estimators=50, seed=7).fit(X)
    f2 = saa.IsolationForest(n_estimators=50, seed=7).fit(X)
    s1 = f1.anomaly_scores(X)
    s2 = f2.anomaly_scores(X)
    assert np.allclose(s1, s2)  # 同种子可复现
    assert np.all((s1 > 0.0) & (s1 <= 1.0))


def test_isolation_forest_ranks_anomalies_higher():
    rng = np.random.default_rng(1)
    normals = [_normal_spectrum(rng) for _ in range(200)]
    anomalies = [_anomaly_spectrum(rng, kind=k) for k in ("multitone", "comb", "wideband", "sideband")] * 3
    specs = normals + anomalies
    X = saa.embed_spectra(specs, n_bins=48)
    scores = saa.IsolationForest(n_estimators=100, seed=3).fit(X).anomaly_scores(X)
    normal_mean = float(scores[:200].mean())
    anom_mean = float(scores[200:].mean())
    assert anom_mean > normal_mean


def test_isolation_forest_requires_fit():
    with pytest.raises(RuntimeError):
        saa.IsolationForest().anomaly_scores(np.ones((5, 8)))


# ============ 3. 规则评审 ============


def test_rule_reviewer_filters_empty_and_flat():
    rev = saa.RuleReviewer()
    assert rev.review(np.zeros(64)).accepted is False
    assert rev.review(np.full(64, 2.0)).accepted is False
    # 近平坦谱（微小抖动）→ 平坦度→1 → 噪声，过滤
    flat = np.full(64, 1.0) + 1e-3 * np.random.default_rng(0).random(64)
    assert rev.review(flat).accepted is False


def test_rule_reviewer_keeps_and_labels_suspicious():
    rev = saa.RuleReviewer()
    rng = np.random.default_rng(2)
    multi = _anomaly_spectrum(rng, kind="comb")
    v = rev.review(multi)
    assert v.accepted is True
    assert saa.RULE_MULTIPEAK in v.labels
    # 正常单载波保留且无可疑标签
    vn = rev.review(_normal_spectrum(rng))
    assert vn.accepted is True
    assert vn.labels == []


# ============ 4. 管线：命中率 + 降幅 ============


def test_screen_candidates_hit_rate_and_reduction():
    """合成异常注入：候选命中率 ≥80%，筛选量较全量扫描降 ≥10×。"""
    rng = np.random.default_rng(42)
    n_normal, n_anom = 300, 12
    specs = [_normal_spectrum(rng) for _ in range(n_normal)]
    # 12 个独立生成的异常（先展开元组再列表推导，避免 [..]*3 只复制同一批）
    specs += [_anomaly_spectrum(rng, kind=k) for k in ("multitone", "comb", "wideband", "sideband") * 3]
    anom_idx = set(range(n_normal, n_normal + n_anom))

    result = saa.screen_candidates(specs, n_bins=48, target_reduction=10.0, seed=7)

    assert result.n_total == n_normal + n_anom
    assert result.reduction >= 10.0
    assert result.n_candidates <= result.n_total // 10 + 1

    top = {c.index for c in result.candidates}
    hit = len(anom_idx & top)
    hit_rate = hit / n_anom
    assert hit_rate >= 0.8, f"命中率 {hit_rate:.2f} < 0.8（命中 {hit}/{n_anom}）"


def test_screen_candidates_rejects_empty():
    with pytest.raises(ValueError):
        saa.screen_candidates([])
    with pytest.raises(ValueError):
        saa.screen_candidates([np.zeros(64)], target_reduction=0)
