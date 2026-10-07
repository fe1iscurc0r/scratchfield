"""glyco 糖链信息学工具组实现（工单203 任务二）。

底座（均为许可干净的开源件）：
    - glypy（40★ Apache-2.0）：糖链结构解析 / 质量 / 树遍历
    - glycowork（98★ MIT）：glycan → 功能注释（SweetNet 等）

**实测口径（2026-10-07，本机）**：
    - glypy 的 ``iupac`` 方言**不接受 CFG 简写**（如 ``Man9GlcNAc2``）与常见 condensed 写法，
      实测均抛 ``IUPACError``；**可用路径是 GlycoCT**（``RES/LIN`` 段）——已实测：
      ``Man(a1-3)Man`` 的 GlycoCT 解析得到 2 残基 / 质量 342.1；
    - 因此 ``parse_glycan`` / ``to_tree`` 默认走 GlycoCT；传 IUPAC 时若 glypy 方言不匹配，
      **返回结构化错误并指明方言限制**（不静默降级）。

依赖缺失时一律返回 ``{"status": "degraded", "reason": ...}``，不抛异常（对齐 eis 口径）。
"""
from __future__ import annotations

from typing import Any

#: 支持的输入格式
FORMATS = ("auto", "glycoct", "iupac")


def _load_glypy():
    """延迟导入 glypy（重依赖，避免拖慢总线启动）。"""
    try:
        from glypy.io import glycoct as _gct
        from glypy.io import iupac as _iupac

        return _gct, _iupac, None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"


def _parse(text: str, fmt: str):
    """解析糖链文本 → (glycan, err)。fmt: auto|glycoct|iupac。"""
    gct, iupac, err = _load_glypy()
    if err:
        return None, f"glypy_unavailable: {err}"
    order = ("glycoct", "iupac") if fmt == "auto" else (fmt,)
    errors: list[str] = []
    for f in order:
        try:
            if f == "glycoct":
                return gct.loads(text), None
            if f == "iupac":
                return iupac.loads(text), None
        except Exception as exc:  # noqa: BLE001 - 逐个方言试，收集原因
            errors.append(f"{f}: {type(exc).__name__}: {str(exc)[:80]}")
    return None, "parse_failed → " + " | ".join(errors)


def _residue_brief(res: Any) -> dict[str, Any]:
    """单个残基的容错摘要（glypy 各版本属性名不完全一致，全部 getattr 兜底）。"""
    brief: dict[str, Any] = {}
    for key in ("name", ):
        val = getattr(res, key, None)
        brief[key] = val() if callable(val) else (str(val) if val is not None else None)
    sup = getattr(res, "superclass", None)
    brief["superclass"] = getattr(sup, "name", None) or (str(sup) if sup is not None else None)
    try:
        brief["mass"] = round(float(res.mass()), 3)
    except Exception:  # noqa: BLE001
        brief["mass"] = None
    try:
        brief["children"] = len(list(res.children()))
    except Exception:  # noqa: BLE001
        brief["children"] = None
    if not brief.get("name"):
        brief["name"] = str(res).strip()[:40]
    return brief


def parse_glycan(text: str, fmt: str = "auto") -> dict[str, Any]:
    """解析糖链结构 → 摘要（残基表 / 总数 / 总质量 / 组成统计）。

    ``fmt``: auto（先 GlycoCT 再 IUPAC）/ glycoct / iupac
    """
    if not str(text or "").strip():
        return {"status": "error", "error": "empty_input"}
    if fmt not in FORMATS:
        return {"status": "error", "error": f"unknown_format: {fmt}", "available": list(FORMATS)}
    glycan, err = _parse(str(text), fmt)
    if glycan is None:
        return {
            "status": "error",
            "error": "parse_failed",
            "detail": err,
            "hint": "glypy 的 iupac 方言不接受 CFG 简写（如 Man9GlcNAc2）；请提供 GlycoCT（RES/LIN）文本",
        }
    residues = [_residue_brief(r) for r in glycan]
    composition: dict[str, int] = {}
    for r in residues:
        key = str(r.get("name") or "?")
        composition[key] = composition.get(key, 0) + 1
    try:
        total_mass = round(float(glycan.mass()), 3)
    except Exception:  # noqa: BLE001
        total_mass = None
    return {
        "status": "ok",
        "residue_count": len(residues),
        "total_mass": total_mass,
        "composition": composition,
        "residues": residues,
        "format_used": fmt,
    }


def to_tree(text: str, fmt: str = "auto") -> dict[str, Any]:
    """结构 → 层次树（root 起，逐层 children）。容错：取不到 children 时给扁平表。"""
    parsed = parse_glycan(text, fmt)
    if parsed.get("status") != "ok":
        return parsed
    glycan, _err = _parse(str(text), fmt)
    nodes: list[dict[str, Any]] = []
    try:
        def walk(res: Any, depth: int) -> None:
            node = _residue_brief(res)
            node["depth"] = depth
            nodes.append(node)
            if depth > 32:            # 防御：异常环
                return
            try:
                for child in res.children():
                    walk(child, depth + 1)
            except Exception:         # noqa: BLE001
                pass

        walk(glycan.root, 0)
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "reason": f"tree_walk_failed: {type(exc).__name__}: {exc}",
                "fallback": parsed["residues"]}
    return {
        "status": "ok",
        "node_count": len(nodes),
        "max_depth": max((n["depth"] for n in nodes), default=0),
        "nodes": nodes,
    }


def glytoucan_lookup(accession: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    """按 GlyTouCan accession 查询结构（公共 API；网络不可用时返回 degraded）。"""
    acc = str(accession or "").strip()
    if not acc:
        return {"status": "error", "error": "empty_accession"}
    import urllib.error
    import urllib.request

    url = f"https://api.glycosmos.org/glytoucan/glycans/{acc}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:  # noqa: S310 - 固定官方域名
            import json

            data = json.loads(resp.read().decode("utf-8"))
        return {"status": "ok", "accession": acc, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "accession": acc,
                "reason": f"glytoucan_unreachable: {type(exc).__name__}: {str(exc)[:120]}",
                "url": url}


def annotate_glycan(text: str, fmt: str = "auto") -> dict[str, Any]:
    """glycan → 功能注释（glycowork / SweetNet 路线）。

    glycowork 未安装或缺少模型权重时返回 degraded（含原因与安装指引），不静默降级。
    """
    parsed = parse_glycan(text, fmt)
    if parsed.get("status") != "ok":
        return parsed
    try:
        import glycowork  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "degraded",
            "reason": f"glycowork_unavailable: {type(exc).__name__}: {exc}",
            "install": "uv pip install glycowork（实测不依赖 torch）",
            "residue_count": parsed.get("residue_count"),
        }
    return {
        "status": "degraded",
        "reason": "annotation_model_not_configured",
        "detail": "glycowork 已安装，但本轮未接入其 SweetNet 权重（需模型文件与 GPU 策略定稿）",
        "residue_count": parsed.get("residue_count"),
        "composition": parsed.get("composition"),
    }


TOOLS = ("parse_glycan", "to_tree", "glytoucan_lookup", "annotate_glycan")
