"""K线优先单原型测试（K33/K34/K35/K42/K46/K47/K48/K49/K50）。

运行：python -m pytest tools/test_k_priority_prototypes.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from k_priority_prototypes import (
    daei_invert,
    daei_naive_invert,
    daei_noise_sweep,
    daei_recovery_error,
    evisafe_score,
    gpu_kernel_verify,
    gumbel_verify,
    jacobian_quantize,
    oattention,
    proxyformer_compress,
    reconstruction_benchmark,
    tup_bon_distill,
)


def test_k33_daei_denoising_beats_naive_under_noise():
    """去噪感知嵌入反演在病态 W + 高斯噪声下恢复误差低于朴素 pinv（噪声保护不足）。"""
    rng = np.random.default_rng(0)
    dim, out = 8, 16
    # 病态 W：奇异值快速衰减 → 朴素 pinv 放大噪声
    U, _ = np.linalg.qr(rng.normal(0, 1, (out, dim)))
    V, _ = np.linalg.qr(rng.normal(0, 1, (dim, dim)))
    s = np.geomspace(1.0, 0.01, dim)
    W = U @ np.diag(s) @ V.T
    x = rng.normal(0, 1, dim)
    from k_priority_prototypes import _embed
    emb = _embed(x, W, noise_std=0.5, seed=1)
    err_naive = daei_recovery_error(x, daei_naive_invert(emb, W))
    err_daei = daei_recovery_error(x, daei_invert(emb, W, noise_std=0.5))
    assert err_daei < err_naive


def test_k33_daei_advantage_grows_with_noise():
    """噪声越大，去噪感知反演相对朴素 pinv 的优势越大（噪声保护随噪声被削弱）。"""
    rng = np.random.default_rng(0)
    dim, out = 8, 16
    U, _ = np.linalg.qr(rng.normal(0, 1, (out, dim)))
    V, _ = np.linalg.qr(rng.normal(0, 1, (dim, dim)))
    W = U @ np.diag(np.geomspace(1.0, 0.01, dim)) @ V.T
    x = rng.normal(0, 1, dim)
    levels = np.array([0.1, 0.3, 0.6, 1.0])
    errs_naive, errs_daei = daei_noise_sweep(x, W, levels, seed=0)
    # 各噪声水平下，去噪感知反演都更优
    assert np.all(errs_daei < errs_naive)
    # 优势（误差比 naive/daei）随噪声增大而增大
    ratio = errs_naive / errs_daei
    assert ratio[-1] > ratio[0]


def test_k34_tournament_beats_single_model():
    """锦标赛选优 match 率显著高于单模型（候选噪声足够大时）。"""
    rng = np.random.default_rng(0)
    n_ideas, n_refs, dim = 200, 5, 16
    ideas = rng.normal(0, 1, (n_ideas, dim))
    refs = ideas[:, None, :] + rng.normal(0, 0.05, (n_ideas, n_refs, dim))
    res = reconstruction_benchmark(ideas, refs, n_models=5, noise_std=0.5, seed=1)
    assert res["tournament_match_rate"] > res["single_model_match_rate"]
    assert res["tournament_match_rate"] - res["single_model_match_rate"] > 0.1


def test_k35_tup_bon_reward_higher():
    """TUP-BoN 蒸馏（截断+上尾重加权）奖励高于朴素平均。"""
    res = tup_bon_distill(n_samples=128, seed=0)
    assert res["tup_bon_reward"] > res["naive_reward"]


def test_k42_gumbel_verify_flags_exfiltration():
    """Gumbel 验证：可疑 token 概率集中 → 判为熵膨胀/越界；正常查询放行。"""
    logits = np.array([0.1, 0.2, 0.1, 5.0, 0.1])  # index 3 可疑
    normal = {0, 1, 2, 4}
    exfil = {3}
    assert gumbel_verify(logits, normal, exfil)["flagged"] is True
    logits_ok = np.array([2.0, 1.0, 0.5, 0.1, 0.1])
    assert gumbel_verify(logits_ok, normal, exfil)["flagged"] is False


def test_k46_oattention_masked_exact_zero():
    """OAttention：掩码 token 贡献精确为零，未掩码与标准注意力一致（重归一化）。"""
    rng = np.random.default_rng(0)
    q = rng.normal(0, 1, (2, 4))
    k = rng.normal(0, 1, (5, 4))
    v = rng.normal(0, 1, (5, 3))
    mask = np.array([1, 1, 0, 1, 1])
    out = oattention(q, k, v, mask)
    # 掩码 token（index 2）的注意力权重严格为 0 → 对输出无贡献
    scores = q @ k.T / np.sqrt(q.shape[1])
    scores = np.where(mask[None, :] == 1, scores, -np.inf)
    attn = np.exp(scores - scores.max(1, keepdims=True))
    attn /= attn.sum(1, keepdims=True)
    assert np.all(attn[:, 2] == 0.0)  # 精确零
    assert np.allclose(out, attn @ v)


def test_k47_gpu_kernel_verify_detects_bugs():
    """GPU 内核验证器：12 对抗门发现错误内核的问题。"""
    def good_kernel(a, b):
        return a @ b
    def bad_kernel(a, b):
        out = a @ b
        out[0, 0] += 1.0  # 注入 bug
        return out
    res_good = gpu_kernel_verify(good_kernel)
    res_bad = gpu_kernel_verify(bad_kernel)
    assert res_good["problems_found"] == 0
    assert res_bad["problems_found"] > 0
    assert res_good["gates"] == 12


def test_k48_jacobian_quantization_lower_error():
    """Jacobian 引导量化：平均输出误差显著低于标准均匀量化（统计增益）。"""
    std_errs, jac_errs = [], []
    for seed in range(30):
        rng = np.random.default_rng(seed)
        x = rng.normal(0, 1, 6)
        W = rng.normal(0, 1, (4, 6))
        res = jacobian_quantize(x, W, n_bits=4, seed=seed)
        std_errs.append(res["std_quant_error"])
        jac_errs.append(res["jacobian_quant_error"])
    assert np.mean(jac_errs) < np.mean(std_errs)


def test_k49_proxyformer_compresses_with_fidelity():
    """ProxyFormer：64× 压缩比下信息保真度仍高（结构化上下文）。"""
    rng = np.random.default_rng(0)
    n_clusters, per, dim = 8, 64, 8
    centers = rng.normal(0, 3, (n_clusters, dim))
    tokens = np.repeat(centers, per, axis=0) + rng.normal(0, 0.2, (n_clusters * per, dim))
    res = proxyformer_compress(tokens, n_proxy=8)
    assert res["compression_ratio"] == 64.0
    assert res["fidelity"] > 0.7


def test_k50_evisafe_catches_ungrounded():
    """EviSafe：证据锚定评测能抓住"回答对但证据缺失"的样本。"""
    responses = [
        {"safe": True, "evidence": True},
        {"safe": True, "evidence": False},  # 答案对但无据 → 最终回答漏判
        {"safe": False, "evidence": False},
    ]
    res = evisafe_score(responses)
    assert res["final_only_missed"] >= 1
    assert res["evidence_grounded_caught"] >= res["final_only_missed"]
