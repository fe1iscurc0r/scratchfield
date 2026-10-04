"""临时实验：对比三种剪枝在高稀疏度下的 PDE 残差保持（m15 的 80% 退化问题）

方法：
- one-shot  leave-one-out 残差显著性（一次性排序，当前 m15 做法）
- 迭代贪心  leave-one-out（每次移除后重算显著性，IMP/Lottery Ticket 思想）
- 随机基线

结论预期：one-shot 在 80% 退化（排序过时）；迭代贪心重算能补救。
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


def residual_mse(W1, b1, W2, b2):
    _, u = forward(W1, b1, W2, b2)
    uxx = (u[2:] - 2 * u[1:-1] + u[:-2]) / hx ** 2
    R = uxx + np.pi ** 2 * u[1:-1]
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

# 权重清单
weights = []
for name, mat in [("W1", W1), ("W2", W2)]:
    for idx in np.ndindex(mat.shape):
        weights.append((name, idx))


def get_mat(W1, W2, name):
    return W1 if name == "W1" else W2


def loo_saliency(W1, W2, remaining):
    base = residual_mse(W1, b1, W2, b2)
    sal = {}
    for name, idx in remaining:
        mat = get_mat(W1, W2, name)
        orig = mat[idx]
        mat[idx] = 0.0
        sal[(name, idx)] = residual_mse(W1, b1, W2, b2) - base
        mat[idx] = orig
    return sal


# one-shot：一次性排序
sal_once = loo_saliency(W1, W2, weights)
order_once = sorted(sal_once, key=sal_once.get)

# 迭代贪心：每次移除后重算
W1g, W2g = W1.copy(), W2.copy()
remaining = list(weights)
order_iter = []
while remaining:
    sal = loo_saliency(W1g, W2g, remaining)
    k = min(sal, key=sal.get)
    order_iter.append(k)
    get_mat(W1g, W2g, k[0])[k[1]] = 0.0
    remaining.remove(k)

# 随机
order_rand = list(weights)
rng.shuffle(order_rand)


def trace(order):
    W1p, W2p = W1.copy(), W2.copy()
    out = [residual_mse(W1p, b1, W2p, b2)]
    for name, idx in order:
        get_mat(W1p, W2p, name)[idx] = 0.0
        out.append(residual_mse(W1p, b1, W2p, b2))
    return out


n = len(weights)
tr_once = trace(order_once)
tr_iter = trace(order_iter)
tr_rand = trace(order_rand)

print(f"{'剪枝率':>6s} | {'one-shot 残差':>13s} | {'迭代贪心 残差':>13s} | {'随机 残差':>13s}")
for pct in (0, 20, 40, 60, 80, 90):
    i = int(n * pct / 100)
    print(f"{pct:>5d}% | {tr_once[i]:>13.2f} | {tr_iter[i]:>13.2f} | {tr_rand[i]:>13.2f}")
