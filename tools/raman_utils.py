"""拉曼光谱薄封装（RamanSPy 落地 · data_tools 四件套之 raman）。

依据 docs/RamanSPy-深挖评估-2026-09-08.md：
- 厂商格式直读走 ramanspy.load（WITec .mat / Renishaw .wdf / HORIBA .txt），懒加载，
  不依赖 wget（不拉内置数据集）；解混（pysptools）不在本封装范围（懒加载隔离）。
- 预处理/绘图自实现（numpy/scipy/matplotlib，与 ramanspy 同算法族）：去尖峰（中位
  绝对偏差）/ SavGol 去噪 / ASLS 基线 / MinMax 归一化——确定性可测，不引重依赖。
- 兼容 shim：使用前先 `import raman_compat`（get_cmap + _flinalg，见 raman_compat.py）。
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

import tools.raman_compat as _compat  # noqa: F401  兼容 shim，import 即生效

# ============ 解析 ============


def parse_raman_text(text: str) -> pd.DataFrame:
    """解析两列文本（Raman shift / intensity），分隔符自动探测。

    无表头（header=None），列名统一为 RamanShift_cm1 / Intensity。
    """
    import io as _io

    text = text.lstrip("\ufeff")
    best, best_cols = ",", -1
    for d in (",", "\t", ";", r"\s+"):
        try:
            df = pd.read_csv(_io.StringIO(text), sep=d, comment="#", engine="python", header=None)
            if df.shape[1] > best_cols:
                best, best_cols = d, df.shape[1]
        except Exception:
            continue
    df = pd.read_csv(_io.StringIO(text), sep=best, comment="#", engine="python", header=None)
    if df.shape[1] < 2:
        raise ValueError("至少需要两列数据（x 与 y）")
    return df.iloc[:, :2].rename(
        columns={df.columns[0]: "RamanShift_cm1", df.columns[1]: "Intensity"},
    )


def parse_raman_vendor(data: bytes, fmt: str) -> pd.DataFrame:
    """厂商格式直读（懒加载 ramanspy.load）：witec / renishaw / horiba。

    ramanspy 返回 SpectralContainer（spectral_axis + spectral_data 3D），
    这里降维取第一个光谱/第一帧，输出两列 DataFrame（x=cm⁻¹, y=intensity）。
    """
    import ramanspy as rp

    loader = {
        "witec": rp.load.witec,
        "renishaw": rp.load.renishaw,
        "horiba": rp.load.labspec,
    }.get(fmt)
    if loader is None:
        raise ValueError(f"不支持的厂商格式：{fmt}（支持 witec/renishaw/horiba）")
    import tempfile
    from pathlib import Path

    suffix = {"witec": ".mat", "renishaw": ".wdf", "horiba": ".txt"}[fmt]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / f"sample{suffix}"
        path.write_bytes(data)
        container = loader(str(path))
    axis = np.asarray(container.spectral_axis)
    spec = np.asarray(container.spectral_data)
    if spec.ndim == 3:
        spec = spec[0, 0]
    elif spec.ndim == 2:
        spec = spec[0]
    return pd.DataFrame({"RamanShift_cm1": axis, "Intensity": spec})


def parse_raman(data: bytes, fmt: str | None = None) -> pd.DataFrame:
    """统一入口：text（两列文本，fmt=None/'text'）或厂商格式（witec/renishaw/horiba）。"""
    if fmt in (None, "text"):
        return parse_raman_text(data.decode("utf-8", errors="replace"))
    return parse_raman_vendor(data, fmt)


# ============ 预处理 ============


def remove_spikes(y: np.ndarray, threshold: float = 3.0, window: int = 7) -> np.ndarray:
    """中位绝对偏差（MAD）去尖峰：把偏离局部中位线的拉曼尖峰替换为邻域中值。"""
    out = y.astype(float)
    n = out.size
    if n < window:
        return out
    med = np.empty_like(out)
    mad = np.empty_like(out)
    half = window // 2
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        seg = out[lo:hi]
        med[i] = np.median(seg)
        mad[i] = np.median(np.abs(seg - med[i]))
    sigma = 1.4826 * mad
    sigma[sigma < 1e-12] = 1e-12
    spike = np.abs(out - med) > threshold * sigma
    for i in np.where(spike)[0]:
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out[i] = np.median(out[lo:hi])
    return out


def asls_baseline(y: np.ndarray, lam: float = 1e5, p: float = 0.01, niter: int = 10) -> np.ndarray:
    """ASLS（不对称最小二乘平滑）基线估计。"""
    y = y.astype(float)
    n = y.size
    if n < 3:
        return np.zeros_like(y)
    # 二阶差分矩阵 D（(n-2) x n），DTD 为 (n x n) 循环带状
    d = np.zeros((n - 2, n))
    for i in range(n - 2):
        d[i, i] = 1.0
        d[i, i + 1] = -2.0
        d[i, i + 2] = 1.0
    dtd = d.T @ d
    w = np.ones(n)
    z = np.zeros(n)
    for _ in range(niter):
        a = np.diag(w) + lam * dtd
        z = np.linalg.solve(a, w * y)
        w = np.where(y > z, p, 1 - p)
    return z


def preprocess_raman(
    df: pd.DataFrame,
    *,
    despike: bool = True,
    savgol_window: int = 9,
    baseline: bool = True,
    normalise: str | None = "minmax",
) -> pd.DataFrame:
    """拉曼预处理链：去尖峰 → SavGol 去噪 → ASLS 基线扣除 → MinMax 归一化。

    返回两列 DataFrame（x 不变，y=处理后强度）；pipeline 可逐段关（参数化）。
    """
    out = df.copy()
    x = out.iloc[:, 0].to_numpy()
    y = out.iloc[:, 1].to_numpy().astype(float)

    if despike:
        y = remove_spikes(y)
    if savgol_window and savgol_window > 2:
        if savgol_window % 2 == 0:
            savgol_window += 1
        y = savgol_filter(y, window_length=savgol_window, polyorder=3)
    if baseline:
        y = y - asls_baseline(y)
    if normalise == "minmax":
        lo, hi = y.min(), y.max()
        if hi - lo > 1e-12:
            y = (y - lo) / (hi - lo)

    out = pd.DataFrame({out.columns[0]: x, out.columns[1]: y})
    return out


# ============ 绘图 ============


def plot_raman(df: pd.DataFrame, title: str = "Raman spectrum") -> io.BytesIO:
    """科研风拉曼谱 PNG（复用 data_tools plot_curve 风格：白底/网格/图例）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x, y = df.iloc[:, 0], df.iloc[:, 1]
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=120)
    ax.plot(x, y, color="#1f77b4", linewidth=1.2, label="Intensity")
    ax.set_xlabel("Raman shift (cm⁻¹)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_title(title)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
    ax.legend(frameon=False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# ============ 合成样例 ============


def synth_raman(n: int = 800, seed: int = 3) -> pd.DataFrame:
    """合成洛伦兹峰 + 尖峰 + 噪声（样例/测试用，标「自造」）。"""
    rng = np.random.default_rng(seed)
    x = np.linspace(550, 1700, n)
    y = np.zeros(n)
    for center, amp, width in ((1250.0, 900.0, 6.0), (1004.0, 500.0, 4.0), (1602.0, 700.0, 5.0)):
        y += amp * (width / 2) ** 2 / ((x - center) ** 2 + (width / 2) ** 2)
    y += 30.0 + x * 0.01  # 缓升荧光背景
    y += rng.normal(0, 5.0, n)  # 噪声
    y[400] += 1500.0  # 单点尖峰
    return pd.DataFrame({"RamanShift_cm1": x, "Intensity": y})
