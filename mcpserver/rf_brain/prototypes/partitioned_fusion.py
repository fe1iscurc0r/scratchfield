"""R17 · 多传感器分区融合原型（约束证据可见性）

灵感：digest-g1-3 授粉点① · 论文 2608.20054v3（Slot-selective evidence masking）。

思想：多传感器系统若把**全量**数据喂给一个统一编码器，会学到跨传感器的虚假相关；
若按物理过程分区——每个模块只见自己的证据子集 + 轻量接口（固定求和）——则结构上
被禁止学跨传感器交互，只能学每个传感器各自的物理贡献，从而在**未见组合**上泛化更好。

原型：3 个传感器各测一个物理过程（连续值），真目标 = 各过程独立贡献之和
（y = f1(s1)+f2(s2)+f3(s3)，f 为非线性）。训练只覆盖部分组合，测试覆盖未见组合。

  - 统一编码器：全传感器 joint 特征（含交叉项）→ 单编码器，易过拟合训练集组合。
  - 分区融合：每传感器独立编码器（各自多项式）+ 固定求和接口 → 结构泛化。

对比两者在「未见组合」测试集上的误差，验证分区融合的组合泛化优势。

运行：python -m mcpserver.rf_brain.prototypes.partitioned_fusion
"""
from __future__ import annotations

import numpy as np


def synthesize(n_samples: int, *, seed: int = 0) -> dict:
    """3 传感器各取 3 档 {0,1,2}，真目标 = s1² + 2·s2 - s3（各传感器独立贡献）。"""
    rng = np.random.default_rng(seed)
    S = rng.integers(0, 3, size=(n_samples, 3))
    y = S[:, 0] ** 2 + 2.0 * S[:, 1] - S[:, 2]
    return S, y


def partition_features(S: np.ndarray) -> np.ndarray:
    """分区：每传感器独立编码器（各自 2 阶多项式），轻量接口 = 求和（线性回归实现）。"""
    s1, s2, s3 = S[:, 0], S[:, 1], S[:, 2]
    return np.column_stack([s1, s1 ** 2, s2, s2 ** 2, s3, s3 ** 2])


def unified_features(S: np.ndarray) -> np.ndarray:
    """统一编码器：全传感器 joint 特征，含所有二阶/三阶交叉项。"""
    s1, s2, s3 = S[:, 0], S[:, 1], S[:, 2]
    return np.column_stack([
        s1, s2, s3, s1 ** 2, s2 ** 2, s3 ** 2,
        s1 * s2, s1 * s3, s2 * s3, s1 * s2 * s3,
    ])


def _fit_predict(X_tr, y_tr, X_te):
    w, *_ = np.linalg.lstsq(X_tr, y_tr, rcond=None)
    return X_te @ w


def evaluate(n_train: int = 16, n_test: int = 11, *, seed: int = 0) -> dict:
    """训练/测试用不同组合（未见组合），对比两模型的测试误差。"""
    S, y = synthesize(n_train + n_test, seed=seed)
    S_tr, y_tr = S[:n_train], y[:n_train]
    S_te, y_te = S[n_train:], y[n_train:]

    y_p = _fit_predict(partition_features(S_tr), y_tr, partition_features(S_te))
    y_u = _fit_predict(unified_features(S_tr), y_tr, unified_features(S_te))
    return {
        "partitioned_mse": float(np.mean((y_te - y_p) ** 2)),
        "unified_mse": float(np.mean((y_te - y_u) ** 2)),
    }


def main() -> None:
    # 多随机种子平均，避免单次偶然
    p_mse, u_mse = [], []
    for seed in range(50):
        r = evaluate(seed=seed)
        p_mse.append(r["partitioned_mse"])
        u_mse.append(r["unified_mse"])
    print(f"分区融合 平均测试 MSE = {np.mean(p_mse):.3f}")
    print(f"统一编码 平均测试 MSE = {np.mean(u_mse):.3f}")
    print(f"分区较统一 误差降低 = {(1 - np.mean(p_mse)/np.mean(u_mse))*100:.1f}%")


if __name__ == "__main__":
    main()
