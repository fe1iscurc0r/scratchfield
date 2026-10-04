"""ChEMBL MCP 封装 · chembl/chembl_webresource_client (Apache-2.0)

把欧洲生物活性分子库（EBI REST）封装为陆墨 MCP 工具体系的一个 agent。
官方纯 Python 客户端内置 requests-cache 自动缓存，在线 REST 依赖。

6 个命令：
  chembl_search_compound  按名称/前缀搜索化合物
  chembl_target           靶点信息（CHEMBL_ID → 名称/物种/类型/组件）
  chembl_activity         活性数据（分子 → assay 活性测定）
  chembl_structure        结构获取（CHEMBL_ID → SMILES + molfile）
  chembl_similarity       相似度搜索（SMILES → 相似分子）
  chembl_batch            批次下载（多个 CHEMBL_ID 批量拉取）

契约（docs/academic/MODEL_INTERFACE.md）：
  返回 {ok: true, ...data, source: "ChEMBL"}；参数非法抛 ValueError；
  依赖缺失抛 AcademicDependencyError（含 pip install 提示）；
  网络不可达抛同形降级错误（只标注不否决）。

边界：独立目录 mcpserver/chembl/，仅通过 MCP 调度接入，不碰主流程。
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    from system.config import logger
except ImportError:  # 独立 pytest 时降级到标准 logging
    logger = logging.getLogger("chembl")

try:
    from mcpserver.academic.errors import AcademicDependencyError
except ImportError:  # 独立运行/测试时使用本地同形类

    class AcademicDependencyError(RuntimeError):
        def __init__(self, package: str, pip_name: str, extra: str = ""):
            hint = f"{package} 未安装：pip install {pip_name} 后可用"
            if extra:
                hint += f"（{extra}）"
            super().__init__(hint)


class _ChEMBLUnavailable(RuntimeError):
    """ChEMBL 在线不可用（网络/服务/解析失败），与依赖缺失同形降级。"""


def _client() -> Any:
    """惰性加载 new_client；缺失抛 AcademicDependencyError，不可达抛降级错误。"""
    try:
        from chembl_webresource_client.new_client import new_client

        return new_client
    except AcademicDependencyError:
        raise
    except Exception as e:
        raise AcademicDependencyError(
            "chembl-webresource-client",
            "chembl-webresource-client",
            "在线 EBI REST，需网络可达 https://www.ebi.ac.uk/chembl/",
        ) from e


def _first_of(rec: dict, *keys: str, default: Any = None) -> Any:
    """多键兼容取值（新旧版客户端字段名差异）。"""
    for k in keys:
        if rec.get(k) not in (None, ""):
            return rec.get(k)
    return default


class ChEMBLAgent:
    """ChEMBL 生物活性分子库 agent（封装 EBI REST 官方客户端）。"""

    def __init__(self):
        self.name = "chembl"
        self.display_name = "ChEMBL 生物活性分子库"
        self.version = "1.0.0"
        self.description = "欧洲生物活性分子库：化合物搜索/靶点/活性/结构/相似度/批量下载（在线 EBI REST）"
        self.tools = {
            "chembl_search_compound": self._chembl_search_compound,
            "chembl_target": self._chembl_target,
            "chembl_activity": self._chembl_activity,
            "chembl_structure": self._chembl_structure,
            "chembl_similarity": self._chembl_similarity,
            "chembl_batch": self._chembl_batch,
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

    # ---- 1. 搜索化合物 ----

    def _chembl_search_compound(self, params: dict) -> dict:
        query = str(params.get("query") or "").strip()
        if not query:
            raise ValueError("query 不能为空（化合物名称或前缀，如 'aspirin' 或 'CHEMBL25'）")
        limit = min(max(int(params.get("limit") or 5), 1), 20)
        try:
            nc = _client()
            if query.upper().startswith("CHEMBL"):
                hits = list(nc.molecule.get(query.upper())) if False else list([nc.molecule.get(query.upper())])
            else:
                hits = list(nc.molecule.filter(pref_name__icontains=query)[:limit])
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 化合物搜索失败（query={query}）: {e}") from e
        result = []
        for h in hits:
            if not h:
                continue
            result.append(
                {
                    "chembl_id": h.get("molecule_chembl_id") or h.get("chembl_id"),
                    "pref_name": h.get("pref_name"),
                    "formula": _first_of(h, "molecule_formula", "molecular_formula"),
                }
            )
        return {"ok": True, "query": query, "count": len(result), "hits": result, "source": "ChEMBL"}

    # ---- 2. 靶点信息 ----

    def _chembl_target(self, params: dict) -> dict:
        target_id = str(params.get("target_id") or "").strip().upper()
        if not target_id.startswith("CHEMBL"):
            raise ValueError("target_id 格式应为 CHEMBL 加编号，如 'CHEMBL2368546'")
        try:
            rec = _client().target.get(target_id)
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 靶点查询失败（{target_id}）: {e}") from e
        if not rec:
            raise ValueError(f"ChEMBL 未找到靶点 {target_id}（编号不存在或已废弃）")
        comps = []
        for c in rec.get("target_components") or []:
            comps.append(
                {
                    "accession": c.get("accession"),
                    "description": c.get("description"),
                    "component_type": c.get("component_type"),
                }
            )
        return {
            "ok": True,
            "target_id": target_id,
            "pref_name": rec.get("pref_name"),
            "organism": rec.get("organism"),
            "target_type": rec.get("target_type"),
            "components": comps,
            "source": "ChEMBL",
        }

    # ---- 3. 活性数据 ----

    def _chembl_activity(self, params: dict) -> dict:
        chembl_id = str(params.get("chembl_id") or "").strip().upper()
        if not chembl_id.startswith("CHEMBL"):
            raise ValueError("chembl_id 格式应为 CHEMBL 加编号，如 'CHEMBL25'")
        limit = min(max(int(params.get("limit") or 10), 1), 100)
        try:
            rows = list(_client().activity.filter(molecule_chembl_id=chembl_id)[:limit])
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 活性数据查询失败（{chembl_id}）: {e}") from e
        activities = [
            {
                "assay_chembl_id": a.get("assay_chembl_id"),
                "target_chembl_id": a.get("target_chembl_id"),
                "standard_type": a.get("standard_type"),
                "standard_value": a.get("standard_value"),
                "standard_units": a.get("standard_units"),
                "pchembl_value": a.get("pchembl_value"),
                "relation": a.get("standard_relation"),
            }
            for a in rows
        ]
        return {
            "ok": True,
            "chembl_id": chembl_id,
            "count": len(activities),
            "activities": activities,
            "source": "ChEMBL",
        }

    # ---- 4. 结构获取 ----

    def _chembl_structure(self, params: dict) -> dict:
        chembl_id = str(params.get("chembl_id") or "").strip().upper()
        if not chembl_id.startswith("CHEMBL"):
            raise ValueError("chembl_id 格式应为 CHEMBL 加编号，如 'CHEMBL25'")
        try:
            rec = _client().molecule.get(chembl_id)
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 结构获取失败（{chembl_id}）: {e}") from e
        if not rec:
            raise ValueError(f"ChEMBL 未找到 {chembl_id}（编号不存在或已废弃）")
        struct = rec.get("molecule_structures") or {}
        smiles = struct.get("canonical_smiles")
        if not smiles:
            raise ValueError(f"{chembl_id} 无 canonical SMILES（可能为无机/混合物）")
        return {
            "ok": True,
            "chembl_id": chembl_id,
            "pref_name": rec.get("pref_name"),
            "canonical_smiles": smiles,
            "molfile": struct.get("molfile"),
            "molecular_formula": _first_of(struct, "molecular_formula"),
            "source": "ChEMBL",
        }

    # ---- 5. 相似度搜索 ----

    def _chembl_similarity(self, params: dict) -> dict:
        smiles = str(params.get("smiles") or "").strip()
        if not smiles:
            raise ValueError("smiles 不能为空（查询分子 SMILES）")
        similarity = int(params.get("similarity") or 90)
        limit = min(max(int(params.get("limit") or 5), 1), 20)
        if not 0 <= similarity <= 100:
            raise ValueError("similarity 必须在 0-100 之间")
        try:
            hits = list(_client().similarity.filter(smiles=smiles, similarity=similarity)[:limit])
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 相似性检索失败: {e}") from e
        result = [
            {
                "chembl_id": h.get("molecule_chembl_id"),
                "pref_name": h.get("pref_name"),
                "similarity": h.get("similarity"),
            }
            for h in hits
        ]
        return {
            "ok": True,
            "query_smiles": smiles,
            "similarity_threshold": similarity,
            "count": len(result),
            "hits": result,
            "source": "ChEMBL",
        }

    # ---- 6. 批次下载 ----

    def _chembl_batch(self, params: dict) -> dict:
        raw = params.get("chembl_ids") or params.get("chembl_ids_list") or []
        if isinstance(raw, str):
            ids = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        else:
            ids = [str(x).strip() for x in raw if str(x).strip()]
        ids = [x.upper() for x in ids]
        bad = [x for x in ids if not x.startswith("CHEMBL")]
        if not ids:
            raise ValueError("chembl_ids 不能为空（CHEMBL 编号列表，如 ['CHEMBL25','CHEMBL26']）")
        if bad:
            raise ValueError(f"非法 CHEMBL 编号: {bad}（格式应为 CHEMBL 加编号）")
        if len(ids) > 50:
            raise ValueError(f"批次上限 50 个，当前 {len(ids)} 个")
        try:
            nc = _client()
            molecules = []
            for cid in ids:
                rec = nc.molecule.get(cid)
                if not rec:
                    molecules.append({"chembl_id": cid, "pref_name": None, "found": False})
                    continue
                struct = rec.get("molecule_structures") or {}
                molecules.append(
                    {
                        "chembl_id": cid,
                        "found": True,
                        "pref_name": rec.get("pref_name"),
                        "canonical_smiles": struct.get("canonical_smiles"),
                        "molecular_formula": _first_of(rec, "molecular_formula", "molecule_formula"),
                    }
                )
        except AcademicDependencyError:
            raise
        except Exception as e:
            raise _ChEMBLUnavailable(f"ChEMBL 批次下载失败: {e}") from e
        return {
            "ok": True,
            "requested": len(ids),
            "found": sum(1 for m in molecules if m["found"]),
            "molecules": molecules,
            "source": "ChEMBL",
        }
