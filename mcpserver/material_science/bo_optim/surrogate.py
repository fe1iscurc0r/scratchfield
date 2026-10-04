"""代理模型：随机森林 / numpy 手写高斯过程。统一 fit / predict / uncertainty 接口。

选型（H-01 结论）：外部 BO 工具链（skopt/optuna/GPyOpt）未装且偏重，故：
- RandomForestSurrogate：sklearn 随机森林，点预测取树均值、不确定性取树间标准差。小样本友好。
- GaussianProcessSurrogate：纯 numpy 手写 RBF GP，无 sklearn 依赖时的降级路径。
- make_surrogate(kind)：工厂选择。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    from sklearn.ensemble import RandomForestRegressor

    _HAS_SKLEARN = True
except Exception:  # pragma: no cover - 依赖缺失降级
    _HAS_SKLEARN = False


class RandomForestSurrogate:
    """随机森林代理：predict 为树均值，uncertainty 为树间标准差。"""

    def __init__(self, n_estimators: int = 100, random_state: int = 0) -> None:
        if not _HAS_SKLEARN:
            raise RuntimeError("缺 scikit-learn，无法使用 RandomForestSurrogate；请改用 GaussianProcessSurrogate")
        self.model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
        self.fitted = False

    def fit(self, X, y) -> "RandomForestSurrogate":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        if len(X) == 0:
            raise RuntimeError("训练集为空")
        self.model.fit(X, y)
        self.fitted = True
        return self

    def _tree_preds(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        return np.array([t.predict(X) for t in self.model.estimators_])

    def predict(self, X) -> np.ndarray:
        return self._tree_preds(X).mean(axis=0)

    def uncertainty(self, X) -> np.ndarray:
        return self._tree_preds(X).std(axis=0)

    def predict_with_uncertainty(self, X) -> Tuple[np.ndarray, np.ndarray]:
        preds = self._tree_preds(X)
        return preds.mean(axis=0), preds.std(axis=0)


def _rbf(X1: np.ndarray, X2: np.ndarray, length_scale: float) -> np.ndarray:
    """RBF 核：exp(-0.5 * ||x1 - x2||^2 / l^2)。"""
    sq = (
        (X1**2).sum(axis=1, keepdims=True)
        + (X2**2).sum(axis=1, keepdims=True).T
        - 2.0 * (X1 @ X2.T)
    )
    return np.exp(-0.5 * sq / (length_scale**2))


class GaussianProcessSurrogate:
    """numpy 手写 RBF 高斯过程（零 sklearn 依赖的降级路径）。

    fit 求解 (K + noise·I)α = y；predict_with_uncertainty 返回后验均值与标准差。
    """

    def __init__(self, length_scale: float = 1.0, noise: float = 1e-6) -> None:
        self.length_scale = float(length_scale)
        self.noise = float(noise)
        self.fitted = False
        self._X: np.ndarray | None = None
        self._alpha: np.ndarray | None = None

    def fit(self, X, y) -> "GaussianProcessSurrogate":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        if len(X) == 0:
            raise RuntimeError("训练集为空")
        self._X = X
        K = _rbf(X, X, self.length_scale) + self.noise * np.eye(len(X))
        # 加 jitter 保证数值可逆
        try:
            self._alpha = np.linalg.solve(K, y)
        except np.linalg.LinAlgError:
            K = K + 1e-4 * np.eye(len(X))
            self._alpha = np.linalg.solve(K, y)
        self.fitted = True
        return self

    def predict(self, X) -> np.ndarray:
        return self.predict_with_uncertainty(X)[0]

    def uncertainty(self, X) -> np.ndarray:
        return self.predict_with_uncertainty(X)[1]

    def predict_with_uncertainty(self, X) -> Tuple[np.ndarray, np.ndarray]:
        if not self.fitted or self._X is None or self._alpha is None:
            raise RuntimeError("代理模型未拟合，请先 fit")
        X = np.asarray(X, dtype=float)
        Ks = _rbf(X, self._X, self.length_scale)
        mean = Ks @ self._alpha
        K = _rbf(self._X, self._X, self.length_scale) + self.noise * np.eye(len(self._X))
        # 后验方差 diag(Kss - Ks K^-1 Ks^T)；v = K^-1 Ks^T，形状 (n_train, n_test)
        v = np.linalg.solve(K, Ks.T)
        var = 1.0 - (Ks * v.T).sum(axis=1)
        std = np.sqrt(np.clip(var, 0.0, None))
        return mean, std


def make_surrogate(kind: str = "rf", **kwargs):
    """代理模型工厂：kind ∈ {"rf", "gp"}。"""
    if kind == "rf":
        return RandomForestSurrogate(**kwargs)
    if kind == "gp":
        return GaussianProcessSurrogate(**kwargs)
    raise ValueError(f"未知代理模型 kind: {kind!r}（可选 rf / gp）")
