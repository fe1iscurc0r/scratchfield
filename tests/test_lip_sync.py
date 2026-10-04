"""唇形同步验收硬线（handcrafted 蒸馏批 W100-01）。"""
import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lumo.lip_sync.interpolator import (  # noqa: E402
    LipSyncSmoother,
    TimedPhoneme,
    build_timeline_from_words,
    ease_in_out_quad,
    lerp_pose,
)
from tools.lumo.lip_sync.pinyin_poses import NEUTRAL_POSE, all_phonemes, get_pose  # noqa: E402

_INITIAL_COUNT = 21
_FINAL_COUNT = 36


def test_pose_table_covers_pinyin():
    """口型表全拼音可查：声母 21 + 韵母 36 + SIL/停顿 + 整体认读。"""
    keys = set(all_phonemes())
    assert "SIL" in keys and "PAUSE" in keys
    for p in ("b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
              "j", "q", "x", "zh", "ch", "sh", "r", "z", "c", "s"):
        assert p in keys, f"缺声母 {p}"
    for f in ("a", "o", "e", "i", "u", "v", "ai", "ei", "ui", "ao", "ou",
              "iu", "ie", "ve", "er", "an", "en", "in", "un", "vn", "ang",
              "eng", "ing", "ong", "ia", "iao", "ian", "iang", "iong", "ua",
              "uo", "uai", "uan", "uang", "ueng", "van"):
        assert f in keys, f"缺韵母 {f}"


def test_pose_9_dims_and_unknown_fallback():
    """每个口型 9 维齐全；未知音素回落中性。"""
    for p in all_phonemes():
        pose = get_pose(p)
        assert set(pose.keys()) == set(NEUTRAL_POSE.keys()), p
        assert all(0.0 <= pose[k] <= 1.0 for k in ("MouthOpenY", "JawOpen", "MouthShrug", "MouthFunnel", "CheekPuff"))
        assert all(-1.0 <= pose[k] <= 1.0 for k in ("MouthForm", "MouthPuckerWiden", "MouthPressLipOpen", "MouthX"))
    assert get_pose("不存在的音素") == NEUTRAL_POSE


def test_ease_in_out_quad_bounds():
    """缓动函数端点与单调性。"""
    assert ease_in_out_quad(0.0) == 0.0 and ease_in_out_quad(1.0) == 1.0
    assert ease_in_out_quad(0.5) == 0.5
    vals = [ease_in_out_quad(t) for t in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert vals == sorted(vals)


def test_lerp_pose_endpoints():
    """逐维插值端点 = 两个姿态本身（浮点容差比较）。"""
    a, b = get_pose("a"), get_pose("u")
    lo, hi = lerp_pose(a, b, 0.0), lerp_pose(a, b, 1.0)
    for k in a:
        assert abs(lo[k] - a[k]) < 1e-9
        assert abs(hi[k] - b[k]) < 1e-9


def test_smoother_no_jump_on_step():
    """阶跃输入无跳变：跨音素后首帧不直接等于新目标（指数平滑逼近）。"""
    s = LipSyncSmoother()
    s.set_timeline([
        TimedPhoneme("SIL", 0.0, 0.5),
        TimedPhoneme("a", 0.5, 1.0),  # a 开口 0.75，与 SIL 差异大
    ])
    s.update(0.0, 1 / 60)
    s.update(0.4, 1 / 60)
    before = s.snapshot()
    out = s.update(0.55, 1 / 60)  # 刚跨入 a
    assert out["MouthOpenY"] > before["MouthOpenY"]  # 方向对
    assert out["MouthOpenY"] < 0.75  # 平滑逼近，非瞬间跳满


def test_smoother_returns_neutral_when_idle():
    """静止回归中性：无音素时持续逼近全零。"""
    s = LipSyncSmoother()
    s.set_timeline([TimedPhoneme("a", 0.0, 0.3), TimedPhoneme("SIL", 0.3, 10.0)])
    for t in (0.0, 0.1, 0.2):
        s.update(t, 1 / 60)
    for _ in range(120):  # 2 秒静音
        s.update(1.0 + 1 / 60, 1 / 60)
    pose = s.snapshot()
    assert abs(pose["MouthOpenY"]) < 0.05
    assert pose["CheekPuff"] == 0.0


def test_cheek_puff_fast_decay():
    """鼓腮快收：b 音素后进入静音，CheekPuff 快速衰减。"""
    s = LipSyncSmoother()
    s.set_timeline([TimedPhoneme("b", 0.0, 0.2), TimedPhoneme("SIL", 0.2, 10.0)])
    s.update(0.0, 0.05)
    s.update(0.1, 0.05)
    peak = s.snapshot()["CheekPuff"]
    assert peak > 0.1  # b 鼓腮已抬起
    for _ in range(10):
        s.update(0.4, 0.05)
    assert s.snapshot()["CheekPuff"] < peak * 0.5  # 快衰减


def test_timeline_driven_continuous_sequence():
    """播放进度回调驱动：1s 音频产生连续 9 维参数序列（帧帧可查）。"""
    words = [{"phonemes": "ni3hao3shi4jie4", "start": 0.0, "end": 1.0}]
    timeline = build_timeline_from_words(words)
    assert len(timeline) > 4  # 音素均分展开（数字被忽略）
    s = LipSyncSmoother()
    s.set_timeline(timeline)
    frames = []
    t = 0.0
    while t < 1.0:
        frames.append(s.update(t, 1 / 60))
        t += 1 / 60
    assert len(frames) == 60
    for f in frames:
        assert set(f.keys()) == set(NEUTRAL_POSE.keys())


def test_word_to_phoneme_ignores_stress_marks():
    """词级→音素级均分，且忽略重音/音长符号。"""
    words = [{"phonemes": "ˈhɛˌloʊ", "start": 0.0, "end": 0.3}]
    timeline = build_timeline_from_words(words)
    assert len(timeline) == 5  # h ɛ l o ʊ（忽略 ˈˌ）
    assert timeline[-1].end <= 0.3 + 1e-9
