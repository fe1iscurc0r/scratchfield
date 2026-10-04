"""R48 验收测试：STRIPE 式统计滤波干扰识别（识别率 ≥85%，误报率 ≤5%）。

运行：python -m pytest mcpserver/rf_brain/test_rfi_statistical.py -q
"""
from __future__ import annotations

import numpy as np

from .rfi_statistical import StatisticalRFIDetector, StreamingRFIDetector

T, F, B = 120, 512, 16
SUB = F // B


def _scenario():
    """噪声底 + 两段持续干扰突发 + 两个单帧毛刺。"""
    rng = np.random.default_rng(0)
    db = np.full((T, F), -100.0) + rng.normal(0, 0.5, (T, F))
    truth = np.zeros((T, B), dtype=bool)

    def burst(bands, t0, t1, boost=35.0):
        for b in bands:
            db[t0:t1, b * SUB : (b + 1) * SUB] += boost
            truth[t0:t1, b] = True

    burst([2, 3], 30, 70)   # 持续干扰 1（40 帧）
    burst([9], 80, 110)     # 持续干扰 2（30 帧）
    # 单帧毛刺（应被时域累积过滤，不计入真值）
    db[20, 6 * SUB : 7 * SUB] += 35.0
    db[90, 12 * SUB : 13 * SUB] += 35.0
    return db, truth


def test_detect_shape():
    det = StatisticalRFIDetector(B)
    db, _ = _scenario()
    mask = det.detect(db)
    assert mask.shape == (T, B)
    assert mask.dtype == bool


def test_detect_1d_single_frame():
    det = StatisticalRFIDetector(B)
    db, _ = _scenario()
    mask = det.detect(db[0])
    assert mask.shape == (B,)


def test_acceptance_recall_and_false_alarm():
    det = StatisticalRFIDetector(B, sigma=4.0, persistence=3)
    db, truth = _scenario()
    pred = det.detect(db)
    recall = float(pred[truth].mean())
    fa = float(pred[~truth].mean())
    assert recall >= 0.85, f"识别率 {recall} 低于 85%"
    assert fa <= 0.05, f"误报率 {fa} 超过 5%"


def test_temporal_accumulation_removes_glitches():
    det = StatisticalRFIDetector(B, sigma=4.0, persistence=3)
    db, _ = _scenario()
    pred = det.detect(db)
    assert not pred[20, 6], "单帧毛刺未被时域累积过滤（frame 20）"
    assert not pred[90, 12], "单帧毛刺未被时域累积过滤（frame 90）"


def test_persistence_beats_no_persistence_on_false_alarm():
    """对比：不做时域累积的基线会把毛刺误报为干扰。"""
    det = StatisticalRFIDetector(B, sigma=4.0, persistence=3)
    db, truth = _scenario()
    with_persist = det.detect(db)
    no_persist = det.detect_no_persistence(db)
    fa_with = float(with_persist[~truth].mean())
    fa_without = float(no_persist[~truth].mean())
    # 累积版误报率必须不高于无累积基线
    assert fa_with <= fa_without
    # 无累积基线会把两个单帧毛刺误报
    assert no_persist[20, 6] and no_persist[90, 12]


def test_resource_estimate_esp32_compatible():
    det = StatisticalRFIDetector(B, persistence=3)
    est = det.estimate_resources()
    assert est.esp32_compatible
    assert est.state_bytes < 4096  # ESP32 级 RAM 预算
    assert est.ops_per_frame < 10_000


def test_bad_params_rejected():
    try:
        StatisticalRFIDetector(1)
        raised = False
    except ValueError:
        raised = True
    assert raised
    try:
        StatisticalRFIDetector(B, persistence=0)
        raised = False
    except ValueError:
        raised = True
    assert raised


# ---------- 流式（逐帧）检测 ----------


def test_streaming_acceptance_recall_and_false_alarm():
    """逐帧流式处理整段场景，验收口径与批处理一致。"""
    sd = StreamingRFIDetector(B, sigma=4.0, persistence=3, history=32)
    db, truth = _scenario()
    pred = np.zeros((T, B), dtype=bool)
    for t in range(T):
        pred[t] = sd.update(db[t])
    recall = float(pred[truth].mean())
    fa = float(pred[~truth].mean())
    assert recall >= 0.85, f"流式识别率 {recall} 低于 85%"
    assert fa <= 0.05, f"流式误报率 {fa} 超过 5%"


def test_streaming_removes_glitches_and_holds_long_burst():
    """毛刺被过滤；且长干扰突发（> 噪声窗口长度）不因噪声底漂移而中途丢检。"""
    sd = StreamingRFIDetector(B, sigma=4.0, persistence=3, history=32)
    db, truth = _scenario()
    pred = np.zeros((T, B), dtype=bool)
    for t in range(T):
        pred[t] = sd.update(db[t])
    assert not pred[20, 6] and not pred[90, 12], "单帧毛刺未被过滤"
    # 突发1 持续 40 帧（> history=32）：中后段（如 t=60）仍应检出
    assert pred[60, 2] and pred[60, 3], "长突发中途丢检（噪声底被污染）"
    assert pred[60, 2] == truth[60, 2]


def test_streaming_resource_esp32_compatible():
    sd = StreamingRFIDetector(B, persistence=3, history=32)
    est = sd.estimate_resources()
    assert est.esp32_compatible
    assert est.state_bytes < 4096
