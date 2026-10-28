"""PRIDB 读取（vallenae 包装，不复制其源码）。"""
from __future__ import annotations

from typing import Any

_PRIDB_ALIASES = {
    "SETUP_INDEX": "setup_index",
    "CHANNEL": "channel",
    "TIME": "time",
    "AMP": "amplitude",
    "RISE": "rise_time",
    "COUNT": "counts",
    "ENER": "energy",
    "DURATION": "duration",
    "TRAI": "trai",
    "PCNTS": "partial_counts",
}


def _import_vallenae() -> Any:
    """延迟导入；缺包时给可读提示（工单 §2「不许裸 traceback」）。"""
    try:
        import vallenae  # noqa: F401
    except ImportError as exc:
        raise ImportError("需要 vallenae：pip install vallenae") from exc
    return vallenae


def read_pridb(path: str) -> Any:
    """读 PRIDB 参数表，返回 pandas.DataFrame。

    * 保留上游原始列名（`SETUP_INDEX`/`CHANNEL`/`TIME`/`AMP` ...）；
    * 同时追加小写别名列（`setup_index`/`channel`/`time`/`amplitude` ...），
      方便下游按统一口径取列而不用记上游大小写。

    Raises:
        ImportError: 未安装 vallenae。
        FileNotFoundError: 文件不存在。
    """
    vallenae = _import_vallenae()

    import os

    if not os.path.exists(path):
        raise FileNotFoundError(f"PRIDB 不存在: {path}")

    prd = vallenae.io.PriDatabase(path)
    df = prd.read(time_unit="us")

    for upper, lower in _PRIDB_ALIASES.items():
        if upper in df.columns and lower not in df.columns:
            df[lower] = df[upper]
    return df
