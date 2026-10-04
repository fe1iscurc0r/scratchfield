"""临时实验：纯贪心 vs 贪心+重训（每剪一个权重后重训几步，让剩余权重补偿）

"贪心+重训" = 迭代剪枝 + 剪后微调（prune-then-finetune / Lottery Ticket 的核心）。
"""
import numpy as np

rng = np.random.default_rng(6)

n_h = 16
W1 = rng.normal(0, 1, (1, n_h)); b1 = rng.normal(0, 1, n_h)
W2 = rng.normal(0, 1, (n_h, 1)); b2 = rng.normal(0, 1, 1)
x = np.linspace(0, 1, 200).reshape(-1, 1)
u_true = np.sin(np.pi * x).ravel()
hx = x[1, 0] - x[0, 0]


def forward(W1, b1, W2, b2):
    h = np.tanh(x @ W1 + b1)
    return h, (h @ W2 + b2).ravel()


def residual_mse(W1, b1, W2, b2):
    _, u = forward(W1, b1, W2, b2)
    uxx = (u[2:] - 2 * u[1:-1] + u[:-2]) / hx ** 2
    R = uxx + np.pi ** 2 * u[1:-1]
    return float(np.mean(R ** 2))


def fit_step(W1, b1, W2, b2, mask, lr=0.01):
    """一步梯度下降，仅更新 mask=True 的权重。"""
    h, u = forward(W1, b1, W2, b2)
    err = u - u_true
    g_W2 = h.T @ err.reshape(-1, 1) / len(x)
    g_h = err.reshape(-1, 1) @ W2.T
    g_z = g_h * (1 - h ** 2)
    g_W1 = x.T @ g_z / len(x)
    W2 -= lr * g_W2 * mask[1]
    W1 -= lr * g_W1 * mask[0]


lr = 0.01
for _ in range(6000):
    h, u = forward(W1, b1, W2, b2)
    err = u - u_true
    g_W2 = h.T @ err.reshape(-1, 1) / len(x); g_b2 = err.mean()
    g_h = err.reshape(-1, 1) @ W2.T; g_z = g_h * (1 - h ** 2)
    g_W1 = x.T @ g_z / len(x); g_b1 = g_z.mean(0)
    W2 -= lr * g_W2; b2 -= lr * g_b2
    W1 -= lr * g_W1; b1 -= lr * g_b1


def greedy(retrain_steps=0):
    W1p, W2p = W1.copy(), W2.copy()
    weights = [("W1", i) for i in np.ndindex(W1.shape)] + [("W2", i) for i in np.ndindex(W2.shape)]
    trace = [residual_mse(W1p, b1, W2p, b2)]
    while len(weights) > 1:
        base = residual_mse(W1p, b1, W2p, b2)
        sal = {}
        for name, idx in weights:
            mat = W1p if name == "W1" else W2p
            orig = mat[idx]
            mat[idx] = 0.0
            sal[(name, idx)] = residual_mse(W1p, b1, W2p, b2) - base
            mat[idx] = orig
        q = min(sal, key=sal.get)
        (W1p if q[0] == "W1" else W2p)[q[1]] = 0.0
        weights.remove(q)
        if retrain_steps > 0:
            for _ in range(retrain_steps):
                fit_step(W1p, b1, W2p, b2,
                         mask=(np.abs(W1p) > 0, np.abs(W2p) > 0))
        trace.append(residual_mse(W1p, b1, W2p, b2))
    return trace


tr_plain = greedy(0)
tr_retrain = greedy(30)

print(f"{'剪枝率':>6s} | {'纯贪心':>10s} | {'贪心+重训':>10s}")
n_w = W1.size + W2.size
for pct in (0, 20, 40, 60, 80, 85, 90, 95):
    i = min(int(n_w * pct / 100), n_w)
    print(f"{pct:>5d}% | {tr_plain[i]:>10.2f} | {tr_retrain[i]:>10.2f}")
