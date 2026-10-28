"""弹性曲线 + 簇规模/跳数权衡 → ``dashboard.json``（**只产数据，不画前端**）。

输出两块图数据
--------------
1. ``resilience_curve``          —— 节点失活率 5% / 10% / 20% / 30% → 数据重建成功率。
2. ``cluster_scale_vs_hops``     —— ``max_hops`` 扫描 → 簇规模 ↑ vs 中继跳数 ↑ 的权衡。
另附 ``rlnc_redundancy_sweep``   —— 固定失活率下扫冗余率 factor，用来说明 RLNC 冗余的实际收益。

重建成功率模型（**刻意简单，别当物理真值**）
------------------------------------------
每个 trial：
1. 生成拓扑 → 按 ``failure_rate`` 随机失活节点 → 按阈值 + 跳数分簇；
2. 取**活成员最多**的簇作为「一代数据的中继组」，其活成员数为 ``A``；
3. 源数据切成 ``k`` 个等长块（``k`` 固定，见 ``DEFAULT_SOURCE_BLOCKS``），
   用**真值源** ``encode_random``（经兼容层）编码成 ``n = k + ⌊k·factor⌋`` 个块；
4. 中继槽位 ``min(A, n)`` 个 —— 超过 ``n`` 个成员也拿不出更多**彼此独立**的组合
   （k 个源块最多张成 n 维，多转发只是重复）。取跳数最近的若干个活成员担当中继，
   每块沿 ``h`` 跳中继的生存率按 ``s^h``（``s = 1 − block_loss_rate``）连乘；
5. 收到的块喂 ``decode_full`` —— **满秩即重建成功**（与源块逐字节比对）。

⚠️ 两个必须知道的口径
- **为什么默认区域是 30 km × 30 km、阈值 −110 dBm**：LoRa（SF7/125 kHz，灵敏度约 −123 dBm）
  单跳覆盖可达数公里，区域太小会退化成**单一巨簇** —— 此时失活率根本不改变最大簇规模，
  曲线会是一条平线（实测 500 m × 500 m 下 5%~30% 全档都是 87.5%）。30 km 下可达半径
  r ≈ 4.56 km、解析平均度 λπr² ≈ 3.6（**实测 ≈ 3.0**）⇒ 落在连通相变（约 4.5）**之下**的
  多簇区（实测 12 簇），分簇才有意义。
- **曲线会有平台段**：当 ``A ≥ n`` 时 n 个中继槽位已满，再多活成员不改变收块分布，
  因此相邻失活率可能给出同一成功率。这不是 bug，是 ``n`` 上限的必然结果。
- **曲线单调是实测性质，不是构造保证**：模型没有强制「活成员越少 ⇒ 成功率越低」，
  簇结构离散时「最大簇」会随失活率切换。文档基线（``DASHBOARD_BASELINE``，随机拓扑）
  实测 10 个 seed 全部单调；网格拓扑 10 个 seed 仅 4 个单调（5%→10% 反弹到 23.3%）。
- 本模型**不是**物理层仿真：没有 MCS / 重传 / 信道时变 / 干扰模型，也没有真实硬件标定。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

from .cluster_sim import (
    DEFAULT_RSSI_THRESHOLD_DBM,
    DEFAULT_TX_POWER_DBM,
    build_clusters,
    cluster_report,
    generate,
    normalize_config,
)
from .cluster_sim.config import apply_failure
from .rlnc import decode_full, encode_random

DEFAULT_FAILURE_LEVELS = (0.05, 0.10, 0.20, 0.30)
DEFAULT_HOP_SWEEP = (1, 2, 3, 4)
DEFAULT_REDUNDANCY_SWEEP = (0.0, 0.3, 0.6, 1.0)
DEFAULT_TRIALS = 60
DEFAULT_SEED = 20261014
# 默认区域取 30 km × 30 km（不是 500 m）——理由见模块 docstring「为什么默认区域是 30 km」
DEFAULT_AREA_M = 30000.0
# 一代源数据的块数与每块字节数（等长才能做逐字节比对）
DEFAULT_SOURCE_BLOCKS = 8
DEFAULT_BLOCK_BYTES = 32
# 「丢包 30%」——工单 §2 任务二.3 的边界用例口径，dashboard 沿用它作块级丢失率
DEFAULT_BLOCK_LOSS_RATE = 0.30
DEFAULT_REDUNDANCY_FACTOR = 0.6
DEFAULT_OUTPUT = "dashboard.json"

# dashboard 的**基线配置**：与 ``build_parser()`` 的默认值**逐项一致**。
#
# ⚠️ 为什么不能直接沿用 ``cluster_sim.config.DEFAULT_CONFIG``（topology="grid"）：
# 同一套「dashboard 默认」若库调用（``build_dashboard()``）走 grid、CLI 走 random，
# 两个入口会给出**两套数字**（实测 5% 失活下 21.7% vs 45.0%）。
# 且网格拓扑节点位置规则、簇结构离散，「最大簇」会随失活率**离散切换** ⇒
# 实测 10 个 seed 里只有 4 个曲线单调、20 次抽样有 6 次在 5%→10% 出现反弹
# （21.7% → 23.3%）；随机拓扑 10/10 单调。故 dashboard 基线显式取 random。
DASHBOARD_BASELINE: dict = {
    "nodes": 50,
    "area": [DEFAULT_AREA_M, DEFAULT_AREA_M],
    "rssi_threshold": DEFAULT_RSSI_THRESHOLD_DBM,
    "topology": "random",
    "tx_power_dbm": DEFAULT_TX_POWER_DBM,
    "seed": DEFAULT_SEED,
}


def _source_blocks(k: int, byte_len: int, rng: random.Random) -> list[bytes]:
    """生成 k 个等长源块（内容随机、彼此独立）。"""
    return [rng.randbytes(byte_len) for _ in range(k)]


def _trial(
    cfg: dict,
    *,
    failure_rate: float,
    k: int,
    factor: float,
    block_loss_rate: float,
    trial_seed: int,
) -> dict:
    """跑一个 trial，返回该次的观测（供成功率曲线与诊断共用）。"""
    topo = generate(
        cfg["topology"],
        cfg["nodes"],
        width=cfg["area"][0],
        height=cfg["area"][1],
        seed=trial_seed,
        tx_power_dbm=cfg["tx_power_dbm"],
        freq_hz=cfg["freq_hz"],
        path_loss_exponent=cfg["path_loss_exponent"],
    )
    apply_failure(topo.nodes, failure_rate, seed=trial_seed)
    clusters = build_clusters(
        topo.nodes,
        threshold_dbm=cfg["rssi_threshold"],
        max_hops=cfg["max_hops"],
        freq_hz=cfg["freq_hz"],
        exponent=cfg["path_loss_exponent"],
    )
    if not clusters:
        return {"success": False, "alive_members": 0, "relay_slots": 0, "mean_relay_hops": 0.0,
                "blocks_sent": 0, "blocks_received": 0, "reason": "no_alive_nodes"}
    largest = max(clusters, key=lambda c: (len(c.alive_members), c.size))
    alive_members = len(largest.alive_members)
    if alive_members == 0:
        return {"success": False, "alive_members": 0, "relay_slots": 0, "mean_relay_hops": 0.0,
                "blocks_sent": 0, "blocks_received": 0, "reason": "no_alive_members"}

    rng = random.Random(trial_seed ^ 0x5EED)
    source = _source_blocks(k, DEFAULT_BLOCK_BYTES, rng)
    encoded = encode_random(source, factor=factor, seed=trial_seed)
    # 中继槽位：至多 min(A, n) 个——超过 n 个成员也拿不出更多**彼此独立**的组合
    # （k 个源块最多张成 n = k + r 维，多转发只是重复）
    slots = min(alive_members, len(encoded))
    # 取跳数最近的 slots 个活成员当中继（hops 升序，id 升序做确定性 tie-break）
    relays = sorted(largest.alive_members, key=lambda m: (largest.hops[m], m))[:slots]
    blocks = rng.sample(encoded, slots)
    # 块沿 h 跳中继的生存率 = s^h（s = 1 − block_loss_rate）
    survival_per_hop = 1.0 - block_loss_rate
    received = [
        blk
        for member, blk in zip(relays, blocks)
        if rng.random() < survival_per_hop ** largest.hops[member]
    ]
    decoded = decode_full(received, k=k)
    mean_relay_hops = (
        round(sum(largest.hops[m] for m in relays) / len(relays), 3) if relays else 0.0
    )
    return {
        "success": decoded == source,
        "alive_members": alive_members,
        "relay_slots": slots,
        "mean_relay_hops": mean_relay_hops,
        "blocks_sent": len(encoded),
        "blocks_received": len(received),
        "reason": "ok" if decoded == source else ("underdetermined" if len(received) < k else "rank_deficient"),
    }


def reconstruction_success_rate(
    cfg: dict,
    *,
    failure_rate: float,
    trials: int = DEFAULT_TRIALS,
    k: int = DEFAULT_SOURCE_BLOCKS,
    factor: float = DEFAULT_REDUNDANCY_FACTOR,
    block_loss_rate: float = DEFAULT_BLOCK_LOSS_RATE,
    seed: int = DEFAULT_SEED,
) -> dict:
    """一个失活率下的数据重建成功率（``trials`` 次蒙特卡洛）。"""
    if trials <= 0:
        raise ValueError("trials 必须为正")
    if not 0.0 <= failure_rate <= 1.0:
        raise ValueError("failure_rate 必须在 [0, 1]")
    if not 0.0 <= block_loss_rate <= 1.0:
        raise ValueError("block_loss_rate 必须在 [0, 1]")
    runs = [
        _trial(cfg, failure_rate=failure_rate, k=k, factor=factor,
               block_loss_rate=block_loss_rate, trial_seed=seed + i)
        for i in range(trials)
    ]
    successes = sum(1 for r in runs if r["success"])
    return {
        "failure_rate": failure_rate,
        "trials": trials,
        "successes": successes,
        "success_rate": round(successes / trials, 6),
        "k": k,
        "redundancy_factor": factor,
        "block_loss_rate": block_loss_rate,
        "mean_alive_members": round(sum(r["alive_members"] for r in runs) / trials, 3),
        "mean_relay_slots": round(sum(r["relay_slots"] for r in runs) / trials, 3),
        "mean_relay_hops": round(sum(r["mean_relay_hops"] for r in runs) / trials, 3),
        "mean_blocks_received": round(sum(r["blocks_received"] for r in runs) / trials, 3),
        # 按「结局原因」计数，**含成功档 `"ok"`** ⇒ sum(reason_counts.values()) == trials。
        # （曾名 `failure_reasons`，但混入 ok 会让「把各档相加当失败数」的读法出错，故更名。）
        "reason_counts": {
            reason: sum(1 for r in runs if r["reason"] == reason)
            for reason in sorted({r["reason"] for r in runs})
        },
    }


def cluster_scale_vs_hops(
    cfg: dict,
    *,
    hops: tuple[int, ...] = DEFAULT_HOP_SWEEP,
    failure_rate: float = 0.0,
    seed: int = DEFAULT_SEED,
) -> dict:
    """``max_hops`` 扫描：跳数放宽 ⇒ 簇更大、簇数更少，但平均中继跳数上升。"""
    rows = []
    w, h = cfg["area"]
    for max_hops in hops:
        topo = generate(
            cfg["topology"],
            cfg["nodes"],
            width=w,
            height=h,
            seed=seed,
            tx_power_dbm=cfg["tx_power_dbm"],
            freq_hz=cfg["freq_hz"],
            path_loss_exponent=cfg["path_loss_exponent"],
        )
        apply_failure(topo.nodes, failure_rate, seed=seed)
        report = cluster_report(
            topo.nodes,
            threshold_dbm=cfg["rssi_threshold"],
            max_hops=max_hops,
            freq_hz=cfg["freq_hz"],
            exponent=cfg["path_loss_exponent"],
        )
        stats = report["stats"]
        mean_hops = 0.0
        clusters = report["clusters"]
        if clusters:
            mean_hops = sum(c["mean_hops"] for c in clusters) / len(clusters)
        rows.append({
            "max_hops": max_hops,
            "cluster_count": stats["cluster_count"],
            "mean_cluster_size": stats["mean_cluster_size"],
            "largest_cluster": stats["largest_cluster"],
            "mean_hops": round(mean_hops, 4),
            "mean_health": stats["mean_health"],
        })
    return {"axis": [r["max_hops"] for r in rows], "rows": rows}


def rlnc_redundancy_sweep(
    cfg: dict,
    *,
    factors: tuple[float, ...] = DEFAULT_REDUNDANCY_SWEEP,
    failure_rate: float = 0.20,
    trials: int = DEFAULT_TRIALS,
    k: int = DEFAULT_SOURCE_BLOCKS,
    block_loss_rate: float = DEFAULT_BLOCK_LOSS_RATE,
    seed: int = DEFAULT_SEED,
) -> dict:
    """固定失活率下扫冗余率：用来说明「多花带宽换成功率」的实际斜率。"""
    rows = [
        reconstruction_success_rate(
            cfg, failure_rate=failure_rate, trials=trials, k=k, factor=factor,
            block_loss_rate=block_loss_rate, seed=seed,
        )
        for factor in factors
    ]
    return {
        "failure_rate": failure_rate,
        "axis": [r["redundancy_factor"] for r in rows],
        "success_rate": [r["success_rate"] for r in rows],
        "mean_blocks_sent": [
            math.floor(r["redundancy_factor"] * k) + k for r in rows
        ],
        "rows": rows,
    }


def build_dashboard(
    cfg: dict | None = None,
    *,
    failure_levels: tuple[float, ...] = DEFAULT_FAILURE_LEVELS,
    hops: tuple[int, ...] = DEFAULT_HOP_SWEEP,
    trials: int = DEFAULT_TRIALS,
    focus_failure: float | None = None,
    k: int = DEFAULT_SOURCE_BLOCKS,
    factor: float = DEFAULT_REDUNDANCY_FACTOR,
    block_loss_rate: float = DEFAULT_BLOCK_LOSS_RATE,
    seed: int = DEFAULT_SEED,
) -> dict:
    """产出完整 dashboard 数据（**不含时间戳**，同参数同结果，便于回归比对）。

    ``cfg=None`` 时用 ``DASHBOARD_BASELINE``（= CLI 默认值），**不是**
    ``cluster_sim.DEFAULT_CONFIG`` —— 两者 topology 不同，理由见 ``DASHBOARD_BASELINE`` 注释。
    """
    normalized = normalize_config(DASHBOARD_BASELINE if cfg is None else cfg)
    curve = [
        reconstruction_success_rate(
            normalized, failure_rate=rate, trials=trials, k=k, factor=factor,
            block_loss_rate=block_loss_rate, seed=seed,
        )
        for rate in failure_levels
    ]
    payload = {
        "model": {
            "summary": ("最大簇活成员数决定中继槽位（≤ n）；块沿 h 跳中继的生存率为 s^h"
                        "（s = 1 − block_loss_rate）；收到 ≥ k 个线性无关块即重建成功。"),
            "source_blocks_k": k,
            "block_bytes": DEFAULT_BLOCK_BYTES,
            "redundancy_factor": factor,
            "encoded_blocks_n": k + math.floor(k * factor),
            "block_loss_rate": block_loss_rate,
            "trials_per_point": trials,
            "seed": seed,
            "caveat": ("非物理层仿真：无 MCS / 重传 / 信道时变 / 干扰模型，未做硬件标定。"
                       "且 A ≥ n 时曲线会出现平台段（中继槽位已满），非 bug。"
                       "曲线单调是**随机拓扑基线的实测性质，非构造保证**："
                       "网格拓扑因最大簇离散切换，实测 10 个 seed 仅 4 个单调"
                       "（5%→10% 会在 21.7%↔23.3% 间反弹）。"),
        },
        "config": dict(normalized),
        "resilience_curve": {
            "axis": [r["failure_rate"] for r in curve],
            "success_rate": [r["success_rate"] for r in curve],
            "rows": curve,
        },
        "cluster_scale_vs_hops": cluster_scale_vs_hops(normalized, hops=hops, seed=seed),
        "rlnc_redundancy_sweep": rlnc_redundancy_sweep(
            normalized, failure_rate=0.20, trials=trials, k=k,
            block_loss_rate=block_loss_rate, seed=seed,
        ),
    }
    if focus_failure is not None:
        payload["focus"] = reconstruction_success_rate(
            normalized, failure_rate=focus_failure, trials=trials, k=k, factor=factor,
            block_loss_rate=block_loss_rate, seed=seed,
        )
    return payload


def write_dashboard(payload: dict, path: str | Path = DEFAULT_OUTPUT) -> Path:
    """落盘 dashboard.json（UTF-8 + **LF**，缩进 2）。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mcpserver.esp32.dashboard",
        description="ESP32/LoRa 分簇 + RLNC 弹性仪表盘（只产 dashboard.json，不画前端）",
    )
    parser.add_argument("--nodes", type=int, default=50, help="节点数（默认 50）")
    parser.add_argument("--failure", type=float, default=None,
                        help="焦点失活率（如 0.2）；曲线仍按 5/10/20/30%% 全扫")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="每个点的蒙特卡洛次数")
    parser.add_argument("--topology", default="random", help="grid | random | lora_deployment")
    parser.add_argument("--area", type=float, nargs=2, default=[DEFAULT_AREA_M, DEFAULT_AREA_M],
                        metavar=("W", "H"), help="区域尺寸（m，默认 30000×30000）")
    parser.add_argument("--rssi-threshold", type=float, default=DEFAULT_RSSI_THRESHOLD_DBM,
                        help="可达阈值 dBm")
    parser.add_argument("--tx-power", type=float, default=DEFAULT_TX_POWER_DBM,
                        help="发射功率 dBm")
    parser.add_argument("--block-loss", type=float, default=DEFAULT_BLOCK_LOSS_RATE,
                        help="块级丢失率（默认 0.30）")
    parser.add_argument("--redundancy-factor", type=float, default=DEFAULT_REDUNDANCY_FACTOR,
                        help="RLNC 冗余率（默认 0.6）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子（可复现）")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出路径（默认 dashboard.json）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = normalize_config({
        "nodes": args.nodes,
        "area": list(args.area),
        "rssi_threshold": args.rssi_threshold,
        "topology": args.topology,
        "tx_power_dbm": args.tx_power,
        "seed": args.seed,
    })
    payload = build_dashboard(
        cfg,
        trials=args.trials,
        focus_failure=args.failure,
        factor=args.redundancy_factor,
        block_loss_rate=args.block_loss,
        seed=args.seed,
    )
    out = write_dashboard(payload, args.output)
    curve = payload["resilience_curve"]
    print(f"[dashboard] nodes={args.nodes} topology={args.topology} seed={args.seed}")
    for rate, succ, row in zip(curve["axis"], curve["success_rate"], curve["rows"]):
        print(f"  failure {rate:>5.0%} → 重建成功 {succ:>6.1%}  "
              f"(活成员均值 {row['mean_alive_members']}, 收块均值 {row['mean_blocks_received']})")
    if "focus" in payload:
        focus = payload["focus"]
        print(f"  [focus] failure {focus['failure_rate']:.0%} → {focus['success_rate']:.1%} "
              f"({focus['successes']}/{focus['trials']})")
    print(f"[dashboard] 已写出 {out} ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
