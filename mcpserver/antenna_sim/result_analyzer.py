"""仿真结果分析（卷122 W122-03）：S11/谐振/带宽/增益 → 可读报告 + 归档。

输入（按优先级）：

1. OpenEMS 跑出的 S11 CSV（`<结果目录>/s11.csv`，列 `freq_hz,s11_db,zin_re,zin_im`）
2. 指定的 `s11_csv` 路径
3. `synthetic=True` → 生成一条标准 RLC 形状的合成 S11（**报告里标注 synthetic**，用于无环境时跑通链路）

输出：`summary.json`（谐振频率 / S11 最小值 / -10dB 带宽 / 输入阻抗 / 方向特征 / 数据来源）
+ 可选 markdown 报告；并与「理论/文献参考值」对照给出**保守的**调参建议
（只对比已发布的天线类型典型值，不臆造物理结论）。
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: 已发布的天线类型典型增益参考（dBi）——只用于「仿真 vs 理论」对照，不参与计算
THEORY_GAIN_DBI: Dict[str, Tuple[float, float]] = {
    # 类型: (典型增益, 常见区间下限) —— Moxon/Quad 参考业余无线电手册常见值
    "moxon": (5.5, 4.0),
    "quad": (7.0, 6.0),
    "helical_yagi": (10.0, 8.0),
    "sierpinski": (3.0, 2.0),
}

#: 常见谐振点判定阈值
_RESONANCE_S11_DB = -10.0


def _read_csv_rows(path: Path) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("freq"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            row = {
                "freq_hz": float(parts[0]),
                "s11_db": float(parts[1]),
                "zin_re": float(parts[2]) if len(parts) > 2 and parts[2] else 0.0,
                "zin_im": float(parts[3]) if len(parts) > 3 and parts[3] else 0.0,
            }
        except ValueError:
            continue
        rows.append(row)
    rows.sort(key=lambda r: r["freq_hz"])
    return rows


def synthetic_s11(f0_hz: float, *, points: int = 41, bandwidth_ratio: float = 0.05,
                  min_db: float = -28.0, z0: float = 50.0) -> List[Dict[str, float]]:
    """合成一条 S11 曲线（单谐振、Lorentz 形状）——仅用于无环境时跑通分析与测试。

    报告里会带 `synthetic: true` 标记，不冒充实测/仿真结果。
    """
    rows: List[Dict[str, float]] = []
    half = max(bandwidth_ratio, 0.005)
    for i in range(points):
        f = f0_hz * (1.0 - half + 2.0 * half * i / max(1, points - 1))
        x = (f - f0_hz) / (f0_hz * half / 3.0)
        s11_db = min_db - (min_db * -1.0) * 0.0  # 起点：min_db 在中心
        depth = 1.0 / (1.0 + x * x)
        s11_db = min_db * depth + (1.0 - depth) * (-0.5)
        # 由 S11 反推 Zin（便于报告里给阻抗）
        mag = 10 ** (s11_db / 20.0)
        gamma = mag
        zin = z0 * (1 + gamma) / max(1e-9, (1 - gamma))
        rows.append({"freq_hz": f, "s11_db": s11_db, "zin_re": zin, "zin_im": 0.0})
    return rows


def analyze_rows(rows: List[Dict[str, float]], *, f0_hz: float = 0.0,
                 source: str = "") -> Dict[str, Any]:
    """从 S11 数据提取谐振/带宽/阻抗。数据不足时对应字段为 None（不编数）。"""
    if not rows:
        return {"ok": False, "error": "no_data"}
    freqs = [r["freq_hz"] for r in rows]
    s11 = [r["s11_db"] for r in rows]
    idx_min = min(range(len(s11)), key=lambda i: s11[i])
    resonance_hz = freqs[idx_min]
    s11_min_db = s11[idx_min]

    # -10dB 带宽：谐振点左右连续满足 S11 <= -10dB 的区间
    left = idx_min
    while left > 0 and s11[left - 1] <= _RESONANCE_S11_DB:
        left -= 1
    right = idx_min
    while right < len(s11) - 1 and s11[right + 1] <= _RESONANCE_S11_DB:
        right += 1
    bw_hz = freqs[right] - freqs[left] if (right > left and s11_min_db <= _RESONANCE_S11_DB) else 0.0
    bw_ratio = (bw_hz / resonance_hz) if resonance_hz else 0.0

    zin = (rows[idx_min].get("zin_re", 0.0), rows[idx_min].get("zin_im", 0.0))
    return {
        "ok": True,
        "source": source,
        "points": len(rows),
        "freq_range_hz": [freqs[0], freqs[-1]],
        "resonance_hz": resonance_hz,
        "resonance_mhz": round(resonance_hz / 1e6, 4),
        "s11_min_db": round(s11_min_db, 2),
        "bandwidth_hz": round(bw_hz, 1),
        "bandwidth_ratio": round(bw_ratio, 5),
        "bandwidth_note": "S11≤-10dB 连续区间" if bw_hz else "未达 -10dB（未匹配）",
        "zin_at_resonance": {"re": round(zin[0], 2), "im": round(zin[1], 2)},
        "freq_offset_from_target_hz": round(resonance_hz - f0_hz, 1) if f0_hz else None,
    }


def compare_theory(antenna_type: str, *, gain_dbi: float | None = None,
                   resonance_hz: float = 0.0, f0_hz: float = 0.0) -> Dict[str, Any]:
    """与文献典型值对照，给保守建议（不臆造结论，全部标注为推断）。"""
    typical, low = THEORY_GAIN_DBI.get(str(antenna_type), (None, None))
    out: Dict[str, Any] = {
        "antenna_type": antenna_type,
        "theory_gain_dbi": typical,
        "gain_delta_dbi": None,
        "notes": [],
    }
    if gain_dbi is not None and typical is not None:
        delta = round(float(gain_dbi) - float(typical), 2)
        out["gain_delta_dbi"] = delta
        if delta < -2.0:
            out["notes"].append(
                f"仿真增益比典型值低 {abs(delta):.1f} dB：优先检查网格分辨率与边界距离，"
                "其次考虑反射/寄生单元间距；不要先改尺寸"
            )
        elif delta > 2.0:
            out["notes"].append(
                f"仿真增益比典型值高 {delta:.1f} dB：可能是网格过粗或反射过大导致的乐观偏差，建议加密重跑复核"
            )
        else:
            out["notes"].append("增益落在典型值附近，可继续做参数微调")
    if resonance_hz and f0_hz:
        offset_ratio = (resonance_hz - f0_hz) / f0_hz
        out["resonance_offset_ratio"] = round(offset_ratio, 5)
        if abs(offset_ratio) > 0.01:
            direction = "偏长" if offset_ratio < 0 else "偏短"
            out["notes"].append(
                f"谐振点偏高目标 {offset_ratio * 100:+.2f}%：等效振子{direction}，"
                f"可尝试把辐射体长度按约 {-offset_ratio * 100 / 2:+.2f}% 微调后再扫（推断值，需复算验证）"
            )
        else:
            out["notes"].append("谐振点已落在目标 1% 内")
    out["notes"].append("以上均为仿真推断，待实测验证")
    return out


def _result_dir(job_id: str) -> Path:
    from .sim_runner import lab_root, safe_job_id

    key, err = safe_job_id(job_id)
    if key is None:
        raise ValueError(f"非法 job_id: {err}")
    return lab_root() / "results" / key


def analyze_result(job_id: str = "", s11_csv: str = "", synthetic: bool = False,
                   *, antenna_type: str = "", f0_mhz: float = 0.0,
                   gain_dbi: float | None = None, write_report: bool = True) -> Dict[str, Any]:
    """分析一次仿真结果并归档 `summary.json`（+ 可选 markdown 报告）。"""
    from .sim_runner import lab_root, safe_job_id

    source = ""
    rows: List[Dict[str, float]] = []
    target_dir: Path | None = None
    sid = ""
    if job_id:
        sid, err = safe_job_id(job_id)
        if sid is None:
            return {"ok": False, "error": err}
        target_dir = _result_dir(sid)
    if s11_csv:
        path = Path(s11_csv)
        if path.is_file():
            rows = _read_csv_rows(path)
            source = str(path)
        else:
            return {"ok": False, "error": "csv_not_found", "path": str(path)}
    elif target_dir is not None:
        candidate = target_dir / "s11.csv"
        if candidate.is_file():
            rows = _read_csv_rows(candidate)
            source = str(candidate)
    if not rows and synthetic:
        rows = synthetic_s11(f0_mhz * 1e6 if f0_mhz else 300e6)
        source = "synthetic"
    if not rows:
        return {"ok": False, "error": "no_s11_data",
                "hint": "给 --job_id（结果目录里要有 s11.csv）、--s11_csv，或 synthetic=True"}

    summary = analyze_rows(rows, f0_hz=f0_mhz * 1e6 if f0_mhz else 0.0, source=source)
    summary["synthetic"] = source == "synthetic"
    summary["job_id"] = sid
    if antenna_type:
        summary["theory"] = compare_theory(
            antenna_type, gain_dbi=gain_dbi,
            resonance_hz=float(summary.get("resonance_hz") or 0.0),
            f0_hz=f0_mhz * 1e6 if f0_mhz else 0.0,
        )
    if target_dir is None:
        target_dir = lab_root() / "results" / (sid or "adhoc")
        target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "summary.json").write_bytes(
        json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8"))
    summary["summary_path"] = str(target_dir / "summary.json")

    if write_report:
        (target_dir / "report.md").write_bytes(render_report(summary).encode("utf-8"))
        summary["report_path"] = str(target_dir / "report.md")
    logger.info("[antenna_sim] 结果分析完成：%s（谐振 %s MHz，S11min %s dB）",
                sid or "adhoc", summary.get("resonance_mhz"), summary.get("s11_min_db"))
    return {"ok": True, **summary}


def render_report(summary: Dict[str, Any]) -> str:
    """把分析结果渲染成 markdown 报告（含数据来源与合成标记）。"""
    lines = [f"# 天线仿真结果 · {summary.get('job_id') or 'adhoc'}", ""]
    if summary.get("synthetic"):
        lines.append("> ⚠️ **数据来源：合成（synthetic）**——仅用于跑通分析链路，不是仿真/实测结果。")
        lines.append("")
    lines += [
        f"- 数据来源：{summary.get('source')}（{summary.get('points')} 个频点）",
        f"- 频率范围：{summary['freq_range_hz'][0] / 1e6:.3f} ~ {summary['freq_range_hz'][1] / 1e6:.3f} MHz",
        f"- 谐振频率：**{summary.get('resonance_mhz')} MHz**",
        f"- S11 最小值：**{summary.get('s11_min_db')} dB**",
        f"- -10dB 带宽：{summary.get('bandwidth_hz')} Hz（相对 {summary.get('bandwidth_ratio')}）"
        f"——{summary.get('bandwidth_note')}",
        f"- 谐振点输入阻抗：{summary['zin_at_resonance']['re']} "
        f"{summary['zin_at_resonance']['im']:+}j Ω",
    ]
    offset = summary.get("freq_offset_from_target_hz")
    if offset is not None:
        lines.append(f"- 与目标频率偏差：{offset / 1e3:+.1f} kHz")
    theory = summary.get("theory")
    if theory:
        lines += ["", "## 与文献典型值对照（推断）", "",
                  f"- 类型：{theory.get('antenna_type')}｜典型增益 {theory.get('theory_gain_dbi')} dBi",
                  f"- 增益差：{theory.get('gain_delta_dbi')} dB"]
        lines += [f"- {n}" for n in theory.get("notes", [])]
    lines += ["", "## 参数与假设", "",
              "- 网格/边界/激励参数见模型文件头注释（`models/*.xml|py`）",
              "- **仿真结果待实测验证**（对照卷118 W118-03 无相位测量方案）", ""]
    return "\n".join(lines)


def archive_entry(summary: Dict[str, Any]) -> Dict[str, Any]:
    """档案索引条目（供 docs/antenna-lab/results/README.md 汇总）。"""
    return {
        "job_id": summary.get("job_id") or "adhoc",
        "resonance_mhz": summary.get("resonance_mhz"),
        "s11_min_db": summary.get("s11_min_db"),
        "bandwidth_hz": summary.get("bandwidth_hz"),
        "zin": summary.get("zin_at_resonance"),
        "synthetic": bool(summary.get("synthetic")),
        "source": summary.get("source"),
        "status": "仿真结果待实测验证",
    }


__all__ = ["analyze_result", "analyze_rows", "synthetic_s11", "compare_theory",
           "render_report", "archive_entry", "THEORY_GAIN_DBI", "_read_csv_rows"]
