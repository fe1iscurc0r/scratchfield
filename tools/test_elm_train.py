# -*- coding: utf-8 -*-
"""OTA-ELM 训练骨架 pytest（01-01 验收：≥5 用例，覆盖训练/推理/导出/一致性）。

运行：cd tools && pytest -q
依赖：numpy、pytest（无 torch/tf，无 LLM 调用）。
"""

import elm_train as E
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# 固定的小型合成数据（保证测试确定性）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo():
    Xtr, ytr, Xte, yte, names = E.make_demo_dataset(n_per_class=200, seed=7)
    return Xtr, ytr, Xte, yte, names


@pytest.fixture(scope="module")
def trained(demo):
    Xtr, ytr, _, _, _ = demo
    model = E.ELM(n_hidden=48, projection="normal",
                  activation="lut_sigmoid", seed=7)
    model.fit(Xtr, ytr)
    return model


@pytest.fixture(scope="module")
def quantized(trained, demo):
    Xtr, _, _, _, _ = demo
    return trained.export_int8(Xtr)


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------

def test_float_demo_accuracy(demo, trained):
    """合成三类频谱特征，浮点 ELM 应高准确率（≥0.9）。"""
    _, _, Xte, yte, _ = demo
    assert trained.score(Xte, yte) >= 0.9


def test_binary_classification():
    """二分类也可训练（2 个输出，标签 0/1）。"""
    rng = np.random.default_rng(1)
    X = rng.standard_normal((200, E.N_FEATURES))
    # 线性可分：前两维和决定标签
    y = (X[:, 0] + X[:, 1] > 0).astype(np.int64)
    model = E.ELM(n_hidden=32, activation="sigmoid", seed=1)
    model.fit(X, y)
    assert model.beta.shape[1] == 2
    assert model.score(X, y) >= 0.9


def test_projection_normal_and_uniform(demo):
    """正态/均匀随机投影均可训练并收敛。"""
    Xtr, ytr, Xte, yte, _ = demo
    for proj in ("normal", "uniform"):
        model = E.ELM(n_hidden=32, projection=proj, seed=2)
        model.fit(Xtr, ytr)
        assert model.score(Xte, yte) >= 0.85


def test_activation_sigmoid_relu(demo):
    """sigmoid 与 relu 激活均可训练。relu 隐层非负。"""
    Xtr, ytr, Xte, yte, _ = demo
    model = E.ELM(n_hidden=32, activation="relu", seed=3)
    model.fit(Xtr, ytr)
    assert model.score(Xte, yte) >= 0.8
    H = model._activate(Xtr @ model.W + model.b)
    assert (H >= 0).all()


def test_demo_dataset_shapes(demo):
    """演示数据集维度与标签范围正确。"""
    Xtr, ytr, Xte, yte, names = demo
    assert Xtr.shape[1] == E.N_FEATURES
    assert len(names) == 3
    assert set(np.unique(ytr)) == {"A", "B", "C"}
    assert Xte.shape[0] + Xtr.shape[0] == 600
    assert names == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# LUT 构造与定点工具
# ---------------------------------------------------------------------------

def test_sigmoid_lut_sane():
    """sigmoid LUT 单调、中心为 0、输出落在 int8 范围。"""
    lut = E.build_sigmoid_lut(1.0 / 32.0)
    assert lut.dtype == np.int8
    assert lut.shape == (256,)
    assert lut[128] == 0                      # sigmoid(0)-0.5 = 0
    assert (np.diff(lut.astype(np.int32)) >= 0).all()  # 单调不减
    assert lut.min() >= -127 and lut.max() <= 127


def test_exp_neg_lut_sane():
    """softmax 指数 LUT：EN[0]=32767，单调递减，非负。"""
    lut = E.build_exp_neg_lut(1.0 / 32.0)
    assert lut.dtype == np.int16
    assert lut[0] == 32767
    assert (np.diff(lut.astype(np.int32)) <= 0).all()
    assert lut.min() >= 0


def test_best_mult_shift_quality():
    """定点重量化 (M,S) 逼近误差小，且 M 在 int32 范围内。"""
    for ratio in (0.001, 0.5, 1.0, 3.14159, 7.77, 120.0):
        M, S = E.best_mult_shift(ratio)
        assert 1 <= M < (1 << 31)
        assert abs(M / (1 << S) - ratio) / ratio < 1e-6


def test_requant_rounding():
    """requant 按「+half 后算术右移」量化（与固件 requant64 一致）。

    语义：y = (a*mult + (1<<(shift-1))) >> shift，对负值取 floor（算术移位）。
    mult=1, shift=1 → y = (a+1)>>1。
    """
    a = np.array([0, 1, 2, 3, -1, -2, -3], dtype=np.int64)
    y = E.requant(a, 1, 1)  # (a+1)>>1
    assert (y == np.array([0, 1, 1, 2, 0, -1, -1])).all()


# ---------------------------------------------------------------------------
# int8 定点导出与一致性（01-03 核心验收）
# ---------------------------------------------------------------------------

def test_int8_accuracy_close(demo, trained, quantized):
    """int8 定点准确率 ≥0.9，且与浮点差距 ≤0.05。"""
    _, _, Xte, yte, _ = demo
    acc_f = trained.score(Xte, yte)
    acc8 = quantized.score(Xte, yte)
    assert acc8 >= 0.9
    assert abs(acc8 - acc_f) <= 0.05


def test_int8_argmax_agreement(demo, trained, quantized):
    """浮点 vs int8 的 argmax 一致率 ≥0.95。"""
    _, _, Xte, _, _ = demo
    agree = float(np.mean(quantized.predict(Xte) == trained.predict(Xte)))
    assert agree >= 0.95


def test_softmax_permille_approx(demo, trained, quantized):
    """softmax LUT 近似误差（PC 浮点 vs int8 定点）≤ 阈值 0.05。

    标注阈值：0.05（最大绝对概率偏差，无量纲，取值范围 0~1）。
    """
    _, _, Xte, _, _ = demo
    p_f = trained.predict_proba(Xte)
    p8 = quantized.predict_proba(Xte)
    assert np.max(np.abs(p8 - p_f)) <= 0.05
    perm = quantized.predict_proba_permille(Xte)
    assert perm.min() >= 0 and perm.max() <= 1000
    # 行和≈1000：整数 floor 截断，每类最多丢 1，故总和 ∈ [1000-(no-1), 1000]
    assert (1000 - perm.sum(axis=1)).max() <= quantized.n_outputs - 1


# ---------------------------------------------------------------------------
# EBIN 导出 / 往返
# ---------------------------------------------------------------------------

def test_ebin_roundtrip(quantized, tmp_path):
    """EBIN 存→读 往返后，表与预测完全一致。"""
    p = tmp_path / "m.ebin"
    quantized.save_ebin(p)
    q2 = E.QuantizedELM.load_ebin(p)
    Xte = np.random.default_rng(0).standard_normal((20, E.N_FEATURES))
    assert (q2.predict(Xte) == quantized.predict(Xte)).all()
    assert (q2.W1_q == quantized.W1_q).all()
    assert (q2.sig_lut == quantized.sig_lut).all()
    assert (q2.OFF == quantized.OFF).all()


def test_ebin_header_fields(quantized, tmp_path):
    """EBIN 头部 magic/维度/尺度字段合法。"""
    p = tmp_path / "m.ebin"
    quantized.save_ebin(p)
    data = p.read_bytes()
    assert data[:4] == b"ELM1"
    assert data[4] == E.N_FEATURES                  # n_features u8
    assert int.from_bytes(data[5:7], "little") == quantized.n_hidden
    assert data[7] == quantized.n_outputs
    assert data[8] == E.ACT_LUT_SIGMOID
    for s in (quantized.s_x, quantized.s_w1, quantized.s_pre,
              quantized.s_h, quantized.s_b, quantized.s_logit):
        assert s > 0


def test_c_header_deterministic_and_complete(quantized, tmp_path):
    """C 头文件两次生成字节一致，且含关键符号。"""
    h1 = tmp_path / "a.h"
    h2 = tmp_path / "b.h"
    quantized.to_c_header(h1)
    quantized.to_c_header(h2)
    assert h1.read_text(encoding="utf-8") == h2.read_text(encoding="utf-8")
    text = h1.read_text(encoding="utf-8")
    for token in ("ELM_N_FEATURES", "ELM_W1_Q", "ELM_B1_Q", "ELM_B_Q",
                  "ELM_SIG_LUT", "ELM_EN_LUT", "ELM_OFF", "ELM_M1",
                  "ELM_S1", "ELM_M2", "ELM_S2", "ELM_CLASS_NAMES",
                  "ELM_X_A", "ELM_X_B"):
        assert token in text


def test_ebin_numeric_label_roundtrip(tmp_path):
    """数值类标签（int）经 EBIN 往返后 dtype 保持为整数。"""
    rng = np.random.default_rng(3)
    X = rng.standard_normal((160, E.N_FEATURES))
    y = (X[:, 0] > 0).astype(np.int64)  # 数值标签 {0,1}
    model = E.ELM(n_hidden=24, activation="lut_sigmoid", seed=3)
    model.fit(X, y)
    q = model.export_int8(X)
    p = tmp_path / "num.ebin"
    q.save_ebin(p)
    q2 = E.QuantizedELM.load_ebin(p)
    assert q2.classes.dtype.kind == "i"          # 整数，非字符串
    Xt = rng.standard_normal((10, E.N_FEATURES))
    assert (q2.predict(Xt) == q.predict(Xt)).all()


def test_feature_names_physical(demo):
    """特征层为物理量（SNR/包络/谱形），无平台专属量。"""
    _, _, _, _, names = demo
    assert E.FEATURE_NAMES[6] == "snr_db"
    assert "snr" in E.FEATURE_NAMES[6].lower()
    # 8 个特征全部为物理统计量（无 'platform'/'board' 等）
    assert all("platform" not in f and "board" not in f for f in E.FEATURE_NAMES)


def test_run_demo_export(tmp_path):
    """演示入口跑通并产出模型文件（验收：python tools/elm_train.py）。"""
    res = E.run_demo(n_per_class=100, n_hidden=32, seed=11,
                     out_ebin=str(tmp_path / "demo.ebin"),
                     out_header=str(tmp_path / "demo.h"))
    assert res["acc_float"] >= 0.9
    assert res["acc_int8"] >= 0.9
    assert res["softmax_max_abs_err"] <= 0.05
    assert (tmp_path / "demo.ebin").exists()
    assert (tmp_path / "demo.h").exists()
