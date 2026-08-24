"""academic 16 包融合层级总表（W-09 单一事实源）。

数据来源：scratchpad-knowledge/_readme_dump/*.txt（16 份 README 全量 dump）+
FUSION_REPORT.md 初评 + 本仓落地实况（chem_adapter/bio_adapter 为既有融合样板）。
五层级口径与 scratchpad-knowledge/TRAE_PROMPT.md 一致：
MCP / Skill / 融合参考 / 耦合 / 基础设施。

每项字段：level / license / pip（可直调安装名，None=不可直调）/
runtime_deps（硬约束运行依赖，只标注不否决）/ status（本仓落地状态）/ notes。
"""
from __future__ import annotations

FUSION_LEVELS: dict[str, dict] = {
    # ---- 本单封装 MODEL_INTERFACE（Lumo 可调用）----
    "CoolProp": {
        "level": "MCP",
        "license": "MIT",
        "pip": "coolprop",
        "runtime_deps": [],
        "status": "已封装 MODEL_INTERFACE（mcpserver/academic/coolprop_interface.py），venv 实测可用",
        "notes": "工业级热物性库，PropsSI 双参/六参统一入口，SI 单位制",
    },
    "tespy": {
        "level": "MCP",
        "license": "MIT",
        "pip": "tespy",
        "runtime_deps": [],
        "status": "已封装 MODEL_INTERFACE（mcpserver/academic/tespy_interface.py），依赖未装时明确降级",
        "notes": "热力系统网络仿真；版本敏感（0.9/0.11 单位 API 变更），接口钉死构造参数",
    },
    "SLICES": {
        "level": "MCP",
        "license": "LGPL-2.1",
        "pip": "slices",
        "runtime_deps": ["tensorflow-cpu", "m3gnet", "pymatgen（版本钉死）"],
        "status": "已封装 MODEL_INTERFACE（mcpserver/academic/slices_interface.py），重依赖只标注不否决",
        "notes": "晶体结构↔可逆字符串；克隆内无 slices 包本体，走 PyPI 独立分发",
    },
    "thermo": {
        "level": "MCP",
        "license": "MIT",
        "pip": "thermo",
        "runtime_deps": [],
        "status": "候选：接口形态与 CoolProp 同构（Chemical/Mixture），未在本单封装",
        "notes": "化工物性库，常数检索+T/P 依赖物性+混合物相平衡",
    },
    # ---- E-01 化学库四件（chembl/oddt/Indigo/scikit-fingerprints）----
    "Indigo": {
        "level": "MCP",
        "license": "Apache-2.0",
        "pip": "epam-indigo",
        "runtime_deps": [],
        "status": "已封装 MODEL_INTERFACE（mcpserver/academic/indigo_interface.py），venv 实测可用",
        "notes": "通用化学信息学：SMILES 解析/分子量/分子式/子结构匹配；Windows 有 wheel",
    },
    "ChEMBL": {
        "level": "MCP",
        "license": "Apache-2.0",
        "pip": "chembl-webresource-client",
        "runtime_deps": ["在线 EBI REST API（requests-cache 自动缓存）"],
        "status": "已封装 MODEL_INTERFACE（mcpserver/academic/chembl_interface.py），venv 实测在线可用",
        "notes": "欧洲生物活性分子库：CHEMBL_ID 查询/相似性检索；离线时降级为同形错误",
    },
    "scikit-fingerprints": {
        "level": "MCP(候选)",
        "license": "MIT",
        "pip": "scikit-fingerprints",
        "runtime_deps": ["rdkit"],
        "status": "候选封装：>30 种分子指纹（ECFP/Morgan/MACCS…），sklearn 风格 transform；RDKit 未装→只标注不否决",
        "notes": "与 Indigo 指纹能力重叠；RDKit 装后可复用 indigo 同构封装",
    },
    "ODDT": {
        "level": "融合参考",
        "license": "BSD-3-Clause",
        "pip": "oddt",
        "runtime_deps": ["rdkit 或 openbabel", "scikit-learn", "pandas"],
        "status": "未封装：docking/虚拟筛选/rescoring 管线工具；v0.8（2021）维护趋缓",
        "notes": "药效团/打分函数可借鉴；主力场景需分子对接软件（如 AutoDock Vina）",
    },
    # ---- 耦合（源码合入本仓）----
    "ChemFormula": {
        "level": "耦合",
        "license": "MIT",
        "pip": "chemformula",
        "runtime_deps": [],
        "status": "已耦合（mcpserver/adapters/chem_adapter 源码拷贝）+ 本单封装 MODEL_INTERFACE",
        "notes": "化学式解析/分子量/质量分数/化学式算术；依赖 casregnum",
    },
    "AffineGaps": {
        "level": "耦合",
        "license": "Apache-2.0",
        "pip": None,
        "runtime_deps": ["numpy（numba 可选 JIT）"],
        "status": "已耦合（mcpserver/adapters/bio_adapter/align.py 源码拷贝）",
        "notes": "修正 Gotoh 数学的仿射空位序列比对（NW/SW/Levenshtein）",
    },
    "Pynite": {
        "level": "耦合",
        "license": "MIT",
        "pip": "PyniteFEA",
        "runtime_deps": ["numpy", "scipy"],
        "status": "候选耦合：3D 弹性 FEM（框架/板/模态/pushover），knowledge-base 仅残留占位",
        "notes": "纯 Python FEModel3D，作 Lumo 结构计算底座候选",
    },
    "FEMcy": {
        "level": "耦合",
        "license": "MIT",
        "pip": None,
        "runtime_deps": ["taichi", "numpy", "scipy"],
        "status": "候选耦合：Taichi 并行 FEM，脚本式入口需改造为库调用",
        "notes": "CPU/GPU 有限元，Abaqus .inp 前处理",
    },
    # ---- 融合参考（提炼设计，不即插即用）----
    "Clapeyron.jl": {
        "level": "融合参考",
        "license": "MIT",
        "pip": None,
        "runtime_deps": ["Julia>=1.10"],
        "status": "不可直调（Julia 包）；官方 pyclapeyron 桥可后评估",
        "notes": "热力学 EoS 框架，可借鉴其模型注册与相平衡求解分层",
    },
    "PyXtal": {
        "level": "融合参考",
        "license": "MIT",
        "pip": "pyxtal",
        "runtime_deps": ["pymatgen", "ase", "spglib"],
        "status": "未封装：随机晶体生成依赖链重",
        "notes": "晶体结构随机生成 + XRD，可借鉴 Wyckoff 位搜索设计",
    },
    "pycalphad": {
        "level": "融合参考",
        "license": "MIT",
        "pip": "pycalphad",
        "runtime_deps": [],
        "status": "未封装：CALPHAD 相图计算，Cython 内核 PyPI 有 wheel",
        "notes": "TDB 解析+Gibbs 能最小化，相图计算底座候选",
    },
    "hyalite": {
        "level": "融合参考",
        "license": "MIT",
        "pip": None,
        "runtime_deps": ["Rust（MSRV 1.85）"],
        "status": "不可直调（纯 Rust crate）；可借鉴 SIMD 多后端逐位一致设计",
        "notes": "精确序列比对，与 AffineGaps 职能重叠（后者已耦合）",
    },
    # ---- 基础设施（独立部署，不进主仓）----
    "gemmi": {
        "level": "基础设施",
        "license": "MPL-2.0 或 LGPL-3.0（双许可）",
        "pip": "gemmi",
        "runtime_deps": [],
        "status": "独立服务候选：晶体学文件格式底座（mmCIF/PDB/MTZ/MRC）",
        "notes": "文件级 copyleft 需注意分发边界",
    },
    "WaveBench": {
        "level": "基础设施",
        "license": "MIT",
        "pip": None,
        "runtime_deps": ["SCPI 仪器（--fake 可离线）"],
        "status": "独立台架：自带只读 HTTP MCP 接口，接仪器后直挂 mcpserver",
        "notes": "仪器抽象层/声明式运行计划可借鉴",
    },
    "rp2daq": {
        "level": "基础设施",
        "license": "MIT",
        "pip": "rp2daq",
        "runtime_deps": ["树莓派 Pico 硬件+固件"],
        "status": "平台依赖，独立部署",
        "notes": "C 固件+Python API 动态生成命令的设计可借鉴",
    },
    "hololinked": {
        "level": "基础设施",
        "license": "待核（README dump 未含许可文本）",
        "pip": "hololinked",
        "runtime_deps": ["aiomqtt（MQTT 时）"],
        "status": "IoT 互操作框架，独立部署；融合前须核 LICENSE",
        "notes": "W3C WoT Thing Description 标准化设备描述",
    },
}

LEVEL_ORDER = ["MCP", "Skill", "融合参考", "耦合", "基础设施"]


def levels_summary() -> dict[str, int]:
    """各层级包数汇总（验收：16 全标注）。"""
    out = {lvl: 0 for lvl in LEVEL_ORDER}
    for info in FUSION_LEVELS.values():
        out[info["level"]] += 1
    return out


def package_count() -> int:
    return len(FUSION_LEVELS)
