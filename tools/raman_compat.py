"""RamanSPy 0.2.10 兼容 shim（接入前置：`import raman_compat` 即生效）。

依据 docs/RamanSPy-深挖评估-2026-09-08.md 的两个硬兼容坑：
1. matplotlib ≥3.9 移除 `plt.cm.get_cmap` → RamanSPy plot 崩。
   解法 A（采用）：顶部 monkey-patch `matplotlib.cm.get_cmap`。
2. scipy ≥1.13 移除私有模块 `scipy.linalg._flinalg` → pysptools NFINDR 崩。
   解法 A（采用）：守卫注入 `scipy.linalg._flinalg` shim（sdet_c 用 np.linalg.det）。

纪律：只 patch 缺失的兼容面，不覆盖现有行为；幂等（重复 import 无副作用）。
"""
from __future__ import annotations

import numpy as np


def _patch_matplotlib_get_cmap() -> None:
    try:
        import matplotlib
        import matplotlib.cm as cm
    except Exception:
        return
    if hasattr(cm, "get_cmap"):
        return
    try:
        cm.get_cmap = lambda name=None, lut=None: matplotlib.colormaps[name or "viridis"]
    except Exception:
        pass


def _patch_scipy_flinalg() -> None:
    try:
        import scipy.linalg
    except Exception:
        return
    if hasattr(scipy.linalg, "_flinalg"):
        return
    try:
        import types

        mod = types.ModuleType("scipy.linalg._flinalg")
        mod.sdet_c = lambda a: (float(np.linalg.det(a)), 0)
        scipy.linalg._flinalg = mod
    except Exception:
        pass


def apply() -> None:
    """应用全部兼容 shim（幂等）。"""
    _patch_matplotlib_get_cmap()
    _patch_scipy_flinalg()


apply()
