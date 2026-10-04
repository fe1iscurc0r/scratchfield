"""
V-02: 实验数据工具台 — /api/data-tools 路由。

职责：
  - 解析三类科研数据格式（TGA / DSC / XRD，CSV / TXT，分隔符自动探测）
  - 预处理：TGA 基线扣除、DSC 归一化、XRD 平滑（可选）
  - matplotlib 生成科研风 PNG（简洁、白底、坐标轴标签 + 图例）
  - 图存 `experiments/attachments/`，并可生成 ELN 记录 / 追加附件（与 V-01 打通）

硬约束：
  - 仅依赖 numpy / pandas / matplotlib，不引重量级库
  - 样例数据自造并标注「样例」
  - 图表科研风简洁（无冗余网格、清晰坐标轴）

端点：
  - GET  /api/data-tools/samples   返回三类样例数据（标注「样例」）
  - POST /api/data-tools/parse     上传文件 → 探测分隔符 → 返回表头 + 预览
  - POST /api/data-tools/plot      上传文件 + 参数 → 预处理 → 绘图 → 入库 ELN 附件
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Annotated

import matplotlib

matplotlib.use("Agg")  # 无 GUI 后端，服务器/测试环境可用

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..naga_auth import require_local_auth
from . import eln as eln_module

router = APIRouter(prefix="/api/data-tools", tags=["data-tools"])
logger = logging.getLogger(__name__)

# 中文标题字体回退（Windows 用微软雅黑，避免中文乱码；无则回退默认字体）
_CJK_CANDIDATES = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "WenQuanYi Zen Hei"]
_available_fonts = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
for _font in _CJK_CANDIDATES:
    if _font in _available_fonts:
        plt.rcParams["font.sans-serif"] = [_font, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        break

# 支持的数据类型
DATA_TYPES = ("tga", "dsc", "xrd", "raman")

# 分隔符探测候选（按优先级）
_DELIMITERS = [",", "\t", ";", r"\s+"]


# ============ 样例数据（自造，标注「样例」） ============


def _sample_tga() -> str:
    """样例 TGA：温度 / 质量%，标注样例。"""
    temp = np.linspace(30, 800, 100)
    mass = 100 - (temp / 800) ** 2 * 15 + np.sin(temp / 50) * 0.3
    df = pd.DataFrame({"Temperature_C": temp, "Weight_pct": mass})
    return "# 样例 TGA 数据（自造，非实测）\n" + df.to_csv(index=False)


def _sample_dsc() -> str:
    """样例 DSC：温度 / 热流 mW，标注样例。"""
    temp = np.linspace(0, 300, 120)
    # 一个放热峰 + 一个玻璃化转变斜坡
    heatflow = (
        -0.5
        + 3.0 * np.exp(-((temp - 150) ** 2) / (2 * 20**2))
        + 0.02 * temp
        + np.random.default_rng(42).normal(0, 0.05, len(temp))
    )
    df = pd.DataFrame({"Temperature_C": temp, "HeatFlow_mW": heatflow})
    return "# 样例 DSC 数据（自造，非实测）\n" + df.to_csv(index=False)


def _sample_xrd() -> str:
    """样例 XRD：2θ / 强度，标注样例。"""
    two_theta = np.linspace(10, 80, 700)
    peaks = [
        (20.0, 100, 0.6),
        (28.5, 320, 0.5),
        (40.3, 180, 0.7),
        (50.2, 120, 0.8),
    ]
    intensity = np.zeros_like(two_theta)
    rng = np.random.default_rng(7)
    for center, amp, width in peaks:
        intensity += amp * np.exp(-((two_theta - center) ** 2) / (2 * width**2))
    intensity += rng.normal(0, 2.0, len(two_theta))  # 噪声基底
    df = pd.DataFrame({"TwoTheta_deg": two_theta, "Intensity": intensity})
    return "# 样例 XRD 数据（自造，非实测）\n" + df.to_csv(index=False)


def _sample_raman() -> str:
    """样例拉曼：Raman shift / 强度（合成洛伦兹峰+尖峰+噪声），标注样例。

    懒加载 tools.raman_utils（避免 scipy 常驻 data_tools 启动路径）。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.raman_utils import synth_raman

    df = synth_raman(seed=3)
    return "# 样例 Raman 数据（自造，非实测）\n" + df.to_csv(index=False)


_SAMPLES = {"tga": _sample_tga, "dsc": _sample_dsc, "xrd": _sample_xrd, "raman": _sample_raman}


# ============ 解析 ============


def detect_delimiter(text: str) -> str:
    """在候选分隔符中选列数最多者。"""
    best, best_cols = ",", -1
    for d in _DELIMITERS:
        try:
            df = pd.read_csv(io.StringIO(text), sep=d, comment="#", engine="python")
            if df.shape[1] > best_cols:
                best, best_cols = d, df.shape[1]
        except Exception:
            continue
    return best


def parse_dataframe(text: str) -> tuple[pd.DataFrame, str]:
    """解析文本为 DataFrame，返回 (df, 分隔符)。"""
    text = text.lstrip("\ufeff")  # 去掉 BOM
    delim = detect_delimiter(text)
    try:
        df = pd.read_csv(io.StringIO(text), sep=delim, comment="#", engine="python")
    except Exception as e:  # pragma: no cover - 防御路径
        raise HTTPException(status_code=400, detail=f"无法解析数据：{e}") from e
    if df.shape[1] < 2:
        raise HTTPException(status_code=400, detail="至少需要两列数据（x 与 y）")
    return df, delim


# ============ 预处理 ============


def preprocess_tga(df: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    """TGA 基线扣除：质量扣除起始基线，使曲线从 100% 起算。"""
    out = df.copy()
    baseline = out[y_col].iloc[0]
    out[y_col] = out[y_col] - baseline + 100.0
    return out


def preprocess_dsc(df: pd.DataFrame, x_col: str, y_col: str, mass_mg: float | None = None) -> pd.DataFrame:
    """DSC 归一化：热流除以样品质量（缺省时 min-max 归一化到 [0,1]）。"""
    out = df.copy()
    if mass_mg and mass_mg > 0:
        out[y_col] = out[y_col] / mass_mg
    else:
        lo, hi = out[y_col].min(), out[y_col].max()
        if hi - lo > 1e-12:
            out[y_col] = (out[y_col] - lo) / (hi - lo)
    return out


def preprocess_xrd(df: pd.DataFrame, x_col: str, y_col: str, smooth_window: int = 0) -> pd.DataFrame:
    """XRD 平滑（可选）：移动平均，窗口为奇数。smooth_window<=1 表示不平滑。"""
    out = df.copy()
    if smooth_window and smooth_window > 1:
        if smooth_window % 2 == 0:
            smooth_window += 1
        kernel = np.ones(smooth_window) / smooth_window
        out[y_col] = np.convolve(out[y_col], kernel, mode="same")
    return out


def preprocess_raman(df: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    """拉曼预处理链（懒加载 tools.raman_utils）：去尖峰→SavGol→ASLS 基线→MinMax。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.raman_utils import preprocess_raman as _pre

    sub = df[[x_col, y_col]].rename(
        columns={x_col: "RamanShift_cm1", y_col: "Intensity"},
    )
    out = _pre(sub)
    out = out.rename(columns={"RamanShift_cm1": x_col, "Intensity": y_col})
    return out


def preprocess(
    data_type: str,
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    mass_mg: float | None = None,
    smooth_window: int = 0,
) -> pd.DataFrame:
    """按数据类型分派预处理。"""
    if data_type == "tga":
        return preprocess_tga(df, x_col, y_col)
    if data_type == "dsc":
        return preprocess_dsc(df, x_col, y_col, mass_mg=mass_mg)
    if data_type == "xrd":
        return preprocess_xrd(df, x_col, y_col, smooth_window=smooth_window)
    if data_type == "raman":
        return preprocess_raman(df, x_col, y_col)
    raise HTTPException(status_code=400, detail=f"未知数据类型：{data_type}")


# ============ 绘图 ============


def plot_curve(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    data_type: str,
    title: str,
) -> io.BytesIO:
    """绘制科研风曲线，返回 PNG 字节流。简洁：白底、清晰坐标轴、图例。"""
    _AXIS_LABELS = {
        "tga": ("Temperature (°C)", "Weight (%)"),
        "dsc": ("Temperature (°C)", "Heat flow (mW)"),
        "xrd": ("2θ (deg)", "Intensity (a.u.)"),
        "raman": ("Raman shift (cm⁻¹)", "Intensity (a.u.)"),
    }
    xlabel, ylabel = _AXIS_LABELS.get(data_type, (x_col, y_col))

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=120)
    ax.plot(df[x_col], df[y_col], color="#1f77b4", linewidth=1.4, label=y_col)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5)
    ax.legend(frameon=False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# ============ 端点 ============


@router.get("/samples")
async def list_samples(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """返回三类样例数据（自造，标注「样例」）。"""
    return {
        "ok": True,
        "samples": {
            "tga": {"label": "TGA 样例（自造）", "content": _sample_tga()},
            "dsc": {"label": "DSC 样例（自造）", "content": _sample_dsc()},
            "xrd": {"label": "XRD 样例（自造）", "content": _sample_xrd()},
            "raman": {"label": "Raman 样例（自造）", "content": _sample_raman()},
        },
    }


@router.post("/parse")
async def parse_file(
    file: UploadFile = File(...),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """上传文件 → 探测分隔符 → 返回表头 + 前 10 行预览。"""
    raw = (await file.read()).decode("utf-8", errors="replace")
    df, delim = parse_dataframe(raw)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    preview = df.head(10).where(pd.notna(df.head(10)), None)
    return {
        "ok": True,
        "filename": file.filename,
        "delimiter": delim,
        "columns": list(df.columns),
        "numeric_columns": numeric_cols,
        "row_count": int(len(df)),
        "preview": preview.to_dict(orient="records"),
    }


@router.post("/plot")
async def plot_file(
    file: UploadFile = File(...),
    data_type: str = Form(...),
    x_col: str = Form(...),
    y_col: str = Form(...),
    title: str = Form(""),
    mass_mg: float | None = Form(None),
    smooth_window: int = Form(0),
    topic: str = Form(""),
    record_id: str = Form(""),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """上传文件 + 参数 → 预处理 → 绘图 → 存 attachments/ → 生成/追加 ELN 记录。"""
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=400, detail=f"未知数据类型：{data_type}")

    raw = (await file.read()).decode("utf-8", errors="replace")
    df, _delim = parse_dataframe(raw)
    if x_col not in df.columns or y_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"列不存在：{x_col}/{y_col}")
    for col in (x_col, y_col):
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise HTTPException(status_code=400, detail=f"列 {col} 不是数值列")

    processed = preprocess(data_type=data_type, df=df, x_col=x_col, y_col=y_col, mass_mg=mass_mg, smooth_window=smooth_window)

    plot_title = title or f"{data_type.upper()} · {y_col} vs {x_col}"
    png = plot_curve(processed, x_col, y_col, data_type, plot_title)

    # 图存 attachments/，文件名唯一
    stored_name = f"{data_type}_{uuid.uuid4().hex[:12]}.png"
    dest = eln_module._attachments_dir() / stored_name
    dest.write_bytes(png.read())
    rel = f"attachments/{stored_name}"

    # 生成 ELN 记录 或 追加附件
    created_record_id: str | None = None
    if topic:
        rid = uuid.uuid4().hex[:12]
        record = {
            "date": "",
            "topic": topic,
            "status": "进行中",
            "purpose": f"{data_type.upper()} 数据图自动入库",
            "reagents": "",
            "conditions": f"x={x_col}, y={y_col}",
            "results": "",
            "attachments": [rel],
            "conclusion": "",
            "references": "",
        }
        eln_module._write_record(rid, record)
        created_record_id = rid
    elif record_id:
        existing = eln_module._read_record(record_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="ELN 记录不存在")
        attachments = list(existing.get("attachments") or [])
        if rel not in attachments:
            attachments.append(rel)
        existing["attachments"] = attachments
        eln_module._write_record(record_id, existing)
        created_record_id = record_id

    logger.info(f"[data-tools] plot type={data_type} -> {rel} record={created_record_id or '-'}")
    return {
        "ok": True,
        "attachment": rel,
        "record_id": created_record_id,
        "data_type": data_type,
    }
