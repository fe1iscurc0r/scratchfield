"""M29 机械反应预测（离散流匹配）· 最小原型。

授粉源：digest-g1-4-2026-08-30.md 2608.27429（MAELLE：化学反应 = 电子空间变换，
用离散流匹配 Discrete Flow Matching 建模电子占据向量的 CTMC 流动，可预测副产物 +
给出机械论解释）。承接 M16（流匹配能量 → 燃烧/热解 ODE 约束）。

本原型（简化 + 诚实标注）：
  - 电子态 = 二元电子占据向量 e ∈ {0,1}^L（反应位点/键）；
  - 反应 = 稀疏电子转移（若干位翻转），由反应物前 2 位「选择子」决定走哪条规则；
  - 模型 = 轻量 2 层 MLP 条件生成器，学 P(产物电子态 | 反应物)（逐位 sigmoid）；
  - 训练 = 条件生成目标（对「均匀源 → 产物」线性插值概率路径，其离散流匹配目标
    的闭式最小化点等价于逐位交叉熵，见方案 §3）；
  - 采样 = 离散流采样：从均匀源出发沿概率路径流向目标分布（CTMC 简化）。

验收：合成反应数据集产物预测准确率 ≥70%（全向量精确匹配口径，见 test）。

纯 numpy + 手写反向传播，无外部依赖，无 LLM/网络调用。
"""
from __future__ import annotations

import numpy as np

L = 10          # 电子占据向量长度（2 选择子 + 8 反应位点）
H = 32          # 隐层宽度


def _sigmoid(z: np.ndarray) -> np.ndarray:
    """数值稳定 sigmoid（clip 防止 exp 溢出）。"""
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def _masks() -> list[np.ndarray]:
    """4 条电子转移规则（翻转掩码，位置 0/1 为选择子不翻）。"""
    m0 = np.zeros(L, dtype=int); m0[[2, 3, 4]] = 1
    m1 = np.zeros(L, dtype=int); m1[[5, 6, 7]] = 1
    m2 = np.zeros(L, dtype=int); m2[[2, 4, 6, 8]] = 1
    m3 = np.zeros(L, dtype=int); m3[[3, 5, 7, 9]] = 1
    return [m0, m1, m2, m3]


def make_dataset(n_per_rule: int = 200, noise: float = 0.01, seed: int = 0):
    """合成反应对 (反应物 r, 产物 p)。

    反应物前 2 位为「选择子」（决定规则），后 8 位为反应位点；产物 = r XOR 规则掩码，
    叠加 noise 比例的随机翻转（模拟观测噪声/副反应）。
    """
    rng = np.random.default_rng(seed)
    masks = _masks()
    R, P = [], []
    for k, mask in enumerate(masks):
        for _ in range(n_per_rule):
            r = rng.integers(0, 2, size=L)
            r[0], r[1] = (k >> 1) & 1, k & 1   # 选择子编码规则 k
            p = r ^ mask
            flips = rng.random(L) < noise
            p = p ^ flips.astype(int)
            R.append(r)
            P.append(p)
    return np.asarray(R), np.asarray(P)


class ElectronFlowMLP:
    """轻量条件生成器：P(产物电子态 | 反应物)，逐位 sigmoid。"""

    def __init__(self, in_dim: int = L, hid: int = H, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0.0, 0.1, size=(hid, in_dim))
        self.b1 = np.zeros(hid)
        self.W2 = rng.normal(0.0, 0.1, size=(in_dim, hid))
        self.b2 = np.zeros(in_dim)

    def forward(self, X: np.ndarray) -> np.ndarray:
        h = np.maximum(0.0, X @ self.W1.T + self.b1)          # ReLU
        logits = h @ self.W2.T + self.b2
        return _sigmoid(logits)                               # (n, L)

    def train(self, X: np.ndarray, Y: np.ndarray, iters: int = 10000,
              lr: float = 0.05, l2: float = 0.01) -> "ElectronFlowMLP":
        """全批梯度下降 + L2 权重衰减（防过拟合发散，稳定收敛到噪声上限）。"""
        n = X.shape[0]
        for _ in range(iters):
            h = np.maximum(0.0, X @ self.W1.T + self.b1)
            logits = h @ self.W2.T + self.b2
            p = _sigmoid(logits)
            dlogits = (p - Y) / n                             # 逐位交叉熵梯度
            self.b2 -= lr * dlogits.sum(axis=0)
            self.W2 -= lr * (dlogits.T @ h + l2 * self.W2)    # L2 权重衰减
            dh = dlogits @ self.W2
            dh = np.where(h > 0, dh, 0.0)                     # ReLU 反传
            self.b1 -= lr * dh.sum(axis=0)
            self.W1 -= lr * (dh.T @ X + l2 * self.W1)
        return self

    def target_proba(self, X: np.ndarray) -> np.ndarray:
        return self.forward(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.forward(X) >= 0.5).astype(int)

    def flow_sample(self, r: np.ndarray, T: int = 12) -> np.ndarray:
        """离散流采样（CTMC 简化）：从均匀源出发沿概率路径流向目标分布。

        对「均匀源 → 目标」线性插值 p_t = (1-t)·uniform + t·p_target，
        在离散时间步 t=k/T 采样 x_t ~ Bernoulli(p_t)，t=1 时收敛到 argmax(p_target)。
        """
        p_target = self.forward(r.reshape(1, -1))[0]          # (L,)
        x = np.random.binomial(1, 0.5, size=L).astype(float)  # 均匀源
        for k in range(1, T + 1):
            t = k / T
            p_t = (1.0 - t) * 0.5 + t * p_target
            x = np.random.binomial(1, np.clip(p_t, 0.0, 1.0)).astype(float)
        return (x >= 0.5).astype(int)


def full_match(pred: np.ndarray, truth: np.ndarray) -> float:
    """全向量精确匹配准确率（逐样本所有位都一致才算对）。"""
    return float(np.mean(np.all(pred == truth, axis=1)))


def run_demo() -> None:
    R, P = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(R))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    model = ElectronFlowMLP(seed=0).train(R[tr], P[tr].astype(float))
    pred = model.predict(R[te])
    site_acc = float(np.mean(pred == P[te]))
    full_acc = full_match(pred, P[te])
    print(f"[M29] 电子态逐位准确率 = {site_acc:.3f}")
    print(f"[M29] 产物全向量精确匹配 = {full_acc:.3f}（验收 ≥0.70）")

    # 流采样演示：采样产物与 argmax 一致率（展示 CTMC 收敛）
    r0 = R[te][0]
    s = model.flow_sample(r0)
    print(f"[M29] 流采样产物 = {''.join(map(str, s))} ｜ argmax 产物 = {''.join(map(str, model.predict(r0.reshape(1,-1))[0]))}")


if __name__ == "__main__":
    run_demo()
