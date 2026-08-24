"""射频大脑 · 业余频段白名单（安全约束，与 rsba1_adapter 对齐）

来源：rs-ba1-reverse/src/rsba1/ctypes_wrappers/civ_commands.py 的
AMATEUR_BANDS / is_allowed_freq / assert_allowed_freq（IC-705 CI-V 控制桥）。
rf_brain 内部自持一份数值完全一致的副本，避免跨仓库 import 依赖；
任何"设频率"入口（频谱扫描调度器、IC-705 音频输入）都必须先过这里的校验。

业余频段（闭区间 [lo, hi] Hz）：
- 160m-10m：1.8 - 30 MHz
- 6m：50 - 54 MHz
- 2m：144 - 148 MHz
"""
from __future__ import annotations

AMATEUR_BANDS = (
    (1_800_000, 30_000_000),    # HF 160m - 10m
    (50_000_000, 54_000_000),   # 6m
    (144_000_000, 148_000_000), # 2m
)


def is_allowed_freq(hz) -> bool:
    """判断频率是否落在业余频段白名单内（与 rsba1_adapter.is_allowed_freq 一致）。"""
    hz = int(hz)
    return any(lo <= hz <= hi for lo, hi in AMATEUR_BANDS)


def assert_allowed_freq(hz) -> None:
    """断言频率在白名单内，否则抛 ValueError（与 rsba1_adapter.assert_allowed_freq 一致）。

    异常:
        ValueError - 频率不在业余频段白名单内。
    """
    hz = int(hz)
    if not is_allowed_freq(hz):
        raise ValueError(f"频率 {hz} Hz 不在业余频段白名单内: {AMATEUR_BANDS}")
