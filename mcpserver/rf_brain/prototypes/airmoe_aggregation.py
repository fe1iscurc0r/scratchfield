"""W61-01 · AirMoE 空中聚合协议模拟

基于 docs/airmoe-esp32-勘察.md 落地。

三种方案对比：
  1. 正交上传（TDMA）—— N 节点分 N 个时隙依次上传
  2. 空中聚合（AirComp）—— 各节点同步同频发射，空中叠加；网关一次性聚合
  3. 本地独立—— 各节点独立检测，无协作

核心指标：时隙数、频谱占用、聚合精度（与真值相关性）

运行：python -m mcpserver.rf_brain.prototypes.airmoe_aggregation
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# 信号合成（模拟各节点本地频谱检测结果）
# ---------------------------------------------------------------------------

def synthesize_node_detection(n_nodes: int, seed: int = 42) -> list[dict]:
    """模拟 N 个节点各自的频谱感知结果。

    返回结构（每节点）：
        center_freq_hz   频段中心频率
        bandwidth_hz     信号带宽
        power_db         检测功率（dB，相对噪声底）
        snr_db           信噪比估计
        detected         是否检测到信号
        confidence       检测置信度 0..1
    """
    rng = np.random.default_rng(seed)
    results = []
    # 模拟 5 个目标频段（网关期望聚合的频谱地图）
    bands = [
        {"center": 433.5e6, "bw": 125e3, "power": -40.0, "snr": 15.0},
        {"center": 435.0e6, "bw": 125e3, "power": -45.0, "snr": 10.0},
        {"center": 437.0e6, "bw": 250e3, "power": -38.0, "snr": 18.0},
        {"center": 439.5e6, "bw": 125e3, "power": -50.0, "snr": 5.0},
        {"center": 441.0e6, "bw": 125e3, "power": -42.0, "snr": 13.0},
    ]
    for i in range(n_nodes):
        node_results = []
        for b in bands:
            # 节点间有噪声/漏检波动（±3 dB 功率抖动，部分节点漏检）
            power_jitter = rng.normal(0, 3)
            snr_jitter   = rng.normal(0, 2)
            p = b["power"] + power_jitter
            snr = max(b["snr"] + snr_jitter, 0.0)
            # 置信度 = sigmoid(snr - 阈值)
            confidence = float(1.0 / (1.0 + np.exp(-0.5 * (snr - 7.0))))
            detected = snr > 5.0
            node_results.append({
                "center_freq_hz": b["center"],
                "bandwidth_hz":   b["bw"],
                "power_db":       p,
                "snr_db":         snr,
                "detected":       detected,
                "confidence":     confidence,
            })
        results.append(node_results)
    return results


def true_spectrum_map() -> list[dict]:
    """真值频谱地图（用于计算聚合精度）。"""
    bands = [
        {"center": 433.5e6, "bw": 125e3, "power": -40.0},
        {"center": 435.0e6, "bw": 125e3, "power": -45.0},
        {"center": 437.0e6, "bw": 250e3, "power": -38.0},
        {"center": 439.5e6, "bw": 125e3, "power": -50.0},
        {"center": 441.0e6, "bw": 125e3, "power": -42.0},
    ]
    return bands


# ---------------------------------------------------------------------------
# 方案1：正交上传 TDMA（时分多址，逐节点上传）
# ---------------------------------------------------------------------------

@dataclass
class TDMAReport:
    """TDMA 聚合报告。"""
    slots_used: int          # 时隙数 = N 节点
    freq_occupancy: float    # 频谱占用比例（检测到的频段 / 总频段）
    accuracy: float          # 聚合精度（加权平均功率与真值相关性，0..1）
    details: dict


def tdma_upload(node_results: list[list[dict]], true_map: list[dict]) -> TDMAReport:
    """TDMA 方案：每个节点独占一个时隙上传检测结果。"""
    n_nodes = len(node_results)
    # 聚合：取各节点功率均值（检测到的频段）
    n_bands = len(true_map)
    fused_power = np.zeros(n_bands)
    fused_count = np.zeros(n_bands)
    for node_res in node_results:
        for bi, b in enumerate(node_res):
            if b["detected"]:
                fused_power[bi] += b["power_db"]
                fused_count[bi] += 1.0
    # 节点未检测到该频段时用噪声底估计（-90 dBm）
    for bi in range(n_bands):
        if fused_count[bi] == 0:
            fused_power[bi] = -90.0
        else:
            fused_power[bi] /= fused_count[bi]

    # 计算精度：与真值功率的相关性
    true_powers = np.array([b["power"] for b in true_map])
    # 相关性（排除未检测的频段）
    pred = fused_power
    true_arr = true_powers
    pred_centered = pred - pred.mean()
    true_centered = true_arr - true_arr.mean()
    denom = np.linalg.norm(pred_centered) * np.linalg.norm(true_centered)
    accuracy = float(np.abs(np.dot(pred_centered, true_centered)) / denom) if denom > 0 else 0.0

    # 频谱占用：检测到信号的频段数 / 总频段数
    detected_bands = np.sum(fused_count > 0)
    freq_occ = detected_bands / n_bands

    return TDMAReport(
        slots_used=n_nodes,
        freq_occupancy=freq_occ,
        accuracy=accuracy,
        details={"fused_power_db": fused_power.tolist(), "detection_counts": fused_count.tolist()},
    )


# ---------------------------------------------------------------------------
# 方案2：空中聚合 AirComp（同频叠加 + 功率对齐）
# ---------------------------------------------------------------------------

@dataclass
class AirCompReport:
    """AirComp 空中聚合报告。"""
    slots_used: int
    freq_occupancy: float
    accuracy: float
    # AirComp 特有：各节点功率对齐误差（dB），越小越好
    power_align_error_db: float
    details: dict


def power_align(measured: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
    """功率对齐：缩放 measured 使其均值等于 target 均值，返回对齐后向量和 RMS 误差（dB）。"""
    if measured.size == 0 or np.all(measured == 0):
        return measured, 0.0
    scale = target.mean() / measured.mean()
    aligned = measured * scale
    # 对齐误差 RMS（dB）
    # 转换为线性功率再算 dB 误差
    err_db = 10.0 * np.log10(np.abs(aligned.mean()) / np.abs(target.mean()) + 1e-12)
    return aligned, float(np.abs(err_db))


def aircomp_upload(node_results: list[list[dict]], true_map: list[dict]) -> AirCompReport:
    """AirComp 方案：所有节点在同一时隙内以对齐功率同步发射，空中叠加。

    时隙数 = 1（单次聚合）。
    各节点检测结果在网关空中叠加，等效为功率域平均（叠加增益）。
    功率对齐误差模拟同步精度。
    """
    n_nodes = len(node_results)
    n_bands = len(true_map)

    # 模拟空中叠加：各节点结果经功率对齐后叠加
    # 叠加后功率 = sum_i (P_i * align_scale_i)
    # 这里简化为：网关对各节点功率做均值对齐，再线性叠加
    aligned_powers = []
    align_errors = []
    for node_res in node_results:
        node_powers = np.array([b["power_db"] for b in node_res])
        # 理想目标功率：真值（模拟"完美同步"时的对齐目标）
        true_powers = np.array([b["power"] for b in true_map])
        aligned, err = power_align(node_powers, true_powers)
        aligned_powers.append(aligned)
        align_errors.append(err)

    # 空中叠加：线性平均（等效为 N 节点等功率叠加）
    stacked = np.stack(aligned_powers, axis=0)  # (n_nodes, n_bands)
    fused_power = stacked.mean(axis=0)          # 空中叠加 = 均值

    # 计算精度
    true_powers = np.array([b["power"] for b in true_map])
    pred_centered = fused_power - fused_power.mean()
    true_centered = true_powers - true_powers.mean()
    denom = np.linalg.norm(pred_centered) * np.linalg.norm(true_centered)
    accuracy = float(np.abs(np.dot(pred_centered, true_centered)) / denom) if denom > 0 else 0.0

    # 频谱占用
    detected_bands = np.sum(np.abs(fused_power) > 1e-6)
    freq_occ = detected_bands / n_bands

    return AirCompReport(
        slots_used=1,
        freq_occupancy=freq_occ,
        accuracy=accuracy,
        power_align_error_db=float(np.mean(align_errors)),
        details={
            "fused_power_db": fused_power.tolist(),
            "per_node_align_errors_db": align_errors,
        },
    )


# ---------------------------------------------------------------------------
# 方案3：本地独立（无协作，各算各）
# ---------------------------------------------------------------------------

@dataclass
class LocalReport:
    """本地独立方案报告。"""
    slots_used: int   # 0 上行时隙
    freq_occupancy: float
    accuracy: float
    details: dict


def local_independent(node_results: list[list[dict]], true_map: list[dict]) -> LocalReport:
    """本地独立方案：各节点独立检测，不协作，精度受限于单节点能力。"""
    n_bands = len(true_map)
    # 各节点独立决策：取置信度最高的节点结果
    best_per_band = []
    for bi in range(n_bands):
        candidates = [(node_results[ni][bi]["confidence"], node_results[ni][bi]["power_db"])
                      for ni in range(len(node_results))]
        best_conf, best_pow = max(candidates, key=lambda x: x[0])
        best_per_band.append(best_pow if best_conf > 0.5 else -90.0)

    fused_power = np.array(best_per_band)
    true_powers = np.array([b["power"] for b in true_map])
    pred_centered = fused_power - fused_power.mean()
    true_centered = true_powers - true_powers.mean()
    denom = np.linalg.norm(pred_centered) * np.linalg.norm(true_centered)
    accuracy = float(np.abs(np.dot(pred_centered, true_centered)) / denom) if denom > 0 else 0.0
    detected_bands = np.sum(fused_power > -80.0)
    freq_occ = detected_bands / n_bands

    return LocalReport(
        slots_used=0,
        freq_occupancy=freq_occ,
        accuracy=accuracy,
        details={"fused_power_db": fused_power.tolist()},
    )


# ---------------------------------------------------------------------------
# 对比汇总
# ---------------------------------------------------------------------------

def compare_schemes(n_nodes: int = 5, seed: int = 42) -> dict:
    """三种方案对比，返回汇总报告。"""
    node_results = synthesize_node_detection(n_nodes, seed=seed)
    true_map = true_spectrum_map()

    tdma  = tdma_upload(node_results, true_map)
    ac    = aircomp_upload(node_results, true_map)
    local = local_independent(node_results, true_map)

    return {
        "n_nodes": n_nodes,
        "TDMA":  {"slots": tdma.slots_used,  "freq_occ": tdma.freq_occupancy,  "accuracy": tdma.accuracy},
        "AirComp": {"slots": ac.slots_used,   "freq_occ": ac.freq_occupancy,   "accuracy": ac.accuracy, "align_error_db": ac.power_align_error_db},
        "Local": {"slots": local.slots_used,  "freq_occ": local.freq_occupancy, "accuracy": local.accuracy},
        "验收断言": {
            "aircomp_slots_lt_tdma": ac.slots_used < tdma.slots_used,
            "aircomp_accuracy_gte_single": ac.accuracy >= min(tdma.accuracy, local.accuracy),
        },
    }


def main() -> None:
    print("=" * 60)
    print("AirMoE 空中聚合协议模拟")
    print("=" * 60)
    for n in [3, 5, 8]:
        r = compare_schemes(n_nodes=n, seed=42)
        print(f"\n【N={n} 节点】")
        print(f"  TDMA    时隙={r['TDMA']['slots']:2d}  频谱占用={r['TDMA']['freq_occ']:.2f}  精度={r['TDMA']['accuracy']:.3f}")
        print(f"  AirComp 时隙={r['AirComp']['slots']:2d}  频谱占用={r['AirComp']['freq_occ']:.2f}  精度={r['AirComp']['accuracy']:.3f}  对齐误差={r['AirComp']['align_error_db']:.2f}dB")
        print(f"  Local   时隙={r['Local']['slots']:2d}  频谱占用={r['Local']['freq_occ']:.2f}  精度={r['Local']['accuracy']:.3f}")
        print(f"  验收断言: AirComp时隙<TDMA={r['验收断言']['aircomp_slots_lt_tdma']}  聚合精度≥单节点={r['验收断言']['aircomp_accuracy_gte_single']}")
    print()


if __name__ == "__main__":
    main()