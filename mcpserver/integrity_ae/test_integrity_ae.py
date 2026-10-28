"""工单 262 任务 C 验收：AE 包装层。

有样例 pridb 时验证 hit 数 > 0；**无样例时 skip（不许 fail）**。
`cluster_events` / `detect_hits` 是纯逻辑，用真实 pandas DataFrame 测，无需 vallenae。
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from mcpserver.integrity_ae import cluster_events, detect_hits

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ae"
SAMPLE_PRD = FIXTURE_DIR / "sample.pridb"


def _pridb_frame() -> pd.DataFrame:
    """三行：30 dB（低于阈值）/ 45 dB（检出）/ 40 dB（恰好等于阈值，按 > 判定不检出）。"""
    return pd.DataFrame(
        {
            "SETUP_INDEX": [1, 1, 1],
            "CHANNEL": [1, 1, 2],
            "TIME": [1.0, 2.0, 3.0],
            "AMP": [30.0, 45.0, 40.0],
            "amplitude": [30.0, 45.0, 40.0],
            "time": [1.0, 2.0, 3.0],
            "channel": [1, 1, 2],
        }
    )


def test_cluster_events_splits_by_gap() -> None:
    hits = [(0, 100.0), (1, 200.0), (2, 300.0), (3, 5000.0), (4, 5100.0)]
    groups = cluster_events(hits, max_dt_us=1000.0)
    assert groups == [[0, 1, 2], [3, 4]], f"实际 {groups}"


def test_cluster_events_exact_boundary_stays_together() -> None:
    hits = [(0, 0.0), (1, 1000.0)]
    assert cluster_events(hits, max_dt_us=1000.0) == [[0, 1]], "间隔恰好等于阈值应留在同组"


def test_cluster_events_empty_and_negative() -> None:
    assert cluster_events([], max_dt_us=100) == []
    with pytest.raises(ValueError):
        cluster_events([(0, 1.0)], max_dt_us=-1)


def test_cluster_events_accepts_dataframe() -> None:
    """detect_hits 的输出可直接喂给 cluster_events（走 DataFrame 分支）。"""
    df = pd.DataFrame({"index": [7, 8, 9], "time": [0.0, 10.0, 20_000.0]})
    assert cluster_events(df, max_dt_us=1000.0) == [[7, 8], [9]]


def test_detect_hits_filters_by_threshold() -> None:
    hits = detect_hits(_pridb_frame(), None, threshold_db=40.0)
    assert len(hits) == 1, "只应检出 45 dB 那一条（恰好等于阈值的 40 dB 不算）"
    assert hits["amplitude"].tolist() == [45.0]
    assert set(hits.columns) == {"index", "time", "channel", "amplitude"}


def test_detect_hits_missing_amplitude_column() -> None:
    with pytest.raises(KeyError, match="振幅列"):
        detect_hits(pd.DataFrame({"TIME": [1.0]}), None, threshold_db=40.0)


def test_read_pridb_missing_dependency_message() -> None:
    """未装 vallenae 时应抛可读 ImportError（而不是裸 ModuleNotFoundError）。"""
    from mcpserver.integrity_ae.reader import read_pridb

    with pytest.raises(ImportError, match="pip install vallenae"):
        read_pridb("whatever.pridb")


@pytest.mark.skipif(not SAMPLE_PRD.exists(), reason="无样例 pridb（tests/fixtures/ae/ 不入库）")
def test_read_pridb_with_sample() -> None:
    from mcpserver.integrity_ae.reader import read_pridb

    df = read_pridb(str(SAMPLE_PRD))
    assert len(df) > 0, "样例应读出至少一条 hit"
    assert "amplitude" in df.columns, "应提供小写别名列"
