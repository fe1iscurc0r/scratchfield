"""ChemMCP SMILES 纯转换工具适配层（材料知识库分子检索层 · 结构规范化）。

上游: OSU-NLP-Group/ChemMCP（Apache-2.0），本机 clone: github_haul/ChemMCP/。
授粉范围（工单 04-01 铁律：只收纯转换工具，不搬 BBBB/HIV 等药物性质预测模型）：
- smiles_canonicalization ← src/chemmcp/tools/smiles_canonicalization.py
- smiles2cas              ← src/chemmcp/tools/smiles2cas.py（PubChem 在线查询）
- smiles2formula          ← src/chemmcp/tools/smiles2formula.py
- molecule_smiles_check   ← src/chemmcp/tools/molecule_smiles_check.py
辅助函数 is_smiles ← src/chemmcp/tool_utils/smiles.py；CAS 解析段逻辑
← src/chemmcp/tool_utils/names.py:pubchem_smiles2cas（均 Apache-2.0，来源声明保留）。

与上游的实现差异（诚实标注）：
- 规范化：上游 canonicalize2（LlaSMol/MIT 衍生）用 rdchiral.copy_chirality 做
  手性保持的深度拷贝规范化；本仓为免引 rdchiral 重依赖，改用 RDKit 标准
  MolToSmiles 规范化，isomeric/kekulization/keep_atom_map 三参数语义对齐上游，
  多组分沿用上游默认 sort_things=True 排序。常规生物质分子（木质素单体/二聚体、
  无原子映射的复杂手性场景）输出与上游一致；极端手性/原子映射组合可能有别。
- 上游对非法输入抛 ChemMCPInputError；本仓照 context7.py 惯例一律降级为
  {"ok": False, "error": ...}，绝不抛错（分子检索失败只是查不到，不该中断主流程）。
- smiles2cas 的 PubChem 访问用 stdlib urllib（上游用 requests），零第三方依赖；
  API 基址可用环境变量 CHEMMCP_PUBCHEM_BASE 覆盖（测试/代理场景）。

双模式接入（与 fastmcp 惯例一致）：
- Python import：直接调 *_impl 同步函数（数据处理路径，无需起 MCP server）
- MCP：register() 把 4 个 async 包装挂上 FastMCP add_tool（agent 路径）
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

from mcpserver.adapters._common import register_capability_safe

logger = logging.getLogger(__name__)

CAPABILITY: dict = {
    "name": "chemmcp",
    "displayName": "ChemMCP SMILES 纯转换工具",
    "description": "SMILES 规范化/分子式/CAS 号/合法性检查四件纯转换工具（材料知识库分子检索层的结构规范化底座）。",
    "version": "0.1.0",
    "license": "Apache-2.0",
    "vendor": "OSU-NLP-Group/ChemMCP",
    "degradation_mode": "fail-to-ok-false-never-raise",
    "_from_adapter": "chemmcp",
}

# PubChem 单段请求超时；可被环境变量覆盖（测试/弱网场景），照 context7 的 CONTEXT7_TIMEOUT_S 惯例
_REQUEST_TIMEOUT_S = 5.0

_RDKIT_MISSING_MSG = "rdkit 未安装：pip install rdkit 后可用（ChemMCP 纯转换工具依赖 RDKit，缺失自动降级）"


def _pubchem_base() -> str:
    """PubChem API 基址（默认官方端点，环境变量 CHEMMCP_PUBCHEM_BASE 可覆盖）。"""
    return os.environ.get("CHEMMCP_PUBCHEM_BASE", "https://pubchem.ncbi.nlm.nih.gov").rstrip("/")


def _request_timeout() -> float:
    """单段请求超时（环境变量 CHEMMCP_PUBCHEM_TIMEOUT_S 可覆盖，测试用）。"""
    try:
        return max(0.5, float(os.environ.get("CHEMMCP_PUBCHEM_TIMEOUT_S", _REQUEST_TIMEOUT_S)))
    except ValueError:
        return _REQUEST_TIMEOUT_S


def _fail(tool: str, error: str) -> dict[str, Any]:
    """统一降级返回形状：ok=False + error，绝不抛错。"""
    return {"ok": False, "tool": tool, "error": error}


def _load_rdkit():
    """惰性加载 RDKit，返回 (Chem, rdMolDescriptors)；未安装返回 None。

    不做缓存：import 本身被 sys.modules 缓存，重复调用零开销；不缓存便于测试模拟缺失。
    """
    try:
        import rdkit.Chem.rdMolDescriptors as rdMolDescriptors
        from rdkit import Chem

        return Chem, rdMolDescriptors
    except Exception:
        return None


def _is_smiles(chem: Any, text: Any) -> bool:
    """判定字符串是否为合法分子 SMILES。

    移植自 ChemMCP src/chemmcp/tool_utils/smiles.py:is_smiles（Apache-2.0），
    裸 except 收窄为 Exception 防 KeyboardInterrupt 吞噬。
    """
    try:
        return chem.MolFromSmiles(text, sanitize=True) is not None
    except Exception:
        return False


def smiles_canonicalization_impl(
    smiles: str, isomeric: bool = True, kekulization: bool = True, keep_atom_map: bool = True
) -> dict[str, Any]:
    """SMILES 规范化（同步实现）：任意写法 → canonical SMILES。

    参数语义对齐上游 smiles_canonicalization.py：
    - isomeric: 保留立体/同位素信息（上游默认 True）
    - kekulization: 输出 kekulé 形式，芳香键写成交替单双键（上游默认 True）
    - keep_atom_map: 保留原子映射编号（上游默认 True）
    多组分（"." 分隔）各片段规范化后按上游默认 sort_things=True 排序拼接。

    Returns:
        {"ok": True, "canonical_smiles": ...}；无效输入/RDKit 缺失 → {"ok": False, "error": ...}
    """
    loaded = _load_rdkit()
    if loaded is None:
        return _fail("smiles_canonicalization", _RDKIT_MISSING_MSG)
    chem, _ = loaded
    if not isinstance(smiles, str) or not smiles.strip():
        return _fail("smiles_canonicalization", "输入必须是非空 SMILES 字符串")
    try:
        out_parts: list[str] = []
        for part in smiles.split("."):
            mol = chem.MolFromSmiles(part)
            if mol is None:
                return _fail("smiles_canonicalization", f"无效 SMILES 片段: {part!r}")
            if not keep_atom_map:
                for atom in mol.GetAtoms():
                    atom.SetAtomMapNum(0)
            out = chem.MolToSmiles(mol, isomericSmiles=bool(isomeric), kekuleSmiles=bool(kekulization))
            out_parts.append(out)
        out_parts.sort()  # 上游 canonicalize_molecule_smiles 默认 sort_things=True
        return {
            "ok": True,
            "tool": "smiles_canonicalization",
            "input": smiles,
            "canonical_smiles": ".".join(out_parts),
        }
    except Exception as e:
        logger.info("[adapter:chemmcp] smiles_canonicalization 降级（input=%r）: %s", smiles, e)
        return _fail("smiles_canonicalization", str(e) or type(e).__name__)


def smiles2formula_impl(smiles: str) -> dict[str, Any]:
    """SMILES → 分子式（同步实现），Hill 序（C→H→其余字母序），如 CCO → C2H6O。

    上游经 rdMolDescriptors.CalcMolFormula 计数原子；本仓同一 RDKit 原语。
    """
    loaded = _load_rdkit()
    if loaded is None:
        return _fail("smiles2formula", _RDKIT_MISSING_MSG)
    chem, rd_mol_descriptors = loaded
    if not isinstance(smiles, str) or not smiles.strip():
        return _fail("smiles2formula", "输入必须是非空 SMILES 字符串")
    try:
        mol = chem.MolFromSmiles(smiles)
        if mol is None:
            return _fail("smiles2formula", f"无效 SMILES: {smiles!r}")
        return {
            "ok": True,
            "tool": "smiles2formula",
            "input": smiles,
            "formula": rd_mol_descriptors.CalcMolFormula(mol),
        }
    except Exception as e:
        logger.info("[adapter:chemmcp] smiles2formula 降级（input=%r）: %s", smiles, e)
        return _fail("smiles2formula", str(e) or type(e).__name__)


def molecule_smiles_check_impl(smiles: str) -> dict[str, Any]:
    """分子 SMILES 合法性检查（同步实现）。

    上游 molecule_smiles_check.py 语义：含 ">" 视为反应 SMILES/SMARTS 报错（本仓
    改为降级返回，不抛错）；result 文本沿用上游原句便于对照。
    """
    loaded = _load_rdkit()
    if loaded is None:
        return _fail("molecule_smiles_check", _RDKIT_MISSING_MSG)
    chem, _ = loaded
    if not isinstance(smiles, str) or not smiles.strip():
        return _fail("molecule_smiles_check", "输入必须是非空 SMILES 字符串")
    if ">" in smiles:
        return _fail(
            "molecule_smiles_check",
            '输入包含 ">"，疑似反应 SMILES/SMARTS 而非分子 SMILES（本工具只查分子）',
        )
    valid = _is_smiles(chem, smiles)
    return {
        "ok": True,
        "tool": "molecule_smiles_check",
        "input": smiles,
        "valid": valid,
        "result": "The molecular SMILES string is valid."
        if valid
        else "The molecular SMILES string is invalid.",
    }


def _http_get_json(url: str, timeout: float) -> Any:
    """GET 并解析 JSON。任何网络层异常向上抛，由 smiles2cas_impl 统一降级。"""
    req = urllib.request.Request(
        url, headers={"User-Agent": "scratchpad-mcp-chemmcp-adapter/0.1", "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _pubchem_cas(data: Any) -> str:
    """从 PUG_VIEW 响应提取 CAS 号，段结构对齐上游 pubchem_smiles2cas。

    Names and Identifiers → Other Identifiers → CAS → StringWithMarkup[0].String。
    找不到返回空串（调用方据此降级）。
    """
    try:
        for section in data["Record"]["Section"]:
            if section.get("TOCHeading") == "Names and Identifiers":
                for subsection in section["Section"]:
                    if subsection.get("TOCHeading") == "Other Identifiers":
                        for subsubsection in subsection["Section"]:
                            if subsubsection.get("TOCHeading") == "CAS":
                                return subsubsection["Information"][0]["Value"]["StringWithMarkup"][0][
                                    "String"
                                ]
    except (KeyError, IndexError, TypeError):
        return ""
    return ""


def smiles2cas_impl(smiles: str) -> dict[str, Any]:
    """SMILES → CAS 号（同步实现，PubChem 在线查询）。

    照上游 smiles2cas.py：先本地 is_smiles 校验再联网；两步 REST
    （SMILES→CID→PUG_VIEW 取 CAS）。网络失败/无记录一律降级 ok=False 不抛错。
    """
    loaded = _load_rdkit()
    if loaded is None:
        return _fail("smiles2cas", _RDKIT_MISSING_MSG)
    chem, _ = loaded
    if not isinstance(smiles, str) or not smiles.strip():
        return _fail("smiles2cas", "输入必须是非空 SMILES 字符串")
    if not _is_smiles(chem, smiles):
        return _fail("smiles2cas", f"输入不是有效 SMILES: {smiles!r}")
    timeout = _request_timeout()
    try:
        # 第一步：SMILES → CID（SMILES 经 URL 编码；上游 requests 未显式编码，本仓显式 quote 更稳）
        cid_url = f"{_pubchem_base()}/rest/pug/compound/smiles/{urllib.parse.quote(smiles, safe='')}/cids/JSON"
        cid = _http_get_json(cid_url, timeout)["IdentifierList"]["CID"][0]
        # 第二步：CID → PUG_VIEW 全量记录 → 取 CAS 段
        view_url = f"{_pubchem_base()}/rest/pug_view/data/compound/{cid}/JSON"
        cas = _pubchem_cas(_http_get_json(view_url, timeout))
    except Exception as e:
        logger.info("[adapter:chemmcp] smiles2cas 降级（input=%r）: %s", smiles, e)
        return _fail("smiles2cas", f"PubChem 查询失败: {e}")
    if not cas:
        return _fail("smiles2cas", "PubChem 无该分子的 CAS 记录（或响应缺 CAS 段）")
    return {"ok": True, "tool": "smiles2cas", "input": smiles, "cas": cas}


# ---------------------------------------------------------------------------
# MCP 面：async 包装（fastmcp 由签名 + docstring 自动生成 schema），照 context7 惯例
# ---------------------------------------------------------------------------


async def chemmcp_canonicalize_smiles(
    smiles: str,
    isomeric: bool = True,
    kekulization: bool = True,
    keep_atom_map: bool = True,
) -> dict[str, Any]:
    """SMILES 规范化：任意写法 → canonical SMILES（材料分子入库前的标准形态）。

    Args:
        smiles: 分子 SMILES 字符串，如 "C(O)C"；多组分用 "." 连接
        isomeric: 是否保留立体/同位素信息，默认 True
        kekulization: 是否输出 kekulé 形式（芳香键写成交替单双键），默认 True
        keep_atom_map: 是否保留原子映射编号，默认 True

    Returns:
        {"ok": True, "canonical_smiles": "..."}；无效输入/RDKit 缺失 →
        {"ok": False, "error": 原因}（永不抛错）
    """
    return smiles_canonicalization_impl(smiles, isomeric, kekulization, keep_atom_map)


async def chemmcp_smiles2formula(smiles: str) -> dict[str, Any]:
    """SMILES → 分子式（Hill 序），如 CCO → C2H6O。

    Args:
        smiles: 分子 SMILES 字符串

    Returns:
        {"ok": True, "formula": "..."}；无效输入/RDKit 缺失 → {"ok": False, "error": 原因}
    """
    return smiles2formula_impl(smiles)


async def chemmcp_check_molecule_smiles(smiles: str) -> dict[str, Any]:
    """检查分子 SMILES 字符串的语法合法性。

    Args:
        smiles: 待检查的 SMILES 字符串

    Returns:
        {"ok": True, "valid": bool, "result": 上游原文描述}；含 ">"（反应式）→
        {"ok": False, "error": 原因}；RDKit 缺失 → {"ok": False, "error": 原因}
    """
    return molecule_smiles_check_impl(smiles)


async def chemmcp_smiles2cas(smiles: str) -> dict[str, Any]:
    """SMILES → CAS 号（PubChem 在线查询，需联网）。

    Args:
        smiles: 分子 SMILES 字符串，如 "CCO"（乙醇 → 64-17-5）

    Returns:
        {"ok": True, "cas": "..."}；无网络/无记录/无效输入 → {"ok": False, "error": 原因}
    """
    return smiles2cas_impl(smiles)


def healthcheck() -> bool:
    """恒可用：模块 import 零依赖（RDKit/网络都是调用期才需要，缺失走降级不抛错）。

    与 context7 同理——若这里因 RDKit 缺失返回 False，adapter 会被注册门禁整卡
    跳过，连"工具存在但返回安装提示"的降级面都没有了；故恒 True，缺依赖在
    调用时暴露。
    """
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册 4 个 chemmcp_* 工具 + 登记能力卡片（manifest 含 license 字段）。"""
    tools = [
        (chemmcp_canonicalize_smiles, "chemmcp_canonicalize_smiles"),
        (chemmcp_smiles2formula, "chemmcp_smiles2formula"),
        (chemmcp_check_molecule_smiles, "chemmcp_check_molecule_smiles"),
        (chemmcp_smiles2cas, "chemmcp_smiles2cas"),
    ]
    if hasattr(mcp_server, "add_tool"):
        for fn, name in tools:
            mcp_server.add_tool(fn, name=name)
    else:
        logger.warning("[adapter:chemmcp] mcp_server 无 add_tool，工具未挂载（能力卡仍登记）")
    register_capability_safe(mcp_registry, dict(CAPABILITY))
