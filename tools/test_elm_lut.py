# -*- coding: utf-8 -*-
"""AC-02 · OTA-ELM 查表推理 pytest（tools/elm_lut.py 契约测试）。

用例编号：
  E-01 tanh LUT 构建 + 量化误差上界
  E-02 黄金向量（x_q / LUT logits / 双路径预测，C++ 自测同源）
  E-03 float logits 重算一致
  E-04 精度差验收：|acc_float - acc_lut| ≤ 5%（工单验收线）
  E-05 训练决定论（同种子 → 权重/输出层逐位可复现）
  E-06 定点特征精确性（Q7 缩放全为 2 的幂 → 与手算移位逐位一致）
  E-07 镜像副本守卫
  E-08 C++ 头与 Python LUT 表逐项一致（跨语言资产一致性）
  E-09 基准数据打印（CPython 参考，非固件实测，不做阈值断言）
"""
import json
import random
import re
from pathlib import Path

import pytest
from elm_lut import (
    CLASS_N,
    FEATURE_DIM,
    HIDDEN,
    LUT_N,
    TANH_LUT,
    _draw_weights,
    _quantize_weights,
    argmax3,
    build_tanh_lut,
    elm_features_real,
    evaluate,
    infer_float,
    infer_lut,
    lut_error_table,
    make_mock_packet,
    quantize_x,
    train_elm,
)
from mulfree_features import abs_diffs_31, packet_window

REPO = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((REPO / "tools/elm_golden.json").read_text(encoding="utf-8"))

# 模块级训练一次（决定论用例 E-05 与黄金重算共用；同种子重训练逐位一致）
_TRAINED_CACHE = train_elm()


# ---- E-01 LUT 构建与误差 ----

class TestLut:
    def test_e01a_lut_shape_and_values(self):
        """E-01a 256 项、范围 [-127,127]、端点饱和 ±127（tanh(±4)≈±0.999）。"""
        lut = build_tanh_lut()
        assert len(lut) == LUT_N == 256
        assert all(-127 <= v <= 127 for v in lut)
        assert lut[0] == -127 and lut[255] == 127
        assert lut[128] == 0  # tanh(0)=0

    def test_e01b_quantization_error_bound(self):
        """E-01b 逐项激活误差 ≤0.02（理论界 0.0196，实测 ~0.0039）。"""
        import math
        err = lut_error_table()
        assert err["max_abs"] <= 0.02
        assert err["max_abs"] == pytest.approx(
            GOLDEN["lut_error"]["max_abs"], abs=1e-9)

    def test_e01c_monotone(self):
        """E-01c LUT 单调不减（tanh 单调的查表化身）。"""
        assert all(TANH_LUT[i] <= TANH_LUT[i + 1] for i in range(LUT_N - 1))


# ---- E-02/E-03 黄金向量 ----

class TestGolden:
    def test_e02a_golden_features_and_lut(self):
        """E-02a 黄金向量：定点特征与 LUT logits 逐位一致。"""
        assert len(GOLDEN["golden"]) == 12
        for g in GOLDEN["golden"]:
            pkt = bytes.fromhex(g["hex"])
            x_q = quantize_x(elm_features_real(pkt))
            assert x_q == g["x_q"]
            logits = infer_lut(x_q, *_fixed_out())
            assert logits == g["lut_logits"]

    def test_e02b_golden_predictions(self):
        """E-02b 双路径预测与 JSON 记录一致。"""
        for g in GOLDEN["golden"]:
            pkt = bytes.fromhex(g["hex"])
            feats = elm_features_real(pkt)
            assert argmax3(infer_float(feats, *_float_out())) == g["pred_float"]
            assert argmax3(infer_lut(quantize_x(feats), *_fixed_out())) == g["pred_lut"]

    def test_e03_float_logits_recompute(self):
        """E-03 float logits 重算一致（JSON 存 6 位小数，容差 1e-6）。"""
        for g in GOLDEN["golden"]:
            feats = elm_features_real(bytes.fromhex(g["hex"]))
            lf = infer_float(feats, *_float_out())
            for c in range(CLASS_N):
                assert lf[c] == pytest.approx(g["float_logits"][c], abs=1e-6)


def _fixed_out():
    return _TRAINED_CACHE[4], _TRAINED_CACHE[5], _TRAINED_CACHE[3]


def _float_out():
    return _TRAINED_CACHE[0], _TRAINED_CACHE[1], _TRAINED_CACHE[2]


# ---- E-04 精度差验收 ----

class TestAccuracy:
    def test_e04a_lut_vs_float_delta(self):
        """E-04a 工单验收线：LUT 与 float 测试精度差 ≤5%（同种子重跑）。"""
        W, b, Wout_f, Wout_q, W_q, b_q = _TRAINED_CACHE
        stats = evaluate(W, b, Wout_f, Wout_q, W_q, b_q)
        assert stats["acc_delta"] <= 0.05
        assert stats["acc_float"] == pytest.approx(
            GOLDEN["accuracy"]["acc_float"], abs=1e-9)
        assert stats["acc_lut"] == pytest.approx(
            GOLDEN["accuracy"]["acc_lut"], abs=1e-9)

    def test_e04b_confusion_recorded(self):
        """E-04b 混淆矩阵入库（README 表格数据源，150 = 3 类 × 50）。"""
        conf = GOLDEN["accuracy"]["confusion_lut"]
        assert sum(sum(row) for row in conf) == 150


# ---- E-05 训练决定论 ----

class TestDeterminism:
    def test_e05a_retrain_identical(self):
        """E-05a 重训练逐位一致（固定随机输入权重 + 解析解，无随机初始化漂移）。
        train_elm 返回 (W, b, Wout_f, Wout_q, W_q, b_q)。"""
        W, b, Wout_f, Wout_q, W_q, b_q = train_elm()
        assert W_q == _TRAINED_CACHE[4] and b_q == _TRAINED_CACHE[5]
        assert Wout_q == _TRAINED_CACHE[3]

    def test_e05b_weights_frozen_in_json_seeds(self):
        """E-05b 种子入档：权重种子/数据种子记录在案（可复现凭据）。"""
        assert GOLDEN["seeds"]["w"] == 20260902
        assert GOLDEN["seeds"]["golden"] == 20260901
        assert GOLDEN["hyper"]["hidden"] == HIDDEN == 32


# ---- E-06 定点特征精确性 ----

class TestQ7Features:
    def test_e06a_power_of_two_scaling_exact(self):
        """E-06a 所有特征缩放是 2 的幂 → quantize_x 无舍入损失（精确移位）。"""
        rng = random.Random(99)
        pkt = make_mock_packet(0, rng)
        ext, has_header, n = packet_window(pkt)
        absd = abs_diffs_31(ext)
        feats = elm_features_real(pkt)
        x_q = quantize_x(feats)
        # f0..f3 窗和 /16 → Q7 = 窗和<<3
        for j in range(4):
            base = j * 8
            s = sum(absd[base + i] for i in range(8) if base + i < 31)
            assert x_q[j] == s << 3
        # f6 len、f7 header
        assert x_q[6] == min(len(pkt), 255) << 7
        assert x_q[7] == (128 if pkt[:2] == b"\xD0\xCC" else 0)

    def test_e06b_int16_range(self):
        """E-06b 定点特征不溢出 int16（极端全 0xFF 包）。"""
        pkt = bytes([0xFF] * 120)
        assert all(-32768 <= v <= 32767 for v in quantize_x(elm_features_real(pkt)))


# ---- E-07 镜像副本守卫 ----

class TestMirrorSync:
    def test_e07a_demo_copies_identical(self):
        """E-07a 草图目录镜像副本与正本逐字节一致。"""
        base = REPO / "firmware/elm_lut"
        for name in ("elm_inference.h", "elm_inference.cpp", "elm_weights.h"):
            assert (base / "elm_lut_demo" / name).read_bytes() \
                == (base / name).read_bytes(), f"镜像副本漂移: {name}"


# ---- E-08 C++ 头与 Python LUT 一致 ----

class TestCrossLanguageAssets:
    def test_e08a_header_lut_matches_python(self):
        """E-08a 生成的 C++ 头中 ELM_TANH_LUT 与 Python TANH_LUT 逐项一致。"""
        text = (REPO / "firmware/elm_lut/elm_weights.h").read_text(encoding="utf-8")
        m = re.search(r"ELM_TANH_LUT\[256\] = \{(.*?)\};", text, re.S)
        assert m
        vals = [int(v) for v in re.findall(r"-?\d+", m.group(1))]
        assert vals == TANH_LUT

    def test_e08b_header_weight_dims(self):
        """E-08b 头文件维度声明与 Python 常量一致。"""
        text = (REPO / "firmware/elm_lut/elm_weights.h").read_text(encoding="utf-8")
        assert "#define ELM_FEATURE_DIM 8" in text
        assert f"#define ELM_HIDDEN {HIDDEN}" in text
        assert "#define ELM_H_SCALE 127" in text
        assert "ELM_W_Q[32][8]" in text
        assert "ELM_WOUT_Q[3][33]" in text


# ---- E-09 基准（打印用） ----

class TestBench:
    def test_bench_print_only(self):
        """基准参考：CPython ns/样本（非固件实测，S3 实测待真机）。"""
        import timeit
        rng = random.Random(7)
        pkt = make_mock_packet(0, rng)
        feats = elm_features_real(pkt)
        x_q = quantize_x(feats)
        W, b, Wout_f, Wout_q, W_q, b_q = _TRAINED_CACHE
        n = 2000
        t_l = timeit.timeit(lambda: infer_lut(x_q, W_q, b_q, Wout_q), number=n) / n
        t_f = timeit.timeit(lambda: infer_float(feats, W, b, Wout_f), number=n) / n
        print(f"\n[bench] LUT: {t_l * 1e9:.0f} ns/样本 | float: {t_f * 1e9:.0f} "
              f"ns/样本 (CPython 参考)")
        assert t_l > 0
