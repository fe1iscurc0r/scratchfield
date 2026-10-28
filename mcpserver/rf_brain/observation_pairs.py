"""rf_brain 观测档案 · 自监督正对构造（工单227 任务二）.

料源：docs/pollination/channel2world-sdr-2026-10.md（工单226 任务四勘察的候选行动项）。

思想（Channel2World 方法论降级到单 SDR）：
- **正对** = 同一时段相邻两次观测（环境未变——底噪/占用结构应稳定）；
- **负对** = 跨时段远距观测（环境可能变——用于对比学习另一极）；
- 只备料不训练：输出对文件 + 统计，为后续"射频环境档案"（embedding 表征）铺数据。
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Observation:
    """最小观测日志格式（ndjson 一行一条）。"""

    timestamp: float          # epoch 秒
    freq_hz: float
    power_db: float
    snr_db: float | None = None
    metadata: dict | None = None


@dataclass
class Pair:
    kind: str                 # "pos" / "neg"
    a_index: int
    b_index: int
    gap_seconds: float


def load_observations(path: str | Path) -> list[Observation]:
    obs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            obs.append(Observation(**json.loads(line)))
    obs.sort(key=lambda o: o.timestamp)
    return obs


def build_pairs(
    obs: list[Observation],
    pos_window_s: float = 60.0,
    neg_min_gap_s: float = 3600.0,
) -> list[Pair]:
    """构造正负对.

    正对：时间差 ≤ pos_window_s 的相邻观测（i, i+1 顺序配对，不交叉）。
    负对：时间差 ≥ neg_min_gap_s 的采样配对（每 obs 最多入一对负对，防爆炸）。
    """
    pairs: list[Pair] = []
    used_neg: set[int] = set()
    for i in range(len(obs) - 1):
        gap = obs[i + 1].timestamp - obs[i].timestamp
        if gap <= pos_window_s:
            pairs.append(Pair("pos", i, i + 1, gap))
    # 负对：首尾滑窗（每个观测找第一个 ≥neg_min_gap 的对象）
    j = 0
    for i in range(len(obs)):
        j = max(j, i + 1)
        while j < len(obs) and obs[j].timestamp - obs[i].timestamp < neg_min_gap_s:
            j += 1
        if j < len(obs) and i not in used_neg and j not in used_neg:
            pairs.append(Pair("neg", i, j, obs[j].timestamp - obs[i].timestamp))
            used_neg.update((i, j))
    return pairs


def stats(obs: list[Observation], pairs: list[Pair]) -> dict:
    pos = [p for p in pairs if p.kind == "pos"]
    neg = [p for p in pairs if p.kind == "neg"]
    span = (obs[-1].timestamp - obs[0].timestamp) if len(obs) > 1 else 0.0
    return {
        "observations": len(obs),
        "span_hours": round(span / 3600, 2),
        "pos_pairs": len(pos),
        "neg_pairs": len(neg),
        "pos_neg_ratio": round(len(pos) / len(neg), 2) if neg else None,
        "pos_gap_median_s": (
            round(sorted(p.gap_seconds for p in pos)[len(pos) // 2], 1) if pos else None
        ),
    }


# ── demo ──

def _demo() -> int:
    import time

    t0 = time.time() - 8 * 3600  # 8 小时前起
    obs: list[Observation] = []
    ts = t0
    # 三个时段簇（每簇 5 条，间隔 10s；簇间隔 3h）——同簇=正对候选，跨簇=负对
    for cluster in range(3):
        for k in range(5):
            obs.append(Observation(
                timestamp=ts, freq_hz=433_920_000 + cluster * 1000,
                power_db=-95.0 + k * 0.5, snr_db=10.0 + k,
                metadata={"site": "lab", "cluster": cluster}))
            ts += 10
        ts += 3 * 3600
    pairs = build_pairs(obs)
    st = stats(obs, pairs)
    print("=== 观测正对构造 demo（3 时段簇 × 5 观测）===")
    print(f"观测 {st['observations']} 条 | 跨度 {st['span_hours']}h | "
          f"正对 {st['pos_pairs']} | 负对 {st['neg_pairs']} | 正负比 {st['pos_neg_ratio']}")
    for p in pairs[:3] + pairs[-2:]:
        print(f"  {p.kind}: obs[{p.a_index}]↔obs[{p.b_index}] gap={p.gap_seconds:.0f}s")
    # 构造正确性：正对全部同簇、负对全部跨簇
    ok_pos = all(
        (obs[p.a_index].metadata or {}).get("cluster") == (obs[p.b_index].metadata or {}).get("cluster")
        for p in pairs if p.kind == "pos")
    ok_neg = all(
        (obs[p.a_index].metadata or {}).get("cluster") != (obs[p.b_index].metadata or {}).get("cluster")
        for p in pairs if p.kind == "neg")
    print(f"校验：正对同簇={ok_pos} 负对跨簇={ok_neg}")
    return 0 if (ok_pos and ok_neg and st["pos_pairs"] >= 12 and st["neg_pairs"] >= 1) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="rf_brain 观测正对构造（工单227 PoC）")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--obs", help="观测 ndjson 文件")
    ap.add_argument("--out", help="对文件输出路径（ndjson）")
    args = ap.parse_args()
    if args.demo:
        return _demo()
    if args.obs:
        obs = load_observations(args.obs)
        pairs = build_pairs(obs)
        print(json.dumps(stats(obs, pairs), ensure_ascii=False, indent=2))
        if args.out:
            Path(args.out).write_text(
                "\n".join(json.dumps(asdict(p), ensure_ascii=False) for p in pairs) + "\n",
                encoding="utf-8")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
