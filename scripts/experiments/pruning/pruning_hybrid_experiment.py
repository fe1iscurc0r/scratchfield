"""临时实验：纯贪心 vs OBS vs 混合（贪心显著性 + OBS 补偿）

混合 = 用 leave-one-out 一阶残差增量选"删哪个"（贪心的准确显著性），
      删掉后用 OBS 的补偿更新 δw = -w_q·H⁻¹[:,q]/H⁻¹_qq 调整剩余权重。
目标：既有贪心在中低稀疏度的准确，又有 OBS 在极端稀疏度的补偿。
"""
import numpy as np

rng = np.random.default_rng(6)

n_h = 16
W1 = rng.normal(0, 1, (1, n_h)); b1 = rng.normal(0, 1, n_h)
W2 = rng.normal(0, 1, (n_h, 1)); b2 = rng.normal(0, 1, 1)
x = np.linspace(0, 1, 200).reshape(-1, 1)
u_true = np.sin(np.pi * x).ravel()
hx = x[1, 0] - x[0, 0]


def residual_vec(w):
    W1p = w[:n_h].reshape(1, n_h)
    W2p = w[n_h:].reshape(n_h, 1)
    h = np.tanh(x @ W1p + b1)
    u = (h @ W2p + b2).ravel()
    uxx = (u[2:] - 2 * u[1:-1] + u[:-2]) / hx ** 2
    return uxx + np.pi ** 2 * u[1:-1]


def resid_mse(w):
    R = residual_vec(w)
    return float(np.mean(R ** 2))


lr = 0.01
for _ in range(6000):
    h = np.tanh(x @ W1 + b1)
    u = (h @ W2 + b2).ravel()
    err = u - u_true
    g_W2 = h.T @ err.reshape(-1, 1) / len(x); g_b2 = err.mean()
    g_h = err.reshape(-1, 1) @ W2.T; g_z = g_h * (1 - h ** 2)
    g_W1 = x.T @ g_z / len(x); g_b1 = g_z.mean(0)
    W2 -= lr * g_W2; b2 -= lr * g_b2
    W1 -= lr * g_W1; b1 -= lr * g_b1

w0 = np.concatenate([W1.ravel(), W2.ravel()])
n_w = w0.size


def _pick_saliency(w, active, mode, Hinv=None, J=None, active_idx=None):
    """返回待移除权重索引（在 active 内的绝对下标）。"""
    if mode == "greedy":
        base = resid_mse(w)
        sal = {}
        for widx in active:
            orig = w[widx]
            w[widx] = 0.0
            sal[widx] = resid_mse(w) - base
            w[widx] = orig
        return min(sal, key=sal.get)
    else:  # obs 二阶显著性
        sal = {widx: w[widx] ** 2 / (2 * Hinv[j, j]) for j, widx in enumerate(active)}
        return min(sal, key=sal.get)


def prune(pick_mode, compensate):
    w = w0.copy()
    active = list(range(n_w))
    trace = [resid_mse(w)]
    eps = 1e-4
    lam = 1e-6
    while len(active) > 1:
        Hinv = None
        if pick_mode == "obs" or compensate:
            R0 = residual_vec(w)
            J = np.zeros((R0.size, len(active)))
            for j, widx in enumerate(active):
                w[widx] += eps
                J[:, j] = (residual_vec(w) - R0) / eps
                w[widx] -= eps
            H = J.T @ J + lam * np.eye(len(active))
            Hinv = np.linalg.inv(H)
        q = _pick_saliency(w, active, pick_mode, Hinv)
        qidx = active.index(q)
        if compensate:
            for j, widx in enumerate(active):
                if widx != q:
                    w[widx] -= w[q] * Hinv[j, qidx] / Hinv[qidx, qidx]
        w[q] = 0.0
        active.remove(q)
        trace.append(resid_mse(w))
    return trace


tr_greedy = prune("greedy", False)
tr_obs = prune("obs", True)
tr_hybrid = prune("greedy", True)   # 贪心选 + OBS 补偿

print(f"{'剪枝率':>6s} | {'纯贪心':>10s} | {'OBS':>10s} | {'混合':>10s}")
for pct in (0, 20, 40, 60, 80, 85, 90, 95):
    i = min(int(n_w * pct / 100), n_w)
    print(f"{pct:>5d}% | {tr_greedy[i]:>10.2f} | {tr_obs[i]:>10.2f} | {tr_hybrid[i]:>10.2f}")
