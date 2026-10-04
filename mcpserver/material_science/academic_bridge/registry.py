"""academic 16 项目注册表（SPEC-02 Phase 1）。

仅登记元数据（许可/安装方式/文档路径/是否可本地调用），
实际调用入口在 bridge.py。许可详情见仓库根目录 ../academic/LICENSES.md。
"""

from pathlib import Path

# 16 项目元数据：name -> 描述
# call: bridge.py 是否提供本地调用函数
# pypi: 安装方式（None 表示需源码/硬件/独立环境）
PROJECTS = {
    "thermo": {
        "label": "thermo (ChEDL)",
        "domain": "物性/热力学",
        "license": "MIT",
        "import_name": "thermo",
        "pypi": "thermo",
        "call": True,
    },
    "CoolProp": {
        "label": "CoolProp",
        "domain": "热物性数据库",
        "license": "MIT-like",
        "import_name": "CoolProp",
        "pypi": "coolprop",
        "call": True,
    },
    "tespy": {
        "label": "TESPy",
        "domain": "热工系统仿真",
        "license": "MIT",
        "import_name": "tespy",
        "pypi": "tespy",
        "call": False,  # 重依赖，按需人工安装
    },
    "pycalphad": {
        "label": "pycalphad",
        "domain": "CALPHAD 相图",
        "license": "MIT",
        "import_name": "pycalphad",
        "pypi": "pycalphad",
        "call": False,
    },
    "Clapeyron.jl": {
        "label": "Clapeyron.jl",
        "domain": "状态方程",
        "license": "MIT",
        "import_name": "pyclapeyron",
        "pypi": "pyclapeyron",
        "call": False,  # 需 Julia 运行时
    },
    "PyXtal": {
        "label": "PyXtal",
        "domain": "晶体结构生成",
        "license": "MIT",
        "import_name": "pyxtal",
        "pypi": "pyxtal",
        "call": False,
    },
    "SLICES": {
        "label": "SLICES",
        "domain": "晶体字符串表示",
        "license": "MIT*",
        "import_name": "slices",
        "pypi": None,  # 独立 conda 环境
        "call": False,
    },
    "gemmi": {
        "label": "gemmi",
        "domain": "晶体学文件",
        "license": "MPLv2/LGPLv3",  # 非白名单口径，默认不自动调用
        "import_name": "gemmi",
        "pypi": "gemmi",
        "call": False,
    },
    "ChemFormula": {
        "label": "ChemFormula",
        "domain": "化学式/计量",
        "license": "MIT",
        "import_name": "chemformula",
        "pypi": "chemformula",
        "call": True,
    },
    "hyalite": {
        "label": "hyalite",
        "domain": "序列比对(Rust)",
        "license": "MIT",
        "import_name": None,  # Rust crate
        "pypi": None,
        "call": False,
    },
    "AffineGaps": {
        "label": "AffineGaps",
        "domain": "序列比对(Py)",
        "license": "Apache-2.0",
        "import_name": "affine_gaps",
        "pypi": "affine-gaps",
        "call": True,
    },
    "WaveBench": {
        "label": "WaveBench",
        "domain": "仪器测量台",
        "license": "MIT",
        "import_name": "wavebench",
        "pypi": None,  # 独立环境 + 硬件
        "call": False,
    },
    "rp2daq": {
        "label": "rp2daq",
        "domain": "微控制器采集",
        "license": "MIT",
        "import_name": "rp2daq",
        "pypi": None,  # 需 RP2040 硬件
        "call": False,
    },
    "hololinked": {
        "label": "hololinked",
        "domain": "仪器 SCADA/IoT",
        "license": "BSD-3-Clause",
        "import_name": "hololinked",
        "pypi": "hololinked",
        "call": False,
    },
    "Pynite": {
        "label": "Pynite",
        "domain": "结构有限元",
        "license": "MIT",
        "import_name": "Pynite",
        "pypi": "PyniteFEA",
        "call": True,
    },
    "FEMcy": {
        "label": "FEMcy",
        "domain": "连续体有限元",
        "license": "上游待复核",
        "import_name": None,  # 脚本式运行，非库
        "pypi": None,
        "call": False,
    },
}


def doc_path(project: str) -> Path | None:
    """项目 MODEL_INTERFACE.md 的路径（仓库根目录/academic/<name>/）。"""
    root = Path(__file__).resolve().parents[3]
    p = root / "academic" / project / "MODEL_INTERFACE.md"
    return p if p.exists() else None


def is_installed(project: str) -> bool:
    """探测项目对应 Python 包是否可导入（无 import_name 恒为 False）。"""
    meta = PROJECTS.get(project)
    if not meta or not meta.get("import_name"):
        return False
    import importlib.util
    return importlib.util.find_spec(meta["import_name"]) is not None
