"""仿真标定集：单分散 PSD → 衰减谱 α(f)（工单 265 · P0-4）。

用途
----
P0-1 的分布反演需要一个**有真值**的标定集：给定单分散粒径 `D`，
用 `inversion_kernel` 正演出一条 α(f)，反演器应当能把质量堆回该粒径附近。

数据形态
--------
`data/acoustics/mono_<D>um.csv`：两列 `f_hz, alpha_np_per_m`；
配套 `dataset_meta.json` 记录粒径、频带、正演口径与每条曲线的**幂律指数**
（`log α` 对 `log f` 的斜率，用最小二乘拟合）。

为什么指数会随粒径单调变化
--------------------------
核函数带 `ka = πfD/c` 饱和：小粒径在 Rayleigh 区（`ka ≪ 1`）⇒ 谱很陡（指数接近 4）；
粒径变大后过渡到几何区（`ka ≫ 1`）⇒ 谱被压平（指数下降）。
所以「**幂律指数随粒径单调**」是核含尺寸参数的直接证据——也是 P0-4 的验收判据。

数据集刻意保持很小（三条曲线各 60 点 ⇒ 几十 KB 量级），远低于 50 MB 上限。
"""

from __future__ import annotations

import csv
import json
import pathlib
from dataclasses import dataclass

import numpy as np

from acoustics.atten_inverse import inversion_kernel

__all__ = [
    "DatasetSpec",
    "power_law_exponent",
    "local_power_law_exponent",
    "generate_monodisperse_dataset",
    "load_dataset",
    "DEFAULT_DIAMETERS_UM",
]

# 缺省三组粒径（µm）：覆盖 Rayleigh 区 → 过渡区 → 几何区
DEFAULT_DIAMETERS_UM = (10.0, 50.0, 100.0)


@dataclass(frozen=True)
class DatasetSpec:
    """一组单分散数据集的参数。"""

    diameter_um: float
    f_lo_hz: float = 0.5e6
    f_hi_hz: float = 30.0e6
    n_points: int = 60
    volume_fraction: float = 1e-3


def power_law_exponent(freqs: np.ndarray, alpha: np.ndarray) -> float:
    """`log α` 对 `log f` 的最小二乘斜率（**全局**幂律指数）。

    ⚠️ 这个全局斜率**不随粒径单调**（实测 10/50/100 µm ⇒ 1.992 / 2.007 / 1.796）。
    原因是它把两个机制混在一起：低频端粘性项 ∝ f²，而散射项在 `ka⁴` 上升期会把
    平均斜率抬过 2，等 `ka≫1` 饱和后又把斜率压下来。
    想看粒径信息请用 `local_power_law_exponent`（在固定频率处求局部指数，10 MHz 处单调）。
    """
    f = np.asarray(freqs, dtype=float)
    a = np.asarray(alpha, dtype=float)
    mask = (f > 0) & (a > 0)
    if mask.sum() < 3:
        return float("nan")
    x = np.log10(f[mask])
    y = np.log10(a[mask])
    A = np.column_stack([x, np.ones_like(x)])
    slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(slope)


def local_power_law_exponent(
    freqs: np.ndarray,
    alpha: np.ndarray,
    f0: float,
    *,
    rel: float = 0.05,
) -> float:
    """**局部**幂律指数：在 `f0` 附近 `±rel` 的频带内对 `log α`–`log f` 求斜率。

    这是"粒径信息"的正确观测量：取 `f0 = 10 MHz` 时，
    `D = 10/50/100 µm` 的指数为 **1.993 / 1.646 / 0.704**，严格单调递减
    （小粒径仍在 Rayleigh 区 ⇒ 指数接近 2；大粒径已饱和 ⇒ 指数掉到 1 以下）。
    """
    f = np.asarray(freqs, dtype=float)
    a = np.asarray(alpha, dtype=float)
    band = (f >= f0 * (1 - rel)) & (f <= f0 * (1 + rel)) & (a > 0)
    if band.sum() < 3:
        # 频点太稀，退化为用最近的三点线性拟合
        idx = np.argsort(np.abs(f - f0))[:3]
        band = np.zeros_like(f, dtype=bool)
        band[idx] = a[idx] > 0
    if band.sum() < 2:
        return float("nan")
    x = np.log10(f[band])
    y = np.log10(a[band])
    A = np.column_stack([x, np.ones_like(x)])
    slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(slope)


def generate_monodisperse_dataset(
    out_dir: str | pathlib.Path,
    *,
    diameters_um: tuple[float, ...] = DEFAULT_DIAMETERS_UM,
    spec_kwargs: dict | None = None,
) -> dict:
    """生成数据集（CSV + meta），返回 meta dict。

    正演：`α(f) = φ · K(f, D)`，`φ` 为体积分数（缺省 1e-3），
    `K` 取自 `inversion_kernel`（与 P0-1 反演**同一口径**，否则反演没有可比性）。
    """
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kw = dict(spec_kwargs or {})

    entries = []
    for d_um in diameters_um:
        spec = DatasetSpec(diameter_um=float(d_um), **kw)
        freqs = np.geomspace(spec.f_lo_hz, spec.f_hi_hz, spec.n_points)
        diam = np.array([spec.diameter_um * 1e-6])
        w = np.array([spec.volume_fraction])
        alpha = inversion_kernel(freqs, diam)[:, 0] * w[0]

        name = f"mono_{spec.diameter_um:g}um.csv"
        path = out / name
        with path.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh, lineterminator="\n")
            wr.writerow(["f_hz", "alpha_np_per_m"])
            for f, a in zip(freqs, alpha, strict=True):
                wr.writerow([f"{f:.6e}", f"{a:.10e}"])

        entries.append(
            {
                "file": name,
                "diameter_um": spec.diameter_um,
                "volume_fraction": spec.volume_fraction,
                "n_points": spec.n_points,
                "f_lo_hz": spec.f_lo_hz,
                "f_hi_hz": spec.f_hi_hz,
                # 全局斜率（**不单调**，仅留档；见 power_law_exponent 的说明）
                "power_law_exponent_global": round(power_law_exponent(freqs, alpha), 4),
                # 局部指数 @10 MHz（**随粒径严格单调递减**，这才是 P0-4 的验收量）
                "local_exponent_10mhz": round(local_power_law_exponent(freqs, alpha, 10.0e6), 4),
            }
        )

    meta = {
        "generated_by": "acoustics/dataset.py::generate_monodisperse_dataset",
        "kernel": (
            "K(f,D) = (D/D0)^3 * ka^4/(1+ka^2)^2 + (D/D0)^2 * ka^2/(1+ka^2), ka = pi*f*D/c, c=1500 m/s, D0=10um"
        ),
        "note": "α(f) = φ·K(f,D)；与 acoustics.atten_inverse.inversion_kernel 同一口径",
        "entries": entries,
    }
    # ⚠️ newline="\n" 必须显式给：Windows 上 write_text 默认把 \n 翻成 \r\n，
    # 会让这个 JSON 变成 CRLF，与仓库的 LF 基线不一致（实测踩过一次）。
    (out / "dataset_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta


def load_dataset(path: str | pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """读一条 CSV，返回 `(freqs, alpha)`。"""
    f, a = [], []
    with pathlib.Path(path).open(encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            f.append(float(row["f_hz"]))
            a.append(float(row["alpha_np_per_m"]))
    return np.asarray(f), np.asarray(a)
