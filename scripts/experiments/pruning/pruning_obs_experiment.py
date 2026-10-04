"""临时实验：纯贪心 vs OBS（二阶 + 权重补偿），看高稀疏度（80~95%）谁更好

OBS (Optimal Brain Surgeon, Hassibi & Stork 1992) 是贪心剪枝的"升级版"：
- 贪心：leave-one-out 一阶残差增量，移除最小贡献权重，无补偿。
- OBS：二阶显著性 s_q = w_q² / (2[H⁻¹]_qq)（Gauss-Newton Hessian H = JᵀJ），
  移除权重后对剩余权重做补偿更新 δw = -w_q·H⁻¹[:,q]/H⁻¹_qq，显式建模交互。
"""
import numpy as np

rng = np.random.default_rng(6)

n_in, n_h, n_out = 1, 16, 1
W1 = rng.normal(0, 1, (1, 16)); b1 = rng.normal(0, 1, 16)
W2 = rng.normal(0, 1, (16, 1)); b2 = rng.normal(0, 1, 1)
x = np.linspace(0, 1, 200).reshape(-1, 1)
u_true = np.sin(np.pi * x).ravel()
hx = x[1, 0] - x[0, 0]


def forward(W1, b1, W2, b2):
    h = np.tanh(x @ W1 + b1)
    return h, (h @ W2 + b2).ravel()


def residual_vec(w):
    """给定扁平权重 w（前 16 = W1，后 16 = W2），返回残差向量（198 维）。"""
    W1p = w[:16].reshape(1, 16)
    W2p = w[16:].reshape(16, 1)
    h = np.tanh(x @ W1p + b1)
    u = (h @ W2p + b2).ravel()
    uxx = (u[2:] - 2 * u[1:-1] + u[:-2]) / hx ** 2
    return uxx + np.pi ** 2 * u[1:-1]


def resid_mse(w):
    R = residual_vec(w)
    return float(np.mean(R ** 2))


# 训练拟合 u = sin(πx)
lr = 0.01
for _ in range(6000):
    h, u = forward(W1, b1, W2, b2)
    err = u - u_true
    g_W2 = h.T @ err.reshape(-1, 1) / len(x); g_b2 = err.mean()
    g_h = err.reshape(-1, 1) @ W2.T; g_z = g_h * (1 - h ** 2)
    g_W1 = x.T @ g_z / len(x); g_b1 = g_z.mean(0)
    W2 -= lr * g_W2; b2 -= lr * g_b2
    W1 -= lr * g_W1; b1 -= lr * g_b1

w0 = np.concatenate([W1.ravel(), W2.ravel()])   # 32 维
n_w = w0.size

# ---- 纯贪心（迭代 leave-one-out，无补偿）----
def greedy_prune():
    w = w0.copy()
    active = list(range(n_w))
    trace = [resid_mse(w)]
    while len(active) > 1:
        base = resid_mse(w)
        sal = {}
        for widx in active:
            orig = w[widx]
            w[widx] = 0.0
            sal[widx] = resid_mse(w) - base
            w[widx] = orig
        q = min(sal, key=sal.get)
        w[q] = 0.0
        active.remove(q)
        trace.append(resid_mse(w))
    return trace


# ---- OBS（二阶 + 补偿）----
def obs_prune():
    w = w0.copy()
    active = list(range(n_w))
    trace = [resid_mse(w)]
    eps = 1e-4
    lam = 1e-6
    while len(active) > 1:
        R0 = residual_vec(w)
        J = np.zeros((R0.size, len(active)))
        for j, widx in enumerate(active):
            w[widx] += eps
            J[:, j] = (residual_vec(w) - R0) / eps
            w[widx] -= eps
        H = J.T @ J + lam * np.eye(len(active))
        Hinv = np.linalg.inv(H)
        sal = {widx: w[widx] ** 2 / (2 * Hinv[j, j]) for j, widx in enumerate(active)}
        q = min(sal, key=sal.get)
        qidx = active.index(q)
        for j, widx in enumerate(active):
            if widx != q:
                w[widx] -= w[q] * Hinv[j, qidx] / Hinv[qidx, qidx]   # 补偿
        w[q] = 0.0
        active.remove(q)
        trace.append(resid_mse(w))
    return trace


tr_greedy = greedy_prune()
tr_obs = obs_prune()

print(f"{'剪枝率':>6s} | {'纯贪心 残差':>13s} | {'OBS 残差':>13s}")
for pct in (0, 20, 40, 60, 80, 85, 90, 95):
    i = min(int(n_w * pct / 100), n_w)
    print(f"{pct:>5d}% | {tr_greedy[i]:>13.2f} | {tr_obs[i]:>13.2f}")
