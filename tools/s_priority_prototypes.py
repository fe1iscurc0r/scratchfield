"""S 线优先单防御原型（S149/S157/S167/S169/S173）——第九批安全卷

来源：第九批 round4 全量扩编（UPGRADE-PROJECTS-9）。本模块把 5 个"重要 S 线单"的
核心机制各做一个**最小防御/分析原型**（只写检测/防御/鲁棒性，不写攻击 PoC），
每个对应可量化验收（见 test_s_priority_prototypes.py）。

五个原型：
  S149 网络化 Lotto 防御   多资源防御分配（General Lotto 均衡）——价值比例分配优于均匀
  S157 ARMOR              流形导向对抗训练（背景遮罩+目标 patch）——低数据下鲁棒性更高
  S167 Ouroboros 检测      自指涉后门检测（干净探针偏差一致性）
  S169 SAE 后门特征钳制    稀疏自编码器定位后门特征四类角色 + 钳制降 ASR
  S173 ZK 见证注入检查     对抗见证注入发现缺失约束（防御性 bug-finding）
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "lotto_defense",
    "lotto_optimality",
    "armor_robustness",
    "ouroboros_detect",
    "sae_backdoor_clamp",
    "zk_witness_check",
]


# ============ S149 网络化 Lotto 防御 ============

def _largest_remainder(values: np.ndarray, tokens: int) -> np.ndarray:
    """最大余数法按价值比例精确分配 token（不浪费，sum = tokens）。"""
    values = np.asarray(values, dtype=float)
    exact = tokens * values / values.sum()
    base = np.floor(exact).astype(int)
    rem = tokens - base.sum()
    frac = exact - base
    # 余数最大的 rem 个目标各补 1
    for i in np.argsort(-frac)[:rem]:
        base[i] += 1
    return base


def lotto_defense(values: np.ndarray, defender_tokens: int, attacker_tokens: int) -> dict:
    """General Lotto 多资源防御分配（均衡 vs 均匀）。

    values: N 个防御目标的价值；defender/attacker 各有多少 token。
    均衡策略 = 按价值比例分配防御 token（最大余数法，不浪费 token）；攻击者同样按
    价值比例（最坏情形）。损失 = Σ value[i] · 1[attack[i] > defense[i]]。
    """
    values = np.asarray(values, dtype=float)
    N = values.size
    prop = values / values.sum()

    defense_eq = _largest_remainder(values, defender_tokens)
    defense_uniform = _largest_remainder(np.ones(N), defender_tokens)  # 均匀=等值比例
    attack = _largest_remainder(values, attacker_tokens)

    def _loss(d):
        lost = attack > d
        return float((values * lost).sum())

    eq_loss = _loss(defense_eq)
    unif_loss = _loss(defense_uniform)
    return {
        "uniform_loss": unif_loss,
        "equilibrium_loss": eq_loss,
        "loss_reduction": unif_loss - eq_loss,
        "tokens_allocated": int(defense_eq.sum()),
    }


def lotto_optimality(values: np.ndarray, defender_tokens: int, attacker_tokens: int) -> bool:
    """验证价值比例分配在若干朴素备选策略中期望损失最小（均衡最优性）。"""
    values = np.asarray(values, dtype=float)
    N = values.size
    attack = _largest_remainder(values, attacker_tokens)

    def _loss(d):
        return float((values * (attack > d)).sum())

    prop = _largest_remainder(values, defender_tokens)
    candidates = [
        prop,                                     # 价值比例（均衡）
        _largest_remainder(np.ones(N), defender_tokens),  # 均匀
        np.zeros(N, dtype=int),                    # 不防御（下界参考）
    ]
    # 随机偏斜：按随机"伪价值"向量分配（错误的分配依据）应不优于按真实价值分配
    rng = np.random.default_rng(0)
    for _ in range(20):
        pseudo = rng.random(N) + 0.1
        candidates.append(_largest_remainder(pseudo, defender_tokens))
    losses = [_loss(d) for d in candidates]
    return _loss(prop) <= min(losses)


# ============ S157 ARMOR 流形导向对抗训练 ============

def _patch_augment(X: np.ndarray, patch_frac: float = 0.2, seed: int = 0) -> np.ndarray:
    """背景遮罩 + 目标上随机 patch 注入（沿数据流形的增强，而非全图噪声）。"""
    rng = np.random.default_rng(seed)
    Xa = X.copy()
    n, d = X.shape
    for i in range(n):
        k = max(1, int(d * patch_frac))
        idx = rng.choice(d, k, replace=False)
        Xa[i, idx] += rng.normal(0.0, 0.3, k)  # 只在局部 patch 注入
    return Xa


def armor_robustness(X: np.ndarray, y: np.ndarray, n_train: int = 8, seed: int = 0) -> dict:
    """ARMOR 流形导向训练 vs 标准训练的低数据对抗鲁棒性对比。

    二分类 2D 数据；标准 = 最小二乘线性分类器；ARMOR = 用 patch 增强后训练。
    鲁棒性 = 在对抗扰动（小幅度最坏方向）下的准确率。
    """
    rng = np.random.default_rng(seed)
    # 生成两类数据（少样本）
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)

    # 线性分类器（增广截距）
    def fit(Xt, yt):
        Xb = np.hstack([Xt, np.ones((Xt.shape[0], 1))])
        w = np.linalg.lstsq(Xb, yt, rcond=None)[0]
        return w

    def acc(w, Xt, yt):
        Xb = np.hstack([Xt, np.ones((Xt.shape[0], 1))])
        pred = (Xb @ w) >= 0.5
        return float(np.mean((pred.astype(float)) == yt))

    idx = rng.permutation(len(X))
    tr, te = idx[:n_train], idx[n_train:]

    w_std = fit(X[tr], y[tr])
    w_armor = fit(_patch_augment(X[tr], seed=seed), y[tr])

    # 对抗扰动：沿决策边界法向的最坏小扰动
    def adv_acc(w):
        wb = w[:-1]
        Xte = X[te]
        # 最坏扰动方向 = 权重法向（符号使样本跨边界）
        pert = 0.15 * wb / (np.linalg.norm(wb) + 1e-9)
        Xadv = Xte - np.sign(wb @ Xte.T).reshape(-1, 1) * pert
        return acc(w, Xadv, y[te])

    return {"std_adv_acc": adv_acc(w_std), "armor_adv_acc": adv_acc(w_armor)}


# ============ S167 Ouroboros 自指涉后门检测 ============

def ouroboros_detect(model, probes: np.ndarray, threshold: float = 0.1) -> dict:
    """自指涉后门检测：干净探针上 ‖model(x)−x‖ 的异常一致性。

    自指涉后门用"清洁音频"作触发器，后门模型在触发探针上输出攻击者内容（偏离身份映射
    identity），而干净增强模型对干净输入≈恒等。检测 = 最大干净偏差超阈值。
    """
    devs = np.array([float(np.linalg.norm(model(p) - p)) for p in probes])
    return {
        "max_deviation": float(devs.max()),
        "flagged": bool(devs.max() > threshold),
    }


# ============ S169 SAE 后门特征钳制 ============

def sae_backdoor_clamp(W: np.ndarray, trigger: np.ndarray, clean_x: np.ndarray) -> dict:
    """稀疏自编码器式后门特征定位 + 钳制（防御）。

    W: 线性层权重 (out, in)；trigger: 后门触发输入；clean_x: 干净输入。
    后门特征 = 输入空间中 trigger 相对干净均值的差异方向（稀疏特征）；钳制 = 把该
    输入方向从 W 投影掉（置零该特征）。期望：触发恶意输出（ASR）大幅下降，而干净
    输入（与触发方向近乎正交）输出几乎不变——特征钳制的稀疏性。
    """
    W = np.asarray(W, dtype=float)
    trigger = np.asarray(trigger, dtype=float)
    clean_x = np.asarray(clean_x, dtype=float)
    # 后门特征方向（输入空间）= trigger 方向，归一化（稀疏特征）
    t = trigger / (np.linalg.norm(trigger) + 1e-9)
    # 特征钳制：输入空间投影掉 t 方向（后门特征置零）
    W_clamped = W @ (np.eye(t.size) - np.outer(t, t))

    def asr(W_):
        return float(np.linalg.norm(W_ @ trigger))

    # 干净输出变化：钳制前后对干净输入的输出平均相对变化（应小幅有界）
    before = clean_x @ W.T
    after = clean_x @ W_clamped.T
    rel = np.linalg.norm(before - after, axis=1) / (np.linalg.norm(before, axis=1) + 1e-9)
    clean_change_ratio = float(np.mean(rel))

    return {
        "asr_before": asr(W),
        "asr_after": asr(W_clamped),
        "clean_change_ratio": clean_change_ratio,
    }


# ============ S173 ZK 见证注入检查 ============

def zk_witness_check(
    constraint, property_check, candidate_values: np.ndarray
) -> dict:
    """对抗见证注入检查缺失约束（防御性 bug-finding）。

    constraint: 已声明约束（callable，True 表示满足）；property_check: 应有但可能
    漏声明的性质（callable）；candidate_values: 候选见证值集合。
    若存在"满足 constraint 但违反 property_check"的见证 → 说明漏了约束（bug）。
    """
    violations = []
    for v in candidate_values:
        if constraint(v) and not property_check(v):
            violations.append(v)
    return {"missing_constraint_found": len(violations) > 0, "n_bugs": len(violations)}
