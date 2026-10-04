"""临时实验：扫描分段剪枝的最优切换点 switch_frac

对每个 switch_frac（贪心阶段移除的权重比例），跑完整分段剪枝，统计：
- mean 残差（全程积分）
- max 残差（最坏点）
- 90% / 95% 剪枝率处的残差
找出使这些指标最优的切换点。
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
    W1p = w[:n_h].reshape(1, n_h); W2p = w[n_h:].reshape(n_h, 1)
    h = np.tanh(x @ W1p + b1)
    u = (h @ W2p + b2).ravel()
    uxx = (u[2:] - 2 * u[1:-1] + u[:-2]) / hx ** 2
    return uxx + np.pi ** 2 * u[1:-1]


def resid_mse(w):
    return float(np.mean(residual_vec(w) ** 2))


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


def greedy_pick(w, active):
    base = resid_mse(w)
    sal = {}
    for widx in active:
        orig = w[widx]
        w[widx] = 0.0
        sal[widx] = resid_mse(w) - base
        w[widx] = orig
    return min(sal, key=sal.get)


def obs_pick_and_compensate(w, active):
    eps = 1e-4; lam = 1e-6
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
            w[widx] -= w[q] * Hinv[j, qidx] / Hinv[qidx, qidx]
    w[q] = 0.0
    active.remove(q)


def staged(switch_frac):
    w = w0.copy()
    active = list(range(n_w))
    trace = [resid_mse(w)]
    n_switch = int(n_w * switch_frac)
    while len(active) > 1:
        removed = n_w - len(active)
        if removed < n_switch:
            q = greedy_pick(w, active)
            w[q] = 0.0
            active.remove(q)
        else:
            obs_pick_and_compensate(w, active)
        trace.append(resid_mse(w))
    return np.array(trace)


print(f"{'切换点':>6s} | {'全程mean':>9s} | {'全程max':>9s} | {'90%残差':>8s} | {'95%残差':>8s}")
for sf in np.arange(0.50, 0.96, 0.05):
    tr = staged(float(sf))
    n = len(tr)
    r90 = tr[min(int(n_w * 0.90), n_w)]
    r95 = tr[min(int(n_w * 0.95), n_w)]
    print(f"{sf:>5.2f}  | {tr.mean():>9.2f} | {tr.max():>9.2f} | {r90:>8.2f} | {r95:>8.2f}")
