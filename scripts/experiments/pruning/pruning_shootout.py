"""临时实验：staged 基线 vs leverage采样+重解 vs log-sum 连续松弛

三种思路对比（同一训练好的 32 权重 MLP）：
- staged：贪心 leave-one-out → 80% 后 OBS（当前最好，已提交）
- leverage：OBS 显著性 w²/(2[H⁻¹]qq) 当 leverage score，keep top-k 后对保留权重
  重解（梯度下降拟合 sin(πx)），谱稀疏化"采样支撑+重解"的思路
- logsum：min 数据拟合 + λ·Σ log(1+|w|/δ) 连续松弛，扫 λ 得不同稀疏度
指标：全程 mean/max 残差、90%/95% 残差。
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


def fit_mse(w):
    W1p = w[:n_h].reshape(1, n_h); W2p = w[n_h:].reshape(n_h, 1)
    u = (np.tanh(x @ W1p + b1) @ W2p + b2).ravel()
    return float(np.mean((u - u_true) ** 2))


# 训练拟合 sin(πx)
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


# ---------- 基线：staged ----------
def greedy_pick(w, active):
    base = resid_mse(w)
    sal = {}
    for widx in active:
        orig = w[widx]; w[widx] = 0.0
        sal[widx] = resid_mse(w) - base
        w[widx] = orig
    return min(sal, key=sal.get)


def obs_pick_and_compensate(w, active):
    eps = 1e-4; lam = 1e-6
    R0 = residual_vec(w)
    J = np.zeros((R0.size, len(active)))
    for j, widx in enumerate(active):
        w[widx] += eps; J[:, j] = (residual_vec(w) - R0) / eps; w[widx] -= eps
    H = J.T @ J + lam * np.eye(len(active))
    Hinv = np.linalg.inv(H)
    sal = {widx: w[widx] ** 2 / (2 * Hinv[j, j]) for j, widx in enumerate(active)}
    q = min(sal, key=sal.get); qidx = active.index(q)
    for j, widx in enumerate(active):
        if widx != q:
            w[widx] -= w[q] * Hinv[j, qidx] / Hinv[qidx, qidx]
    w[q] = 0.0; active.remove(q)


def staged():
    w = w0.copy(); active = list(range(n_w))
    trace = [resid_mse(w)]; n_switch = int(n_w * 0.8)
    while len(active) > 1:
        if n_w - len(active) < n_switch:
            q = greedy_pick(w, active); w[q] = 0.0; active.remove(q)
        else:
            obs_pick_and_compensate(w, active)
        trace.append(resid_mse(w))
    return np.array(trace)


# ---------- leverage 采样 + 重解 ----------
def leverage_scores():
    eps = 1e-4; lam = 1e-6
    R0 = residual_vec(w0)
    J = np.zeros((R0.size, n_w))
    for j in range(n_w):
        w0[j] += eps; J[:, j] = (residual_vec(w0) - R0) / eps; w0[j] -= eps
    H = J.T @ J + lam * np.eye(n_w)
    Hinv = np.linalg.inv(H)
    return {j: w0[j] ** 2 / (2 * Hinv[j, j]) for j in range(n_w)}


def refit(w, active, steps=200):
    lr = 0.01
    for _ in range(steps):
        h = np.tanh(x @ w[:n_h].reshape(1, n_h) + b1)
        u = (h @ w[n_h:].reshape(n_h, 1) + b2).ravel()
        err = u - u_true
        g_W2 = h.T @ err.reshape(-1, 1) / len(x)
        g_h = err.reshape(-1, 1) @ w[n_h:].reshape(n_h, 1).T
        g_z = g_h * (1 - h ** 2)
        g_W1 = x.T @ g_z / len(x)
        for widx in active:
            if widx < n_h:
                w[widx] -= lr * g_W1[0, widx]
            else:
                w[widx] -= lr * g_W2[widx - n_h, 0]


def leverage_prune():
    lev = leverage_scores()
    order = sorted(range(n_w), key=lambda j: lev[j], reverse=True)  # 高 leverage 优先保留
    trace = []
    for k in range(n_w, 0, -1):
        w = w0.copy()
        keep = set(order[:k])
        for j in range(n_w):
            if j not in keep:
                w[j] = 0.0
        refit(w, list(keep))
        trace.append(resid_mse(w))
    trace.append(resid_mse(np.zeros_like(w0)))
    return np.array(trace[::-1])  # 0..32


# ---------- log-sum 连续松弛 ----------
def logsum_prune(delta=0.05, n_lam=12):
    lams = np.logspace(-1.5, 0.8, n_lam)
    records = []
    for lam in lams:
        w = w0.copy()
        lr = 0.01
        for _ in range(3000):
            h = np.tanh(x @ w[:n_h].reshape(1, n_h) + b1)
            u = (h @ w[n_h:].reshape(n_h, 1) + b2).ravel()
            err = u - u_true
            g_fit_w2 = h.T @ err.reshape(-1, 1) / len(x)
            g_h = err.reshape(-1, 1) @ w[n_h:].reshape(n_h, 1).T
            g_z = g_h * (1 - h ** 2)
            g_fit_w1 = x.T @ g_z / len(x)
            grad = np.concatenate([g_fit_w1.ravel(), g_fit_w2.ravel()])
            grad += lam * np.sign(w) / (delta + np.abs(w))   # ∂(log-sum)
            w -= lr * grad
        w[np.abs(w) < 1e-2] = 0.0
        nz = int(np.count_nonzero(w))
        records.append((nz, resid_mse(w)))
    # 按稀疏度排序，插值成 trace
    records = sorted(records)
    return records


# ---------- 汇总 ----------
tr_staged = staged()

print("=== leverage 采样+重解 ===")
lev = leverage_scores()
order = sorted(range(n_w), key=lambda j: lev[j], reverse=True)
tr_lev = leverage_prune()

print("=== log-sum 连续松弛 ===")
ls_records = logsum_prune()

print(f"{'方法':<22s} | {'全程mean':>8s} | {'全程max':>8s} | {'90%残差':>8s} | {'95%残差':>8s}")
tr_s = tr_staged
print(f"{'staged(基线)':<22s} | {tr_s.mean():>8.2f} | {tr_s.max():>8.2f} | {tr_s[min(int(n_w*0.9),n_w)]:>8.2f} | {tr_s[min(int(n_w*0.95),n_w)]:>8.2f}")
print(f"{'leverage+重解':<22s} | {tr_lev.mean():>8.2f} | {tr_lev.max():>8.2f} | {tr_lev[min(int(n_w*0.9),n_w)]:>8.2f} | {tr_lev[min(int(n_w*0.95),n_w)]:>8.2f}")

print()
print("log-sum 记录 (稀疏度, 残差):")
for nz, r in ls_records:
    print(f"  nz={nz:>3d}  resid={r:.3f}")
