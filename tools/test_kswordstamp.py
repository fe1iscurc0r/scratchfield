"""kswordstamp 测试（S25 验收：水印机制对比 + 顺序鲁棒性）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from kswordstamp import (
    attack_rearrange,
    attack_resegment,
    attack_rewrite,
    detect_content,
    detect_position,
    embed_content,
    embed_position,
    run_eval,
)


def test_content_watermark_survives_rearrange():
    text = embed_content("a. b. c. d. e. f. g. h.")
    assert detect_content(attack_rearrange(text)) >= 0.9


def test_position_watermark_broken_by_rearrange():
    text = embed_position("a. b. c. d. e. f. g. h.")
    assert detect_position(attack_rearrange(text)) < 0.6


def test_content_watermark_more_robust_under_rearrange():
    """重排下，k-SwordStamp（内容水印）应显著优于顺序水印——这是核心对比。"""
    for r in run_eval(seed=0)["results"]:
        if r["attack"] == "rearrange":
            assert r["content_watermark"] > r["position_watermark"], r


def test_rewrite_degrades_both_but_not_catastrophically():
    text = embed_content("a. b. c. d. e. f. g. h.")
    det = detect_content(attack_rewrite(text, 0.5))
    assert 0.3 <= det <= 0.9  # 改写会破坏部分水印，但不会全灭
