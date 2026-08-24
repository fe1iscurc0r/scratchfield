"""ChEMBL MODEL_INTERFACE — 欧洲生物活性分子数据库 REST 客户端（Lumo · E-01）。

上游：https://github.com/chembl/chembl_webresource_client （Apache-2.0，
PyPI: chembl-webresource-client）——官方纯 Python 客户端，基于 EBI REST API
（https://www.ebi.ac.uk/chembl/api/data），内置 requests-cache 自动缓存。
本仓 venv 实测在线可用：CHEMBL25=ASPIRIN，SMILES 与名称均正确返回。
网络不可达时降级为 AcademicDependencyError 同形错误（仅标注，不否决）。
"""
from __future__ import annotations

from typing import Any

MODEL_INTERFACE: dict[str, Any] = {
    "name": "chembl",
    "package": "ChEMBL",
    "vendor_repo": "https://github.com/chembl/chembl_webresource_client",
    "pip": "chembl-webresource-client",
    "license": "Apache-2.0",
    "fusion_level": "MCP",
    "description": "欧洲生物活性分子库：CHEMBL_ID 查询/相似性检索（SMILES→相似分子），在线 REST",
    "entrypoints": [
        {
            "command": "chembl_molecule",
            "params": {"chembl_id": "CHEMBL 编号，如 CHEMBL25"},
            "returns": {"pref_name": "str", "canonical_smiles": "str",
                        "molecular_formula": "str"},
            "example": "chembl_molecule('CHEMBL25') → {pref_name: 'ASPIRIN', "
                       "canonical_smiles: 'CC(=O)Oc1ccccc1C(=O)O'}",
        },
        {
            "command": "chembl_search_smiles",
            "params": {"smiles": "查询 SMILES", "similarity": "相似度阈值 0-100（默认 90）",
                       "limit": "返回条数（默认 5，上限 20）"},
            "returns": {"hits": "[{chembl_id, pref_name, similarity}]"},
            "example": "chembl_search_smiles('CC(=O)Oc1ccccc1C(=O)O', 95) → 阿司匹林相似物",
        },
    ],
    "runtime_deps": ["在线 EBI REST API（requests-cache 自动本地缓存）"],
    "degradation": "包缺失→pip install chembl-webresource-client；网络不可达→抛含恢复提示的降级错误",
    "verified": "2026-08-23 本仓 .venv 实测：CHEMBL25=ASPIRIN 名称/SMILES 正确返回",
}


class _ChEMBLUnavailable(RuntimeError):
    """ChEMBL 在线不可用（网络/服务/解析失败），与依赖缺失同形降级。"""


def _client() -> Any:
    """惰性加载 new_client；缺失/不可达统一降级。"""
    try:
        from chembl_webresource_client.new_client import new_client
        return new_client
    except Exception as e:  # ImportError 或在线初始化失败
        raise _ChEMBLUnavailable(
            "ChEMBL 客户端不可用：pip install chembl-webresource-client，"
            "且需可访问 https://www.ebi.ac.uk/chembl/ （在线 REST）") from e


def chembl_molecule(chembl_id: str) -> dict[str, Any]:
    """CHEMBL_ID → 分子基础信息（名称/SMILES/分子式）。"""
    chembl_id = (chembl_id or "").strip()
    if not chembl_id or not chembl_id.upper().startswith("CHEMBL"):
        raise ValueError("chembl_id 格式应为 CHEMBL 加编号，如 'CHEMBL25'")
    try:
        rec = _client().molecule.get(chembl_id.upper())
    except _ChEMBLUnavailable:
        raise
    except Exception as e:
        raise _ChEMBLUnavailable(f"ChEMBL 在线查询失败（{chembl_id}）: {e}") from e
    if not rec:
        raise ValueError(f"ChEMBL 未找到 {chembl_id}（编号不存在或已废弃）")
    struct = rec.get("molecule_structures") or {}
    smiles = struct.get("canonical_smiles")
    if not smiles:
        raise ValueError(f"{chembl_id} 无 canonical SMILES（可能为无机/混合物）")
    return {"ok": True, "chembl_id": chembl_id.upper(),
            "pref_name": rec.get("pref_name"),
            "canonical_smiles": smiles,
            "molecular_formula": struct.get("molecular_formula"),
            "source": MODEL_INTERFACE["package"]}


def chembl_search_smiles(smiles: str, similarity: int = 90,
                         limit: int = 5) -> dict[str, Any]:
    """SMILES 相似性检索 → 相似分子列表（在线 REST）。"""
    smiles = (smiles or "").strip()
    if not smiles:
        raise ValueError("smiles 不能为空")
    similarity = int(similarity)
    limit = min(max(int(limit), 1), 20)
    if not 0 <= similarity <= 100:
        raise ValueError("similarity 必须在 0-100 之间")
    try:
        hits = list(_client().similarity.filter(
            smiles=smiles, similarity=similarity)[:limit])
    except _ChEMBLUnavailable:
        raise
    except Exception as e:
        raise _ChEMBLUnavailable(f"ChEMBL 相似性检索失败: {e}") from e
    return {"ok": True, "query_smiles": smiles, "similarity_threshold": similarity,
            "hits": [
                {"chembl_id": h.get("molecule_chembl_id"),
                 "pref_name": h.get("pref_name"),
                 "similarity": h.get("similarity")}
                for h in hits
            ],
            "source": MODEL_INTERFACE["package"]}
