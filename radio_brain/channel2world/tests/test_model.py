"""T2 模型骨架单测（≥6 用例）。

覆盖验收点：
1. 变长集合 → 固定 Kz×Dm = 16×128 嵌入（输入形状断言）
2. 置换不变性（打乱 context 顺序输出不变）
3. 三头输出形状（per-path GMM / 增益回归 / per-channel GMM）
4. 误差注入开关
5. loss 计算正确性（GMM NLL 闭式 + 总损失分解）
6. checkpoint 保存/加载
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import torch

from radio_brain.channel2world.model.dataset import Channel2WorldDataset, DatasetConfig, FEATURE_DIM
from radio_brain.channel2world.model.encoder import Channel2WorldModel, PerceiverEncoder
from radio_brain.channel2world.model.losses import compute_losses, gaussian_mixture_nll, total_loss


def _small_model(**kw) -> Channel2WorldModel:
    return Channel2WorldModel(
        d_in=FEATURE_DIM, d_model=32, kz=8, heads=2, encoder_layers=2,
        query_cross_layers=2, query_self_layers=1, n_components=2, **kw,
    )


def _make_hdf5(tmp_path, n_bs=2, n_ue=2, max_paths=12):
    """造一个最小 HDF5（对齐 T1 schema）。"""
    import h5py

    rng = np.random.default_rng(0)
    path = tmp_path / "tiny.h5"
    with h5py.File(path, "w") as f:
        g = f.create_group("scene_000")
        g.create_dataset("bs_position", data=rng.uniform(0, 60, size=(n_bs, 3)).astype(np.float32))
        ue = np.empty((n_bs, n_ue, 3), dtype=np.float32)
        ue[:, :, 0] = rng.uniform(2, 50, size=(n_bs, n_ue))
        ue[:, :, 1] = rng.uniform(2, 80, size=(n_bs, n_ue))
        ue[:, :, 2] = 1.5
        g.create_dataset("ue_position", data=ue)
        g.create_dataset("num_paths", data=np.full((n_bs, n_ue), max_paths, dtype=np.int32))
        g.create_dataset("tau_rel", data=rng.uniform(0, 1.3e-7, size=(n_bs, n_ue, max_paths)).astype(np.float32))
        g.create_dataset("aoa_theta", data=rng.uniform(0, np.pi, size=(n_bs, n_ue, max_paths)).astype(np.float32))
        g.create_dataset("aoa_phi", data=rng.uniform(0, 2 * np.pi, size=(n_bs, n_ue, max_paths)).astype(np.float32))
        g.create_dataset("gain_rel", data=rng.uniform(-26, 0, size=(n_bs, n_ue, max_paths)).astype(np.float32))
    return path


# ---------------------------------------------------------------------------
# 1. 变长集合 → 固定 16×128 嵌入
# ---------------------------------------------------------------------------


def test_encoder_variable_set_to_fixed_latent():
    enc = PerceiverEncoder(d_model=128, kz=16, heads=4, layers=6)
    for n in (3, 7, 20):
        x = torch.randn(2, n, 128)
        out = enc(x)
        assert out.shape == (2, 16, 128), f"变长 N={n} 未输出固定 16×128，实际 {out.shape}"


# ---------------------------------------------------------------------------
# 2. 置换不变性
# ---------------------------------------------------------------------------


def test_encoder_permutation_invariance():
    enc = PerceiverEncoder(d_model=64, kz=8, heads=4, layers=3)
    b, n, d = 2, 9, 64
    x = torch.randn(b, n, d)
    mask = torch.tensor([[True] * 6 + [False] * 3, [True] * 9])
    perm = torch.randperm(n)
    x_perm = x[:, perm, :]
    mask_perm = mask[:, perm]
    out = enc(x, mask)
    out_perm = enc(x_perm, mask_perm)
    assert torch.allclose(out, out_perm, atol=1e-4), "置换 context 顺序后嵌入应不变"


# ---------------------------------------------------------------------------
# 3. 三头输出形状
# ---------------------------------------------------------------------------


def test_three_head_output_shapes():
    model = _small_model()
    b, m, nch = 2, 24, 8
    ctx = torch.randn(b, 30, FEATURE_DIM)
    ctx_mask = torch.ones(b, 30, dtype=torch.bool)
    q = torch.randn(b, m, FEATURE_DIM)
    q_mask = torch.ones(b, m, dtype=torch.bool)
    ch_idx = torch.arange(nch).repeat(3).unsqueeze(0).expand(b, -1)  # (B, M) 每信道 3 路径

    out = model(ctx, ctx_mask, q, q_mask, ch_idx)

    assert out["latent"].shape == (b, 8, 32)
    assert out["path_gmm"]["means"].shape == (b, m, 2, 3)
    assert out["path_gmm"]["log_scales"].shape == (b, m, 2)
    assert out["path_gmm"]["logits"].shape == (b, m, 2)
    assert out["gain"].shape == (b, m, 1)
    assert out["ch_gmm"]["means"].shape == (b, nch, 2, 3)
    assert out["ch_gmm"]["log_scales"].shape == (b, nch, 2)
    assert out["ch_gmm"]["logits"].shape == (b, nch, 2)


# ---------------------------------------------------------------------------
# 4. 误差注入开关 + query 掩码
# ---------------------------------------------------------------------------


def test_error_injection_toggle(tmp_path):
    h5 = _make_hdf5(tmp_path)
    base = dict(hdf5_path=str(h5), context_size=2, query_size=2, num_splits=1, seed=0)
    ds_off = Channel2WorldDataset(DatasetConfig(**base, error_injection=False))
    ds_on = Channel2WorldDataset(DatasetConfig(**base, error_injection=True))

    ch = ds_off.channels[0]
    # 开关关闭：context 特征无噪声；开关打开：tau/增益被注入噪声
    f_off = ds_off._features(ch, is_context=True)
    f_on = ds_on._features(ch, is_context=True)
    assert f_off.shape == (12, FEATURE_DIM)
    assert not np.allclose(f_off[:, 0], f_on[:, 0]), "误差注入未改变时延特征"
    assert not np.allclose(f_off[:, 5], f_on[:, 5]), "误差注入未改变增益特征"

    # query：部分观测，增益(第 5 维)与位置(第 6-8 维)恒置零
    f_q = ds_off._features(ch, is_context=False)
    assert np.all(f_q[:, 5] == 0.0) and np.all(f_q[:, 6:9] == 0.0), "query 应掩码增益与位置"


def test_dataset_shapes_and_channel_index(tmp_path):
    h5 = _make_hdf5(tmp_path, n_bs=3, n_ue=3)  # 9 信道
    ds = Channel2WorldDataset(DatasetConfig(hdf5_path=str(h5), context_size=4, query_size=3, num_splits=2, seed=1))
    assert ds.n_channels == 9
    item = ds[0]
    assert item["context_x"].shape == (4 * 12, FEATURE_DIM)
    assert item["query_x"].shape == (3 * 12, FEATURE_DIM)
    assert item["channel_index"].shape == (3 * 12,)
    assert item["channel_index"].min() == 0 and item["channel_index"].max() == 2
    assert item["ch_pos_target"].shape == (3, 3)


# ---------------------------------------------------------------------------
# 5. loss 计算正确性
# ---------------------------------------------------------------------------


def test_gmm_nll_single_component_closed_form():
    means = torch.tensor([[[1.0, 2.0, 3.0]]])  # (1,1,3) C=1, D=3
    log_scales = torch.zeros(1, 1)  # σ=1
    logits = torch.zeros(1, 1)
    target = torch.tensor([[1.5, 2.0, 3.0]])
    nll = gaussian_mixture_nll(means, log_scales, logits, target)
    expected = 1.5 * math.log(2.0 * math.pi) + 0.125
    assert torch.allclose(nll, torch.tensor(expected), atol=1e-5)


def test_total_loss_decomposition():
    b, m, c, d = 1, 3, 2, 3
    outputs = {
        "path_gmm": {
            "means": torch.randn(b, m, c, d),
            "log_scales": torch.randn(b, m, c),
            "logits": torch.randn(b, m, c),
        },
        "gain": torch.randn(b, m, 1),
        "ch_gmm": {
            "means": torch.randn(b, 2, c, d),
            "log_scales": torch.randn(b, 2, c),
            "logits": torch.randn(b, 2, c),
        },
    }
    path_target = torch.randn(b, m, d)
    gain_target = torch.randn(b, m, 1)
    ch_target = torch.randn(b, 2, d)
    mask = torch.ones(b, m, dtype=torch.bool)

    total, comps = compute_losses(outputs, path_target, gain_target, ch_target, path_mask=mask)
    expected = comps["path_pos"] + 0.1 * comps["gain"] + 0.5 * comps["ch_pos"]
    assert torch.allclose(total, expected, atol=1e-5)

    t2 = total_loss(outputs, path_target, gain_target, ch_target, path_mask=mask)
    assert torch.allclose(total, t2, atol=1e-6)


# ---------------------------------------------------------------------------
# 6. checkpoint 保存/加载
# ---------------------------------------------------------------------------


def test_checkpoint_save_load(tmp_path):
    model = _small_model()
    b, m = 2, 12
    ctx = torch.randn(b, 20, FEATURE_DIM)
    ctx_mask = torch.ones(b, 20, dtype=torch.bool)
    q = torch.randn(b, m, FEATURE_DIM)
    q_mask = torch.ones(b, m, dtype=torch.bool)
    ch_idx = torch.zeros(b, m, dtype=torch.long)

    model.eval()
    with torch.no_grad():
        out_a = model(ctx, ctx_mask, q, q_mask, ch_idx)

    ckpt = tmp_path / "model.pt"
    torch.save({"model_state": model.state_dict(), "n_params": model.num_parameters()}, ckpt)

    model2 = _small_model()
    state = torch.load(ckpt, map_location="cpu")
    model2.load_state_dict(state["model_state"])
    model2.eval()
    with torch.no_grad():
        out_b = model2(ctx, ctx_mask, q, q_mask, ch_idx)

    assert torch.allclose(out_a["latent"], out_b["latent"], atol=1e-6)
    assert torch.allclose(out_a["gain"], out_b["gain"], atol=1e-6)


# ---------------------------------------------------------------------------
# 7. 参数量报告（~9.2M 参考，不强制精确）
# ---------------------------------------------------------------------------


def test_param_count_reported():
    model = Channel2WorldModel()  # 默认 128/16/4
    n = model.num_parameters()
    assert n > 1_000_000, "默认模型参数量应 > 1M"
    print(f"\n默认模型参数量: {n:,}")
