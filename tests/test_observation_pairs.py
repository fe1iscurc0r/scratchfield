"""工单227 任务二 · 观测正对构造测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcpserver.rf_brain.observation_pairs import Observation, build_pairs, load_observations, stats  # noqa: E402


def _obs(ts, freq=433_920_000, cluster=0):
    return Observation(timestamp=ts, freq_hz=freq, power_db=-95.0, snr_db=10.0,
                       metadata={"cluster": cluster})


class TestPairs:
    def test_adjacent_same_window_positive(self):
        obs = [_obs(0), _obs(10), _obs(20)]
        pairs = build_pairs(obs, pos_window_s=60)
        assert all(p.kind == "pos" for p in pairs)
        assert len(pairs) == 2  # (0,1) (1,2)

    def test_far_apart_negative(self):
        obs = [_obs(0), _obs(7200)]  # 2h 差
        pairs = build_pairs(obs, pos_window_s=60, neg_min_gap_s=3600)
        kinds = {p.kind for p in pairs}
        assert kinds == {"neg"}

    def test_no_pair_when_middle_distance(self):
        """间隔在两窗之间（既不正也不负）→ 无对。"""
        obs = [_obs(0), _obs(1800)]  # 30min：>60s 且 <3600s
        assert build_pairs(obs, pos_window_s=60, neg_min_gap_s=3600) == []

    def test_cluster_semantics(self):
        """同簇连续=正对；跨簇=负对（demo 的核心语义）。"""
        obs = ([_obs(t, cluster=0) for t in range(0, 50, 10)]
               + [_obs(t, cluster=1) for t in range(10800, 10850, 10)])
        pairs = build_pairs(obs, pos_window_s=60, neg_min_gap_s=3600)
        pos = [p for p in pairs if p.kind == "pos"]
        neg = [p for p in pairs if p.kind == "neg"]
        assert all(obs[p.a_index].metadata["cluster"] == obs[p.b_index].metadata["cluster"] for p in pos)
        assert all(obs[p.a_index].metadata["cluster"] != obs[p.b_index].metadata["cluster"] for p in neg)
        assert len(pos) == 8 and len(neg) >= 1


class TestStats:
    def test_stats_fields(self):
        obs = [_obs(0), _obs(10), _obs(7200)]
        st = stats(obs, build_pairs(obs, pos_window_s=60, neg_min_gap_s=3600))
        assert st["observations"] == 3
        assert st["pos_pairs"] == 1 and st["neg_pairs"] == 1
        assert st["span_hours"] == 2.0


def test_load_roundtrip(tmp_path):
    f = tmp_path / "obs.ndjson"
    f.write_text('{"timestamp": 2, "freq_hz": 1, "power_db": -90, "snr_db": 5, "metadata": null}\n'
                 '{"timestamp": 1, "freq_hz": 1, "power_db": -91, "snr_db": 4, "metadata": null}\n',
                 encoding="utf-8")
    obs = load_observations(f)
    assert [o.timestamp for o in obs] == [1, 2]  # 载入即按时间排序
