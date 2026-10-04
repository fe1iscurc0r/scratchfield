"""临时实验：staged 基线 vs CoSaMP回补 vs best-subset(有界swap)

- CoSaMP：贪心移除后，网格搜已删权重的最优值，残差下降则回补
- best-subset：贪心删到 k 个后，每层做一次最优 swap（有界，避免穷举爆炸）
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
CAND = (-1.0, -0.5, -0.2, 0.2, 0.5, 1.0)


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


def cosamp():
    w = w0.copy(); active = set(range(n_w))
    trace = [resid_mse(w)]
    while len(active) > 1:
        base = resid_mse(w)
        sal = {}
        for widx in active:
            orig = w[widx]; w[widx] = 0.0
            sal[widx] = resid_mse(w) - base
            w[widx] = orig
        q = min(sal, key=sal.get)
        w[q] = 0.0; active.remove(q)
        for rw in range(n_w):
            if rw in active:
                continue
            cur = resid_mse(w)
            best_v = 0.0; best_r = cur
            for c in CAND:
                w[rw] = c
                r = resid_mse(w)
                if r < best_r:
                    best_r = r; best_v = c
            if best_r < cur - 1e-9:
                w[rw] = best_v; active.add(rw)
            else:
                w[rw] = 0.0
        trace.append(resid_mse(w))
    return np.array(trace)


def best_subset():
    w = w0.copy(); active = list(range(n_w))
    trace = [resid_mse(w)]
    while len(active) > 1:
        base = resid_mse(w)
        sal = {}
        for widx in active:
            orig = w[widx]; w[widx] = 0.0
            sal[widx] = resid_mse(w) - base
            w[widx] = orig
        q = min(sal, key=sal.get)
        w[q] = 0.0; active.remove(q)
        # 每层一次最优 swap：找使残差下降最多的 (inactive 进来, active 出去)
        inactive = [j for j in range(n_w) if j not in active]
        cur = resid_mse(w)
        best = None
        for i in active:
            wi = w[i]; w[i] = 0.0
            for j in inactive:
                for c in CAND:
                    w[j] = c
                    r = resid_mse(w)
                    if r < cur - 1e-9 and (best is None or r < best[0]):
                        best = (r, i, j, c)
                    w[j] = 0.0
            w[i] = wi
        if best is not None:
            w[best[1]] = 0.0
            w[best[2]] = best[3]
            active.remove(best[1]); active.append(best[2])
        trace.append(resid_mse(w))
    trace.append(resid_mse(np.zeros_like(w0)))
    return np.array(trace[::-1])


print("staged ...", flush=True)
tr_staged = staged()
print("CoSaMP ...", flush=True)
tr_cosamp = cosamp()
print("best-subset ...", flush=True)
tr_bs = best_subset()

print(f"{'方法':<14s} | {'全程mean':>8s} | {'全程max':>8s} | {'90%':>8s} | {'95%':>8s}")
for name, tr in [("staged", tr_staged), ("CoSaMP", tr_cosamp), ("best-subset", tr_bs)]:
    print(f"{name:<14s} | {tr.mean():>8.2f} | {tr.max():>8.2f} | "
          f"{tr[min(int(n_w*0.9),n_w)]:>8.2f} | {tr[min(int(n_w*0.95),n_w)]:>8.2f}")
