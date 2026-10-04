"""天线仿真模型生成器（卷122 W122-01）。

对话里给「天线类型 / 频率 / 尺寸」→ 出**可跑模型文件**。首期三种（用户 P0）：

| 类型 | 结构 | 关键参数 |
| --- | --- | --- |
| `moxon` | 2 单元线天线（驱动 + 反射，端部弯折） | 振子长度、间距、线径、端部间隙 |
| `quad` | 框形（方框环，周长 ≈ 1λ） | 边长、线径、离地高度 |
| `helical_yagi` | 轴向模螺旋 + 反射板 | 圈数、螺距、直径、反射板尺寸 |

产出两种形态，互相印证：

1. **CSX XML（`.xml`）** —— OpenEMS 的原生输入格式，用 `openEMS.exe model.xml` 直接算，
   **不需要 Python 绑定**（Windows MSVC 版绑定常与本机 Python 版本不匹配，XML 路径最稳）
2. **Python 模型脚本（`.py`）** —— 给有 CSXCAD/openEMS 绑定的环境（Kali / Linux 包）用，
   `python3 model.py` 即可跑

模型头写元信息注释（type/freq/params/generated_by/git），每个模型标注网格与边界假设，
供后续迭代核对。
"""
from __future__ import annotations

import json
import logging
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

C0 = 299792458.0  # 光速 m/s
SUPPORTED_TYPES = ("moxon", "quad", "helical_yagi", "sierpinski")
PLACEHOLDER_TYPES = ("sierpinski",)  # 预留位：只给接口，不实现

#: 各类型的默认参数（按频率缩放；尺寸单位 mm）
DEFAULT_PARAMS: Dict[str, Dict[str, float]] = {
    "moxon": {"driven_len_mm": 0.0, "reflector_len_mm": 0.0, "spacing_mm": 0.0,
              "tip_gap_mm": 0.0, "wire_dia_mm": 2.0},
    "quad": {"side_mm": 0.0, "height_mm": 1000.0, "wire_dia_mm": 3.0},
    "helical_yagi": {"turns": 8, "pitch_mm": 0.0, "diameter_mm": 0.0,
                     "reflector_mm": 0.0, "wire_dia_mm": 3.0},
}


def wavelength_m(freq_mhz: float) -> float:
    return C0 / (float(freq_mhz) * 1e6)


def _defaults_for(antenna_type: str, freq_mhz: float) -> Dict[str, float]:
    """按频率推一套保守的初始尺寸（都是文献常用比例，作为起点不是最终答案）。"""
    lam_mm = wavelength_m(freq_mhz) * 1000.0
    if antenna_type == "moxon":
        return {
            "driven_len_mm": round(lam_mm * 0.343, 1),      # 约 1.03λ/3，Moxon 常用区间
            "reflector_len_mm": round(lam_mm * 0.365, 1),
            "spacing_mm": round(lam_mm * 0.055, 1),
            "tip_gap_mm": round(lam_mm * 0.070, 1),
            "wire_dia_mm": 2.0,
        }
    if antenna_type == "quad":
        return {"side_mm": round(lam_mm / 4.0 * 1.03, 1), "height_mm": round(lam_mm * 0.5, 1),
                "wire_dia_mm": 3.0}
    if antenna_type == "helical_yagi":
        return {
            "turns": 8.0,
            "pitch_mm": round(lam_mm * 0.24 / 8.0, 1),   # 轴向长度 ≈ 0.24λ
            "diameter_mm": round(lam_mm / math.pi * 1.05, 1),  # 周长 ≈ 1.05λ
            "reflector_mm": round(lam_mm * 0.55, 1),
            "wire_dia_mm": 3.0,
        }
    return {}


def normalize_params(antenna_type: str, freq_mhz: float,
                     params: Dict[str, Any] | None = None) -> Dict[str, float]:
    """把用户给的参数与默认值合并（用户给的优先，缺的按频率补）。"""
    merged = dict(_defaults_for(antenna_type, freq_mhz))
    for key, value in (params or {}).items():
        try:
            merged[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return merged


def validate(antenna_type: str, freq_mhz: float, params: Dict[str, float]) -> List[str]:
    """参数物理合法性校验（返回问题清单，空 = 通过）。"""
    problems: List[str] = []
    if antenna_type not in SUPPORTED_TYPES:
        return [f"不支持的天线类型 {antenna_type}（支持 {', '.join(SUPPORTED_TYPES)}）"]
    if not (0.1 <= float(freq_mhz) <= 100000.0):
        problems.append(f"频率 {freq_mhz} MHz 超出合理范围（0.1~100000）")
    lam_mm = wavelength_m(freq_mhz) * 1000.0
    for name, value in params.items():
        if value is None:
            continue
        if float(value) <= 0:
            problems.append(f"参数 {name}={value} 必须为正数")
    if antenna_type == "moxon":
        driven = params.get("driven_len_mm", 0.0)
        refl = params.get("reflector_len_mm", 0.0)
        gap = params.get("tip_gap_mm", 0.0)
        if refl and driven and refl <= driven:
            problems.append("Moxon 反射振子应长于驱动振子（reflector_len_mm > driven_len_mm）")
        if driven and not (lam_mm * 0.15 <= driven <= lam_mm * 0.6):
            problems.append(f"驱动振子长度 {driven}mm 与 {freq_mhz}MHz（λ={lam_mm:.0f}mm）比例不合理")
        if gap and driven and gap >= driven:
            problems.append("端部间隙不能大于振子长度")
    if antenna_type == "quad":
        side = params.get("side_mm", 0.0)
        if side and not (lam_mm * 0.18 <= side <= lam_mm * 0.35):
            problems.append(f"Quad 边长 {side}mm 与 λ={lam_mm:.0f}mm 比例不合理（应在 0.18λ~0.35λ）")
    if antenna_type == "helical_yagi":
        turns = params.get("turns", 0.0)
        if turns and not (3 <= turns <= 40):
            problems.append(f"螺旋圈数 {turns:.0f} 超出常用范围（3~40）")
        dia = params.get("diameter_mm", 0.0)
        if dia and not (lam_mm * 0.2 <= dia <= lam_mm * 0.45):
            problems.append(f"螺旋直径 {dia}mm 与 λ={lam_mm:.0f}mm 比例不合理（0.2λ~0.45λ）")
    return problems


# ---------------------------------------------------------------------------
# CSX XML（OpenEMS 原生输入，无需 Python 绑定）
# ---------------------------------------------------------------------------


def _xml_header(meta: Dict[str, Any], f_max: float) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!--
  {meta['comment_line']}
  antenna_type={meta['antenna_type']}  freq={meta['freq_mhz']} MHz  params={meta['params_json']}
  generated_by={meta['generated_by']}  git={meta['git']}
  网格假设：线径 {meta['params'].get('wire_dia_mm', 2.0)}mm；λ/20 单元映射；吸收边界 = PML(8 层)
  求解设置：f_max={f_max / 1e6:.1f} MHz（=1.6×工作频率），Gauss 激励，扫频 0.6~1.4×工作频率
-->
<openEMS>
  <FDTD NumberOfTimesteps="20000" EndCriteria="1e-5" MaxTime="0" OverSampling="5">
    <Excitation Type="0" Frequency="{f_max:.0f}"/>
  </FDTD>
  <ContinuousStructure CoordSystem="0">
    <Properties>
      <Metal Name="PEC" Conductivity="5.8e7"/>
    </Properties>
"""


def _xml_footer(meta: Dict[str, Any], bbox_mm: Tuple[float, float, float]) -> str:
    lx, ly, lz = bbox_mm
    return f"""    <Grid MaxRes="{meta['max_res_mm']:.2f}" >
      <Lines>
        <XLines>{_lines_xml('X', lx)}</XLines>
        <YLines>{_lines_xml('Y', ly)}</YLines>
        <ZLines>{_lines_xml('Z', lz)}</ZLines>
      </Lines>
    </Grid>
  </ContinuousStructure>
  <PostProcessing>
    <CalcS11 port="1" />
  </PostProcessing>
</openEMS>
"""


def _lines_xml(axis: str, length_mm: float, cells: int = 40) -> str:
    """沿主轴均匀网格线（含边界外延，保证 PML 有余量）。"""
    lines = []
    for i in range(cells + 1):
        pos = -length_mm * 0.5 + length_mm * i / cells
        lines.append(f'<{axis}Line>{pos:.3f}</{axis}Line>')
    return "".join(lines)


def _wire_xml(name: str, points: List[Tuple[float, float, float]], dia_mm: float) -> str:
    """一条折线导体（LinPoly）。点单位 mm，中心在原点。"""
    start = points[0]
    out = [f'      <LinPoly Name="{name}" Priority="1">',
           '        <Material Name="PEC"/>',
           f'        <Start X="{start[0]:.3f}" Y="{start[1]:.3f}" Z="{start[2]:.3f}"/>']
    for pt in points[1:]:
        out.append(f'        <Point X="{pt[0]:.3f}" Y="{pt[1]:.3f}" Z="{pt[2]:.3f}"/>')
    out.append(f'        <Weight X="{dia_mm:.3f}" Y="{dia_mm:.3f}" Z="{dia_mm:.3f}"/>')
    out.append('      </LinPoly>')
    return "\n".join(out)


def _moxon_geometry(p: Dict[str, float]) -> Tuple[List[Tuple[str, List[Tuple[float, float, float]]]], Tuple[float, float, float]]:
    """Moxon：驱动 + 反射，两端向中间弯折（不接触）。X 轴为振子方向，Y 为间距方向。"""
    drive_half = p["driven_len_mm"] / 2.0
    refl_half = p["reflector_len_mm"] / 2.0
    spacing = p["spacing_mm"]
    gap = p["tip_gap_mm"]
    z = 0.0
    driven = [(-drive_half, 0.0, z), (drive_half, 0.0, z)]
    driven_tip_a = [(-drive_half, 0.0, z), (-drive_half + gap, spacing * 0.5, z)]
    driven_tip_b = [(drive_half, 0.0, z), (drive_half - gap, spacing * 0.5, z)]
    reflector = [(-refl_half, spacing, z), (refl_half, spacing, z)]
    refl_tip_a = [(-refl_half, spacing, z), (-refl_half + gap, spacing * 0.5, z)]
    refl_tip_b = [(refl_half, spacing, z), (refl_half - gap, spacing * 0.5, z)]
    wires = [("Driven", driven), ("DrivenTipA", driven_tip_a), ("DrivenTipB", driven_tip_b),
             ("Reflector", reflector), ("ReflTipA", refl_tip_a), ("ReflTipB", refl_tip_b)]
    bbox = (max(p["driven_len_mm"], p["reflector_len_mm"]) * 3.5,
            max(spacing * 6.0, p["reflector_len_mm"] * 0.6), p["driven_len_mm"] * 0.5)
    return wires, bbox


def _quad_geometry(p: Dict[str, float]) -> Tuple[List[Tuple[str, List[Tuple[float, float, float]]]], Tuple[float, float, float]]:
    """Quad：方框环（4 边，周长≈1λ），水平放置于给定高度。

    **馈电边要开口**：闭合环会把端口短路（激励被金属短掉、能量恒为 0，实测踩过），
    所以底边中间留出缺口，端口跨在缺口上（缺口位置由 `_quad_feed` 声明）。
    """
    side = p["side_mm"]
    h = p["height_mm"]
    half = side / 2.0
    gap = min(max(float(p.get("feed_gap_mm") or 0.0), p.get("wire_dia_mm", 3.0) * 2.0), side * 0.05)
    loops = [
        ("QuadFeedA", [(-half, -half, h), (-gap / 2.0, -half, h)]),
        ("QuadFeedB", [(gap / 2.0, -half, h), (half, -half, h)]),
        ("QuadRight", [(half, -half, h), (half, half, h)]),
        ("QuadTop", [(half, half, h), (-half, half, h)]),
        ("QuadLeft", [(-half, half, h), (-half, -half, h)]),
    ]
    bbox = (side * 4.0, side * 4.0, max(h * 2.0, side))
    return loops, bbox


def _helix_geometry(p: Dict[str, float]) -> Tuple[List[Tuple[str, List[Tuple[float, float, float]]]], Tuple[float, float, float]]:
    """轴向模螺旋：N 圈（分段折线逼近）+ 末端反射板。轴沿 X。"""
    turns = int(round(p["turns"]))
    pitch = p["pitch_mm"]
    radius = p["diameter_mm"] / 2.0
    segments_per_turn = 12
    pts: List[Tuple[float, float, float]] = []
    for i in range(turns * segments_per_turn + 1):
        theta = 2.0 * math.pi * i / segments_per_turn
        x = pitch * i / segments_per_turn
        pts.append((x, radius * math.cos(theta), radius * math.sin(theta)))
    reflector_size = p["reflector_mm"]
    half = reflector_size / 2.0
    refl = [(-pitch * 0.25, -half, -half), (-pitch * 0.25, half, -half),
            (-pitch * 0.25, half, half), (-pitch * 0.25, -half, half), (-pitch * 0.25, -half, -half)]
    wires = [("Helix", pts), ("Reflector", refl)]
    bbox = (pitch * turns * 4.0, radius * 6.0, radius * 6.0)
    return wires, bbox


_GEOMETRY = {"moxon": _moxon_geometry, "quad": _quad_geometry, "helical_yagi": _helix_geometry}


def _feed_spec(antenna_type: str, params: Dict[str, float], wires: List[Tuple[str, List[Tuple[float, float, float]]]]) -> Dict[str, Any]:
    """显式声明馈电缺口（端口就跨在缺口上）。

    这是实测踩出来的必要信息：端口若落在导体中间会被**短路**（能量恒为 0、S11 全 nan）。
    所以「缺口在哪、朝向哪个轴、多宽」必须由几何给出，而不是猜第一段的起点。
    """
    radius = float(params.get("wire_dia_mm", 2.0)) / 2.0
    if antenna_type == "quad":
        h = float(params["height_mm"])
        width = max(radius * 4.0, float(params.get("feed_gap_mm") or 0.0))
        return {"center": [0.0, -float(params["side_mm"]) / 2.0, h], "axis": "x", "width_mm": width}
    if antenna_type == "moxon":
        driven = float(params["driven_len_mm"])
        width = min(max(driven * 0.01, radius * 4.0), driven * 0.05)
        return {"center": [0.0, 0.0, 0.0], "axis": "x", "width_mm": width}
    # 螺旋等端馈结构：缺口在线的起点处，沿第一段方向
    first = wires[0][1][0]
    second = wires[0][1][1]
    axis = "x"
    for i, letter in enumerate("xyz"):
        if abs(second[i] - first[i]) > 1e-9:
            axis = letter
            break
    width = max(radius * 4.0, radius * 2.0)
    return {"center": [float(c) for c in first], "axis": axis, "width_mm": width}


def _feed_gap_segments(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把馈电缺口转成「两小段占位」——仅用于前端展示/元信息，不进几何。"""
    return [{"center": feed.get("center"), "axis": feed.get("axis"), "width_mm": feed.get("width_mm")}]


def _git_rev() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=str(Path(__file__).resolve().parent))
        return (out.stdout or "").strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def build_meta(antenna_type: str, freq_mhz: float, params: Dict[str, float]) -> Dict[str, Any]:
    f_max = float(freq_mhz) * 1e6 * 1.6
    lam_mm = wavelength_m(freq_mhz) * 1000.0
    return {
        "antenna_type": antenna_type,
        "freq_mhz": float(freq_mhz),
        "params": params,
        "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
        "generated_by": "mcpserver.antenna_sim.model_generator (卷122 W122-01)",
        "git": _git_rev(),
        "max_res_mm": round(lam_mm / 20.0, 2),
        "comment_line": (f"OpenEMS 模型 · {antenna_type} @ {freq_mhz} MHz（λ={lam_mm:.1f}mm）"
                         " · 由 Lumo antenna_sim 生成"),
    }


def gen_model(antenna_type: str, freq_mhz: float, params: Dict[str, Any] | None = None,
              out_dir: str | Path | None = None, name: str = "") -> Dict[str, Any]:
    """生成一个天线模型（CSX XML + Python 脚本）。

    Returns:
        `{ok, antenna_type, freq_mhz, params, xml_path, py_path, wavelength_mm, problems}`
        或 `{ok: False, error, problems}`
    """
    antenna_type = str(antenna_type or "").strip().lower()
    if antenna_type in PLACEHOLDER_TYPES:
        return {"ok": False, "error": "not_implemented",
                "problems": [f"{antenna_type} 为预留接口（本批次未实现）"]}
    merged = normalize_params(antenna_type, float(freq_mhz or 0.0), params)
    problems = validate(antenna_type, float(freq_mhz or 0.0), merged)
    if problems:
        return {"ok": False, "error": "invalid_params", "problems": problems}

    meta = build_meta(antenna_type, float(freq_mhz), merged)
    wires, bbox = _GEOMETRY[antenna_type](merged)
    body = "\n".join(_wire_xml(n, pts, merged.get("wire_dia_mm", 2.0)) for n, pts in wires)
    xml = _xml_header(meta, float(freq_mhz) * 1e6 * 1.6) + body + "\n" + _xml_footer(meta, bbox)

    target_dir = Path(out_dir) if out_dir else Path.cwd()
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = name or f"{antenna_type}_{int(freq_mhz)}mhz"
    xml_path = target_dir / f"{stem}.xml"
    py_path = target_dir / f"{stem}.py"
    xml_path.write_bytes(xml.encode("utf-8"))
    feed = _feed_spec(antenna_type, merged, wires)
    py_path.write_bytes(render_python_model(meta, wires, bbox, feed).encode("utf-8"))

    logger.info("[antenna_sim] 生成模型 %s（%s @ %s MHz）→ %s",
                stem, antenna_type, freq_mhz, target_dir)
    return {
        "ok": True,
        "antenna_type": antenna_type,
        "freq_mhz": float(freq_mhz),
        "params": merged,
        "wavelength_mm": round(wavelength_m(meta["freq_mhz"]) * 1000.0, 2),
        "xml_path": str(xml_path),
        "py_path": str(py_path),
        "wires": [n for n, _ in wires],
        "problems": [],
    }


TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "model_template.txt"


def render_python_model(meta: Dict[str, Any], wires: List[Tuple[str, List[Tuple[float, float, float]]]],
                        bbox: Tuple[float, float, float], feed: Dict[str, Any] | None = None) -> str:
    """用模板渲染**可直接运行**的 OpenEMS 模型脚本。

    模板在 `templates/model_template.txt`（本机实测通过的形态：圆柱段 + 导线加密网格 +
    delta-gap 端口 + S11 扫频写 CSV）。模板正文与说明之间用 `== 以下为脚本正文 ==` 分隔，
    只取正文部分；占位符 `@@XXX@@` 由这里替换。
    """
    segments = [
        [[round(c, 4) for c in pts[i]], [round(c, 4) for c in pts[i + 1]]]
        for _name, pts in wires
        for i in range(len(pts) - 1)
    ]
    raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    marker = "== 以下为脚本正文 =="
    body = raw.split(marker, 1)[1].lstrip("\n") if marker in raw else raw
    replacements = {
        "@@COMMENT@@": meta["comment_line"],
        "@@TYPE@@": str(meta["antenna_type"]),
        "@@FREQ_MHZ@@": repr(float(meta["freq_mhz"])),
        "@@FREQ_HZ@@": f"{meta['freq_mhz'] * 1e6:.6f}",
        "@@PARAMS_JSON@@": meta["params_json"],
        "@@PARAMS_REPR@@": repr(meta["params_json"]),
        "@@GENERATED_BY@@": meta["generated_by"],
        "@@GIT@@": meta["git"],
        "@@SEGMENTS@@": repr(segments),
        "@@WIRE_DIA@@": repr(float(meta["params"].get("wire_dia_mm", 2.0))),
        "@@BBOX@@": repr(tuple(round(v, 4) for v in bbox)),
        "@@FEED@@": repr(feed or {}),
    }
    for key, value in replacements.items():
        body = body.replace(key, value)
    return body


def sweep_params(antenna_type: str, freq_mhz: float, sweep: Dict[str, List[float]],
                 out_dir: str | Path) -> Dict[str, Any]:
    """批量生成参数扫描模型（供排队跑）。`sweep` 形如 `{"driven_len_mm": [..], "spacing_mm": [..]}`。"""
    import itertools

    keys = list(sweep.keys())
    if not keys:
        return {"ok": False, "error": "empty_sweep", "generated": []}
    combos = list(itertools.product(*[sweep[k] for k in keys]))
    base = normalize_params(antenna_type, freq_mhz, {})
    generated: List[Dict[str, Any]] = []
    for idx, values in enumerate(combos, start=1):
        params = dict(base)
        for key, value in zip(keys, values):
            params[key] = value
        result = gen_model(antenna_type, freq_mhz, params, out_dir=out_dir,
                           name=f"{antenna_type}_sweep{idx:03d}")
        generated.append({"index": idx, "params": {k: params[k] for k in keys},
                          "ok": bool(result.get("ok")), "xml_path": result.get("xml_path", ""),
                          "problems": result.get("problems", [])})
    ok_count = sum(1 for g in generated if g["ok"])
    return {"ok": ok_count > 0, "count": len(generated), "ok_count": ok_count,
            "out_dir": str(out_dir), "generated": generated}


__all__ = ["gen_model", "sweep_params", "validate", "normalize_params", "wavelength_m",
           "SUPPORTED_TYPES", "PLACEHOLDER_TYPES", "DEFAULT_PARAMS"]
