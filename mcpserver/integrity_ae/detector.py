"""hit 检出与事件聚类（纯逻辑，不依赖 vallenae）。"""
from __future__ import annotations

from typing import Any, Sequence

DEFAULT_THRESHOLD_DB = 40.0


def detect_hits(pridb: Any, tradb: Any = None, threshold_db: float = DEFAULT_THRESHOLD_DB) -> Any:
    """按振幅阈值筛出 hit，返回 DataFrame（列：`index`/`time`/`channel`/`amplitude`）。

    Args:
        pridb: `read_pridb()` 的返回（或任何带 `amplitude`/`AMP` 列的 DataFrame）
        tradb: 波形表，本函数**不使用**（保留签名，二期做波形级判定时的入口）
        threshold_db: 振幅阈值（dB，AE 常用 40 dB 起）

    Notes:
        阈值判定用 `>` 而非 `>=`：恰好等于阈值的 hit 不算检出，避免边界样本反复进出。
    """
    del tradb  # 一期不做波形级判定
    amp_col = "amplitude" if "amplitude" in pridb.columns else "AMP"
    if amp_col not in pridb.columns:
        raise KeyError("PRIDB 缺少振幅列（amplitude / AMP）")

    mask = pridb[amp_col] > float(threshold_db)
    hits = pridb.loc[mask]

    time_col = "time" if "time" in hits.columns else "TIME"
    ch_col = "channel" if "channel" in hits.columns else "CHANNEL"
    out = hits.assign(
        index=hits.index,
        time=hits[time_col] if time_col in hits.columns else float("nan"),
        channel=hits[ch_col] if ch_col in hits.columns else -1,
        amplitude=hits[amp_col],
    )
    return out.loc[:, ["index", "time", "channel", "amplitude"]].reset_index(drop=True)


def cluster_events(hits: Any, max_dt_us: float = 1000.0) -> list[list[int]]:
    """按时间间隔聚类，返回 hit 索引组的列表（每组内相邻间隔 ≤ `max_dt_us`）。

    * `hits` 可以是 `detect_hits()` 的 DataFrame（按 `time` 列），也可以是
      `[(index, time), ...]` 形式的序列；
    * 先按时间升序，再线性扫描切分，复杂度 O(n log n)；
    * 组内保存的是**原始 hit 索引**（`index` 列的值），不是行号。
    """
    if max_dt_us < 0:
        raise ValueError("max_dt_us 不能为负")

    if hasattr(hits, "columns"):
        if "time" not in hits.columns or "index" not in hits.columns:
            raise KeyError("hits 需要 time / index 两列")
        pairs = sorted(zip(hits["time"].tolist(), hits["index"].tolist()), key=lambda p: p[0])
    else:
        pairs = sorted(((float(t), int(i)) for i, t in hits), key=lambda p: p[0])

    groups: list[list[int]] = []
    current: list[int] = []
    prev_t: float | None = None
    for t, idx in pairs:
        if prev_t is not None and (float(t) - float(prev_t)) > float(max_dt_us):
            groups.append(current)
            current = []
        current.append(int(idx))
        prev_t = t
    if current:
        groups.append(current)
    return groups


def _flatten(groups: Sequence[Sequence[int]]) -> list[int]:
    """测试辅助：把聚类的索引组摊平。"""
    return [i for g in groups for i in g]
