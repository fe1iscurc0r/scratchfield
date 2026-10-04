"""临时实验：分区间切换剪枝（贪心 → 拐点后换 OBS）

思路：贪心在 ≤80% 最优，OBS 在极端稀疏度更优。做 staged：
- 阶段 1（0→switch）：纯贪心 leave-one-out
- 阶段 2（switch→95%）：换 OBS（二阶 + 补偿）
对比纯贪心 / 纯 OBS / staged（switch=80%）。
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
    eps = 1e-4
    lam = 1e-6
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


def run(mode, switch_frac=0.8):
    w = w0.copy()
    active = list(range(n_w))
    trace = [resid_mse(w)]
    n_switch = int(n_w * switch_frac)
    while len(active) > 1:
        removed = n_w - len(active)
        if mode == "greedy" or (mode == "staged" and removed < n_switch):
            q = greedy_pick(w, active)
            w[q] = 0.0
            active.remove(q)
        else:  # obs 或 staged 的第二阶段
            obs_pick_and_compensate(w, active)
        trace.append(resid_mse(w))
    return trace


tr_greedy = run("greedy")
tr_obs = run("obs")
tr_staged = run("staged", switch_frac=0.8)

print(f"{'剪枝率':>6s} | {'纯贪心':>10s} | {'纯OBS':>10s} | {'分段(80%切换)':>10s}")
for pct in (0, 20, 40, 60, 80, 85, 90, 95):
    i = min(int(n_w * pct / 100), n_w)
    print(f"{pct:>5d}% | {tr_greedy[i]:>10.2f} | {tr_obs[i]:>10.2f} | {tr_staged[i]:>10.2f}")
