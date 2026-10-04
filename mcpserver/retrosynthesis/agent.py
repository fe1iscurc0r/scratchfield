"""逆合成路线规划 MCP 封装 · MolecularAI/aizynthfinder (MIT)

把 aizynthfinder（逆合成规划事实标准，MCTS 树搜索，纯 Python CPU 可跑）封装为
陆墨 MCP 工具体系的一个 agent。**木质素高值化上游**：解聚单体（香草醛/阿魏酸
/丁香醛等）的合成路径搜索 + 可购原料检查 + 反应模板回溯。

3 个命令：
  route_search    逆合成路线搜索（SMILES → 路线树）
  stock_check     可购起始原料检查（SMILES → stock 命中）
  template_lookup 反应模板回溯（SMILES → 命中的应用模板）

**模型数据降级（卷169-A.3，不裸抛异常）**：aizynthfinder 需要 policy/target
模型文件与 stock 数据包（`aizynthfinder` 包不含数据——官方 quickstart 从
Zenodo 下载，`aizynthfinder --download` 或
`https://github.com/MolecularAI/aizynthfinder` README 的 Models 节）。
**数据缺失时返回结构化错误**（含获取路径说明），供调用方降级提示。

契约（docs/academic/MODEL_INTERFACE.md 同 chembl 薄桥）：
  返回 {ok: true, ...data, source: "aizynthfinder"}；参数非法抛 ValueError；
  依赖缺失抛 AcademicDependencyError（含 pip install 提示）；
  数据包缺失抛 ModelDataMissingError（结构化，含获取路径）；
  搜索无解返回 {ok: true, routes: []}（空解不是错误）。

边界：独立目录 mcpserver/retrosynthesis/，仅通过 MCP 调度接入，不碰主流程。
模块级 **零硬 import**（aizynthfinder 会连带 rdkit/numpy——卷123 matplotlib
教训），全部函数内延迟 import。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from system.config import logger
except ImportError:  # 独立 pytest 时降级到标准 logging
    logger = logging.getLogger("retrosynthesis")

try:
    from mcpserver.academic.errors import AcademicDependencyError
except ImportError:  # 独立运行/测试时使用本地同形类

    class AcademicDependencyError(RuntimeError):
        def __init__(self, package: str, pip_name: str, extra: str = ""):
            hint = f"{package} 未安装：pip install {pip_name} 后可用"
            if extra:
                hint += f"（{extra}）"
            super().__init__(hint)


class ModelDataMissingError(RuntimeError):
    """aizynthfinder 的模型/stock 数据包缺失（结构化降级，含获取路径）。"""

    def __init__(self, missing: list[str]):
        paths = (
            "官方获取路径：https://github.com/MolecularAI/aizynthfinder#models "
            "→ `aizynthfinder --download`（Zenodo 训练数据 + stock）"
        )
        super().__init__(
            f"aizynthfinder 模型数据缺失：{', '.join(missing)}。{paths}"
        )
        self.missing = missing


AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = AGENT_DIR / "aizynthfinder_config.yml"
DATA_DIRS = [
    AGENT_DIR / "models",
    Path.home() / ".aizynthfinder",
]


def _import_aizynthfinder() -> Any:
    """延迟 import aizynthfinder（缺包 → AcademicDependencyError）。"""
    try:
        from aizynthfinder.aizynthfinder import AiZynthFinder  # type: ignore

        return AiZynthFinder
    except AcademicDependencyError:
        raise
    except Exception as e:  # noqa: BLE001
        raise AcademicDependencyError("aizynthfinder", "aizynthfinder") from e


def _missing_model_data() -> list[str]:
    """探测模型/stock 数据包是否就位（缺什么列什么，全齐返回空列表）。"""
    missing = []
    for d in DATA_DIRS:
        if not d.exists():
            missing.append(f"{d.name}/（目录不存在）")
            continue
        has_policy = any(d.glob("**/*policy*")) or any(d.glob("**/*.onnx"))
        has_stock = any(d.glob("**/*stock*"))
        if not has_policy:
            missing.append(f"{d}/policy 模型文件")
        if not has_stock:
            missing.append(f"{d}/stock 数据")
    if DATA_DIRS and all(not x.startswith("⚠️") for x in []) :  # 占位保持结构
        pass
    return missing


def _make_finder(config_path: Path | None = None) -> Any:
    """构造 AiZynthFinder（数据缺失 → ModelDataMissingError 结构化降级）。"""
    AiZynthFinder = _import_aizynthfinder()
    missing = _missing_model_data()
    if missing:
        raise ModelDataMissingError(missing)
    kw: dict[str, Any] = {}
    cfg = config_path or (DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None)
    if cfg:
        kw["configfile"] = str(cfg)
    try:
        return AiZynthFinder(**kw)
    except Exception as e:  # noqa: BLE001
        # 配置存在但内部路径失效 → 数据缺失的结构化表达
        raise ModelDataMissingError([f"config 加载失败：{str(e)[:120]}"]) from e


class RetrosynthesisAgent:
    """逆合成路线规划 agent（aizynthfinder 薄封装）。"""

    name = "retrosynthesis"

    # ---- 命令 ----

    def route_search(self, smiles: str, n_routes: int = 5) -> dict[str, Any]:
        """逆合成路线搜索：SMILES → 路线树（MCTS，CPU）。"""
        if not smiles or not isinstance(smiles, str):
            raise ValueError("smiles 必须是非空字符串")
        finder = _make_finder()
        finder.target_smiles = smiles
        finder.stock.load_default_stocks() if hasattr(finder.stock, "load_default_stocks") else None
        finder.tree_search()
        routes = finder.routes
        n = max(1, int(n_routes))
        out_routes = []
        for i in range(min(n, len(routes))):
            r = routes[i]
            out_routes.append({
                "route_index": i,
                "score": getattr(r, "score", None),
                "smiles_length": getattr(r, "smiles_length", None),
                "steps": _route_steps(r),
            })
        return {
            "ok": True,
            "target": smiles,
            "n_routes_found": len(routes),
            "routes": out_routes,
            "source": "aizynthfinder",
        }

    def stock_check(self, smiles: str) -> dict[str, Any]:
        """可购起始原料检查：SMILES 是否在 stock 数据库。"""
        if not smiles or not isinstance(smiles, str):
            raise ValueError("smiles 必须是非空字符串")
        finder = _make_finder()
        finder.target_smiles = smiles
        hit = bool(finder.stock[smiles]) if hasattr(finder.stock, "__getitem__") else False
        return {"ok": True, "smiles": smiles, "in_stock": hit, "source": "aizynthfinder"}

    def template_lookup(self, smiles: str) -> dict[str, Any]:
        """反应模板回溯：SMILES 命中的应用模板（走 policy 模板的展开表）。"""
        if not smiles or not isinstance(smiles, str):
            raise ValueError("smiles 必须是非空字符串")
        finder = _make_finder()
        finder.target_smiles = smiles
        try:
            finder.tree_search()
            routes = finder.routes
        except Exception as e:  # noqa: BLE001
            raise ModelDataMissingError([f"模板展开依赖搜索结果：{str(e)[:100]}"]) from e
        templates = []
        if len(routes):
            first = routes[0]
            nodes = getattr(first, "nodes", {})
            for smi, node in list(nodes.items())[:20]:
                for mols, meta in getattr(node, "children", []) or []:
                    tmpl = getattr(meta, "metadata", {}).get("template_code")
                    if tmpl:
                        templates.append({"smiles": smi, "template_hash": tmpl})
        return {"ok": True, "smiles": smiles, "templates": templates[:20],
                "source": "aizynthfinder"}

    # ---- MCP 契约入口 ----

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """MCP 契约入口（manifest `entryPoint` 声明的类必须实现本方法）。

        按 manifest 的 3 个 invocationCommands 分发；统一返回 JSON 字符串。

        **不裸抛**：依赖缺失 / 数据包缺失 / 参数非法一律转成结构化错误
        （`status: error` + `error_type`），与 mcp_manager 的错误口径一致。
        """
        tool = str(tool_call.get("tool_name") or tool_call.get("command") or "").strip()
        try:
            if tool == "route_search":
                res = self.route_search(
                    str(tool_call.get("smiles") or ""),
                    int(tool_call.get("n_routes") or 5),
                )
            elif tool == "stock_check":
                res = self.stock_check(str(tool_call.get("smiles") or ""))
            elif tool == "template_lookup":
                res = self.template_lookup(str(tool_call.get("smiles") or ""))
            else:
                return json.dumps({
                    "status": "error",
                    "error_type": "unknown_tool",
                    "message": f"未知命令: {tool!r}",
                    "available": ["route_search", "stock_check", "template_lookup"],
                }, ensure_ascii=False)
            return json.dumps({"status": "ok", **res}, ensure_ascii=False)
        except ModelDataMissingError as e:
            return json.dumps({
                "status": "error", "error_type": "model_data_missing",
                "message": str(e),
                "hint": "运行 `aizynthfinder --download` 获取 policy/stock 数据包",
            }, ensure_ascii=False)
        except AcademicDependencyError as e:
            return json.dumps({
                "status": "error", "error_type": "dependency_missing",
                "message": str(e),
            }, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            return json.dumps({
                "status": "error", "error_type": "invalid_argument",
                "message": str(e),
            }, ensure_ascii=False)


def _route_steps(route: Any) -> list[dict[str, Any]]:
    """路线树 → 步骤列表（reactants → product 的 SMILES 链）。"""
    steps = []
    for node in getattr(route, "graph", {}).nodes if hasattr(route, "graph") else []:
        pass
    # aizynthfinder 的 Route 接口：actions/molecules 序列化即可读
    try:
        for smi, d in route.to_dict().items():
            steps.append({"smiles": smi, **(d if isinstance(d, dict) else {})})
    except Exception:  # noqa: BLE001
        steps = [{"note": "路线详情序列化降级（aizynthfinder 版本接口差异）"}]
    return steps
