"""scikit-fingerprints MCP 封装 · scikit-learn 风格分子指纹库 (MIT)

把分子指纹库（ECFP/Morgan/MACCS/拓扑指纹等 >30 种）封装为陆墨 MCP 工具体系的一个 agent。
scikit-learn 风格：transform(SMILES list) 一行出描述符矩阵，可直接接 sklearn 模型训练。
skfp 硬依赖 rdkit（本仓 venv 未装），按契约只标注不否决：缺失抛 AcademicDependencyError。

4 个命令：
  skfp_fingerprint       指纹计算（SMILES → 指纹位向量）
  skfp_similarity_matrix 相似度矩阵（SMILES → 两两 Tanimoto）
  skfp_transform         特征变换（SMILES → sklearn 兼容特征矩阵）
  skfp_scaffold          骨架分析（SMILES → Murcko 骨架）

契约（docs/academic/MODEL_INTERFACE.md）：
  返回 {ok: true, ...data, source: "scikit-fingerprints"}；参数非法抛 ValueError；
  依赖缺失抛 AcademicDependencyError（含 pip install 提示）。

边界：独立目录 mcpserver/scikit_fingerprints/，仅通过 MCP 调度接入，不碰主流程。
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    from system.config import logger
except ImportError:  # 独立 pytest 时降级到标准 logging
    logger = logging.getLogger("scikit_fingerprints")

try:
    from mcpserver.academic.errors import AcademicDependencyError
except ImportError:  # 独立运行/测试时使用本地同形类

    class AcademicDependencyError(RuntimeError):
        def __init__(self, package: str, pip_name: str, extra: str = ""):
            hint = f"{package} 未安装：pip install {pip_name} 后可用"
            if extra:
                hint += f"（{extra}）"
            super().__init__(hint)


# 指纹类型 → skfp 类名（构造参数不同，见 _make_fingerprinter）
_FP_TYPES = {
    "ECFP": "ECFPFingerprint",
    "Morgan": "MorganFingerprint",
    "MACCS": "MACCSFingerprint",
    "Topological": "TopologicalFingerprint",
}
_RADIUS_TYPES = {"ECFP", "Morgan"}


def _skfp() -> Any:
    """惰性加载 skfp；缺失抛 AcademicDependencyError（含 pip 提示）。"""
    try:
        import skfp

        return skfp
    except Exception as e:
        raise AcademicDependencyError(
            "scikit-fingerprints", "scikit-fingerprints", "skfp 硬依赖 rdkit，缺失时一并 pip install rdkit"
        ) from e


def _load_rdkit_scaffold() -> tuple[Any, Any]:
    """加载 rdkit Chem + MurckoScaffold；缺失抛 AcademicDependencyError（统一降级入口）。"""
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold

        return Chem, MurckoScaffold
    except ImportError as e:
        raise AcademicDependencyError("rdkit", "rdkit", "骨架分析需要 RDKit 分子工具包") from e


def _make_fingerprinter(skfp: Any, fp_type: str, radius: int, fp_size: int) -> Any:
    """构造指纹器实例：ECFP/Morgan 带 radius，MACCS/拓扑只有 fp_size。"""
    cls = getattr(skfp.fingerprints, _FP_TYPES[fp_type])
    if fp_type in _RADIUS_TYPES:
        return cls(radius=radius, fp_size=fp_size)
    return cls(fp_size=fp_size)


def _compute_bits(skfp: Any, smiles_list: list[str], fp_type: str, radius: int, fp_size: int) -> list[list[int]]:
    """SMILES 列表 → 每分子 1 位向量（非零位索引列表）。"""
    fp = _make_fingerprinter(skfp, fp_type, radius, fp_size)
    mat = fp.transform(smiles_list)  # numpy 2D 或 list of list
    rows = []
    for row in mat:
        bits = [j for j, v in enumerate(row) if v]
        rows.append(bits)
    return rows


def _tanimoto(a_bits: list[int], b_bits: list[int]) -> float:
    """Tanimoto / Jaccard 相似度（纯 Python，避免 numpy 依赖）。"""
    sa, sb = set(a_bits), set(b_bits)
    union = len(sa | sb)
    return round(len(sa & sb) / union, 4) if union else 0.0


def _split_smiles(raw: Any) -> list[str]:
    """兼容 list / 逗号分隔字符串输入。"""
    if isinstance(raw, str):
        items = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
    else:
        items = [str(x).strip() for x in raw if str(x).strip()]
    return items


class ScikitFingerprintsAgent:
    """scikit-fingerprints 分子指纹 agent（sklearn 风格特征工程入口）。"""

    def __init__(self):
        self.name = "scikit_fingerprints"
        self.display_name = "scikit-fingerprints 分子指纹"
        self.version = "1.0.0"
        self.description = (
            "分子指纹库：ECFP/Morgan/MACCS/拓扑指纹计算、Tanimoto 相似度矩阵、sklearn 特征变换、Murcko 骨架分析"
        )
        self.tools = {
            "skfp_fingerprint": self._skfp_fingerprint,
            "skfp_similarity_matrix": self._skfp_similarity_matrix,
            "skfp_transform": self._skfp_transform,
            "skfp_scaffold": self._skfp_scaffold,
        }
        logger.info(f"[MCP] {self.display_name} 初始化完成，共 {len(self.tools)} 个工具")

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """类方法入口（总线契约）：委托 invoke 分发。

        注册表运行时按 instance.handle_handoff 调用（Format A: {module, class}），
        task 格式 {"tool": ..., "params": {...}}，返回 JSON 字符串。
        """
        command = str(task.get("tool") or task.get("command") or "").strip()
        params = task.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            result = self.invoke(command, params)
        except ValueError as e:  # invoke 对未知命令/坏参数 fail-fast，总线边界落 JSON 不崩
            result = {"status": "error", "error": str(e)}
        return json.dumps(result, ensure_ascii=False, default=str)

    def invoke(self, command: str, params: dict | None = None) -> dict:
        """MCP 分发入口：按命令名调用对应工具。"""
        params = params or {}
        fn = self.tools.get(command)
        if fn is None:
            raise ValueError(f"未知命令 {command!r}，可用命令: {sorted(self.tools)}")
        return fn(params)

    @staticmethod
    def _common_fp_params(params: dict) -> tuple[str, int, int]:
        """解析并校验公共指纹参数（fp_type/radius/fp_size）。"""
        fp_type = str(params.get("fingerprint_type") or "ECFP")
        if fp_type not in _FP_TYPES:
            raise ValueError(f"fingerprint_type 应为 {sorted(_FP_TYPES)} 之一（当前 {fp_type!r}）")
        radius_raw = params.get("radius")
        radius = int(radius_raw) if radius_raw is not None else 2
        fp_size_raw = params.get("fp_size")
        fp_size = int(fp_size_raw) if fp_size_raw is not None else 2048
        if radius < 0:
            raise ValueError("radius 不能为负")
        if fp_size <= 0 or fp_size > 65536:
            raise ValueError("fp_size 应在 1-65536 之间")
        return fp_type, radius, fp_size

    # ---- 1. 指纹计算 ----

    def _skfp_fingerprint(self, params: dict) -> dict:
        smiles_list = _split_smiles(params.get("smiles_list"))
        if not smiles_list:
            raise ValueError("smiles_list 不能为空（SMILES 列表或逗号分隔字符串）")
        fp_type, radius, fp_size = self._common_fp_params(params)
        skfp = _skfp()
        bits_rows = _compute_bits(skfp, smiles_list, fp_type, radius, fp_size)
        fingerprints = [
            {
                "index": i,
                "smiles": s,
                "num_bits": len(bits),
                "bit_indices": bits,
            }
            for i, (s, bits) in enumerate(zip(smiles_list, bits_rows))
        ]
        return {
            "ok": True,
            "fingerprint_type": fp_type,
            "radius": radius if fp_type in _RADIUS_TYPES else None,
            "fp_size": fp_size,
            "count": len(fingerprints),
            "fingerprints": fingerprints,
            "source": "scikit-fingerprints",
        }

    # ---- 2. 相似度矩阵 ----

    def _skfp_similarity_matrix(self, params: dict) -> dict:
        smiles_list = _split_smiles(params.get("smiles_list"))
        if len(smiles_list) < 2:
            raise ValueError("smiles_list 至少需要 2 个分子才能计算相似度矩阵")
        fp_type, radius, fp_size = self._common_fp_params(params)
        skfp = _skfp()
        bits_rows = _compute_bits(skfp, smiles_list, fp_type, radius, fp_size)
        matrix = []
        for i, a in enumerate(bits_rows):
            row = [
                {
                    "index": j,
                    "smiles": smiles_list[j],
                    "similarity": _tanimoto(a, b),
                }
                for j, b in enumerate(bits_rows)
            ]
            matrix.append({"index": i, "smiles": smiles_list[i], "row": row})
        return {
            "ok": True,
            "fingerprint_type": fp_type,
            "radius": radius if fp_type in _RADIUS_TYPES else None,
            "fp_size": fp_size,
            "n": len(smiles_list),
            "matrix": matrix,
            "source": "scikit-fingerprints",
        }

    # ---- 3. 特征变换 ----

    def _skfp_transform(self, params: dict) -> dict:
        smiles_list = _split_smiles(params.get("smiles_list"))
        if not smiles_list:
            raise ValueError("smiles_list 不能为空（SMILES 列表或逗号分隔字符串）")
        fp_type, radius, fp_size = self._common_fp_params(params)
        skfp = _skfp()
        bits_rows = _compute_bits(skfp, smiles_list, fp_type, radius, fp_size)
        # sklearn 兼容特征矩阵视图：rows × cols 稀疏描述
        features = [
            {
                "index": i,
                "smiles": s,
                "nonzero_positions": bits,
            }
            for i, (s, bits) in enumerate(zip(smiles_list, bits_rows))
        ]
        return {
            "ok": True,
            "fingerprint_type": fp_type,
            "radius": radius if fp_type in _RADIUS_TYPES else None,
            "rows": len(smiles_list),
            "cols": fp_size,
            "density": round(sum(len(b) for b in bits_rows) / (len(bits_rows) * fp_size), 6),
            "features": features,
            "source": "scikit-fingerprints",
        }

    # ---- 4. 骨架分析 ----

    def _skfp_scaffold(self, params: dict) -> dict:
        smiles = str(params.get("smiles") or "").strip()
        if not smiles:
            raise ValueError("smiles 不能为空（单个分子 SMILES）")
        Chem, MurckoScaffold = _load_rdkit_scaffold()
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"无效 SMILES（rdkit 无法解析）: {smiles!r}")
        scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
        generic = MurckoScaffold.MakeScaffoldGeneric(mol=mol)
        return {
            "ok": True,
            "smiles": smiles,
            "scaffold_smiles": scaffold,
            "generic_scaffold": str(generic) if generic else None,
            "source": "scikit-fingerprints",
        }
