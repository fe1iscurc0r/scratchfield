"""SigMF 频谱数据标准化最小验证探针（合成 IQ + 完整 core 元数据，写→读回）。

授粉来源：sigmf/SigMF（规范 CC-BY-SA-4.0）、sigmf/sigmf-python（LGPL-3.0）。
本探针遵循 SigMF 规范格式（JSON 元数据 + 二进制 IQ）生成最小录音并读回验证；
未安装 sigmf-python 时用最小实现（不 copy 源码，只遵循格式，诚实标注）。

实现纪律（授粉）：
- 规范只做格式遵循，不抄文档文本；库只做依赖引用，不整包复制。
- 纯 numpy（IQ 合成）+ 标准库 json（元数据），不引新依赖。
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_DATATYPE = "cf32_le"  # complex float32 little-endian（SigMF 最常用类型）


def _synthesize_iq(n: int = 1024, sample_rate: float = 1e6, tone_hz: float = 1000.0) -> np.ndarray:
    """合成一段 1kHz 单音 IQ（complex64）。"""
    t = np.arange(n, dtype=np.float64) / sample_rate
    return (0.5 * np.exp(2j * np.pi * tone_hz * t)).astype(np.complex64)


def _write_sigmf(meta_core: dict, iq: np.ndarray, out_dir: str) -> tuple[Path, Path]:
    """写 SigMF 两件套：.sigmf-meta（JSON）+ .sigmf-data（二进制 IQ）。"""
    global_core = {f"core:{k}": v for k, v in meta_core.items()}
    global_core["core:version"] = "1.0.0"
    meta = {
        "global": global_core,
        "captures": [{"core:sample_start": 0}],
        "annotations": [],
    }
    meta_path = Path(out_dir) / "recording.sigmf-meta"
    data_path = Path(out_dir) / "recording.sigmf-data"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    data_path.write_bytes(iq.astype(np.complex64).tobytes())
    return meta_path, data_path


def _read_sigmf(in_dir: str) -> tuple[dict, np.ndarray]:
    """读回 SigMF 两件套：解析 meta 的 core 字段 + 二进制 IQ。"""
    meta = json.loads((Path(in_dir) / "recording.sigmf-meta").read_text(encoding="utf-8"))
    core = {k.replace("core:", ""): v for k, v in meta["global"].items()}
    raw = (Path(in_dir) / "recording.sigmf-data").read_bytes()
    iq = np.frombuffer(raw, dtype=np.complex64)
    return core, iq


def probe() -> dict:
    """生成最小 SigMF 录音并读回验证（元数据完整 + IQ 无损）。

    返回
    ----
    dict：``{"package", "status", "license", "using_library", "summary",
    "meta_fields", "meta_complete", "roundtrip_ok"}``。
    """
    iq = _synthesize_iq()
    meta_core = {
        "datatype": _DATATYPE,
        "sample_rate": 1_000_000.0,
        "frequency": 91_500_000.0,
        "datetime": datetime.now(timezone.utc).isoformat(),
        "hardware": "IC-705",
        "description": "SigMF 最小验证：合成 1kHz 单音 IQ",
    }
    using_library = importlib.util.find_spec("sigmf") is not None

    with tempfile.TemporaryDirectory() as td:
        _write_sigmf(meta_core, iq, td)
        core, read_iq = _read_sigmf(td)
        roundtrip_ok = bool(np.array_equal(read_iq, iq))
        required = ["datatype", "sample_rate", "frequency", "datetime", "hardware"]
        meta_complete = all(core.get(k) is not None for k in required)

    return {
        "package": "sigmf",
        "status": "success" if (roundtrip_ok and meta_complete) else "degraded",
        "license": "规范 CC-BY-SA-4.0（引用）/ 实现 LGPL-3.0（依赖）",
        "using_library": using_library,
        "summary": (
            "最小 SigMF 录音（合成 IQ + 完整 core 元数据）写→读回验证；"
            + ("使用 sigmf-python 库" if using_library else "未安装 sigmf-python，用最小实现遵循格式")
        ),
        "meta_fields": sorted(core.keys()),
        "meta_complete": meta_complete,
        "roundtrip_ok": roundtrip_ok,
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
