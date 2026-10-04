"""射频大脑 · liquid-dsp ctypes 后端（Phase 4）

用 liquid-dsp（MIT）的 spgramcf 周期图替换 feature_extractor 里的
numpy FFT 参考实现。接口保持纯函数：``power_spectrum(iq)`` 返回
与 numpy 路径同语义的线性功率谱（fftshift 后，长度 = len(iq)）。

降级策略（同 rsba1_adapter 的 RadioLink→RemoteUty 模式）：
- DLL 可定位 → 走 liquid C 库
- DLL 缺失 → ``is_available()=False``，调用方回退 numpy 参考实现

DLL 定位顺序：
1. 环境变量 ``LIQUID_DSP_LIB``（完整路径）
2. 仓库 ``vendor/libliquid.{dll,so,dylib}``
3. ``github_haul/physical/liquid-dsp/src/.libs/libliquid.{dll,so}``（天选7 克隆布局）

API 对齐 liquid-dsp 1.6.x：
``spgramcf_create(nfft, wtype, wlen, delay)`` / ``spgramcf_execute`` /
``spgramcf_get_pxx`` / ``spgramcf_clear`` / ``spgramcf_destroy``。
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# liquid-dsp 窗类型枚举（include/liquid/firdes.h: liquid_firdes_filter_type）
LIQUID_FIRFILT_HAMMING = 6

_REPO_ROOT = Path(__file__).resolve().parents[2]

_LIB_NAMES = {
    "win32": ["libliquid.dll", "liquid.dll"],
    "darwin": ["libliquid.dylib"],
}
_LIB_NAMES_DEFAULT = ["libliquid.so", "libliquid.so.1"]

_CANDIDATE_DIRS = [
    _REPO_ROOT / "vendor",
    _REPO_ROOT / "github_haul" / "physical" / "liquid-dsp" / "src" / ".libs",
    _REPO_ROOT / "github_haul" / "physical" / "liquid-dsp",
]

_lib: ctypes.CDLL | None = None
_load_attempted = False


def _lib_candidates() -> list[Path]:
    env = os.environ.get("LIQUID_DSP_LIB", "").strip()
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    names = _LIB_NAMES.get(sys.platform, _LIB_NAMES_DEFAULT)
    for d in _CANDIDATE_DIRS:
        paths.extend(d / name for name in names)
    return paths


def _load_lib() -> ctypes.CDLL | None:
    """定位并加载 libliquid；失败返回 None（调用方降级到 numpy）。"""
    global _lib, _load_attempted
    if _load_attempted:
        return _lib
    _load_attempted = True
    for path in _lib_candidates():
        if not path.is_file():
            logger.debug("[rf_brain] libliquid 候选路径不存在: %s", path)
            continue
        try:
            lib = ctypes.CDLL(str(path))
            # 签名声明：spgramcf_* 系列（liquid-dsp 1.6.x）
            lib.spgramcf_create.restype = ctypes.c_void_p
            lib.spgramcf_create.argtypes = [
                ctypes.c_uint,   # nfft
                ctypes.c_int,    # wtype
                ctypes.c_uint,   # wlen
                ctypes.c_uint,   # delay
            ]
            lib.spgramcf_execute.argtypes = [ctypes.c_void_p, np.ctypeslib.ndpointer(np.complex64), ctypes.c_uint]
            lib.spgramcf_get_pxx.argtypes = [ctypes.c_void_p, np.ctypeslib.ndpointer(np.float32)]
            lib.spgramcf_clear.argtypes = [ctypes.c_void_p]
            lib.spgramcf_destroy.argtypes = [ctypes.c_void_p]
            _lib = lib
            logger.info("[rf_brain] liquid-dsp 已加载: %s", path)
            return _lib
        except (OSError, AttributeError) as exc:
            logger.warning("[rf_brain] 加载 %s 失败: %s", path, exc)
    logger.warning("[rf_brain] libliquid 未找到，特征提取保持 numpy 参考实现"
                   "（本进程不再重试，部署 DLL 后需重启）。")
    return None


def is_available() -> bool:
    """liquid-dsp 后端是否可用（DLL 可加载）。"""
    return _load_lib() is not None


def power_spectrum(iq: np.ndarray) -> np.ndarray:
    """spgramcf 周期图：返回 fftshift 后的线性功率谱（与 numpy 参考同布局）。

    语义对齐 feature_extractor 的 ``|fft(iq * hanning)|^2 + fftshift``：
    nfft = len(iq)，Hamming 窗，wlen=nfft，delay=1（逐样本累积）。
    """
    lib = _load_lib()
    if lib is None:
        raise RuntimeError("liquid-dsp 不可用；先检查 is_available() 再决定是否回退 numpy。")

    x = np.ascontiguousarray(iq, dtype=np.complex64)
    n = len(x)
    pxx = np.empty(n, dtype=np.float32)
    q = lib.spgramcf_create(ctypes.c_uint(n), LIQUID_FIRFILT_HAMMING, ctypes.c_uint(n), ctypes.c_uint(1))
    if not q:
        raise RuntimeError("spgramcf_create 失败（nfft=%d）" % n)
    try:
        lib.spgramcf_execute(q, x, ctypes.c_uint(n))
        lib.spgramcf_get_pxx(q, pxx)
    finally:
        lib.spgramcf_destroy(q)
    # liquid pxx 布局同 fft 原始序（0→正频→负频），shift 到中心与 numpy 参考一致
    return np.fft.fftshift(pxx.astype(np.float64))
