"""`mcpserver.kicad_mcp` 的 MCP 入口（薄编排层，工单245）。

对外只暴露**读**类能力（外加一张上游能力地图），契约形态与
`mcpserver/toolknit_mcp/server.py::ToolknitBridge`、`mcpserver/rf_workflow/server.py::RfWorkflowBridge`
一致：``handle_handoff(task) -> JSON 字符串``，由 `mcpserver/mcp_registry.py` 扫
`agent-manifest.json` 注册。

本模块**不重算**任何解析逻辑 —— 全部转调 `sexpr` / `board` / `schematic` /
`design_check` / `fab_bridge` / `capability_map`。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from . import capability_map as cap
from . import design_check as dc
from . import fab_bridge as fab
from .board import Board
from .schematic import Schematic

logger = logging.getLogger(__name__)


class KicadBridge:
    """KiCAD 离线读取能力的 MCP 入口。"""

    # ---- 工具一：板子概览 ----

    def board_summary(self, board_path: str) -> dict[str, Any]:
        """`.kicad_pcb` 概览：层栈/板框/元件/焊盘/网络/走线/过孔 + 未布线网络数。

        纯离线解析（**不需要装 KiCAD**）。坐标按 KiCAD 6+ 的 mm 口径；
        `version < 20210000` 的旧文件会在返回体里带 `legacy_coords_warning`。
        """
        b = Board.parse(board_path)
        return {"ok": True, "tool": "board_summary", "data": b.summary()}

    # ---- 工具二：布线统计 ----

    def routing_stats(self, board_path: str) -> dict[str, Any]:
        """走线统计：总数 / 总长(mm) / 按层 / **最小线宽** / 线宽直方图。"""
        b = Board.parse(board_path)
        return {"ok": True, "tool": "routing_stats", "data": b.routing_stats()}

    # ---- 工具三：未布线网络 ----

    def unrouted_nets(self, board_path: str) -> dict[str, Any]:
        """有焊盘但**没有任何走线/过孔**的网络 —— 布局布线进度的直接指标。"""
        b = Board.parse(board_path)
        nets = b.unrouted_nets()
        return {"ok": True, "tool": "unrouted_nets",
                "data": {"count": len(nets), "nets": nets}}

    # ---- 工具四：原理图概览 ----

    def schematic_summary(self, sch_path: str) -> dict[str, Any]:
        """`.kicad_sch` 概览：放置器件（引用号/值/封装属性）、库符号数、标签、层次页。

        ⚠️ 只有**带 `lib_id` 的** `symbol` 才是**放置的器件**；`lib_symbols` 里的是库定义
        （实测自上游 canonical 夹具：4 个 symbol 块里 3 个是库定义）。
        """
        s = Schematic.parse(sch_path)
        return {"ok": True, "tool": "schematic_summary",
                "data": {**s.summary(), "symbols": [x.as_dict() for x in s.symbols]}}

    # ---- 工具五：原理图↔PCB 对账 ----

    def cross_check(self, sch_path: str, board_path: str) -> dict[str, Any]:
        """对账两侧器件：只在原理图 / 只在 PCB / 值不一致 / 封装不一致。

        「AI 改板前先确认两侧对齐」用这个 —— 不对齐时任何自动化都在错误前提上干活。
        """
        s = Schematic.parse(sch_path)
        b = Board.parse(board_path)
        res = dc.cross_check(s, b)
        return {"ok": True, "tool": "cross_check", "data": res.as_dict()}

    # ---- 工具六：布局快照 ----

    def placement_report(self, board_path: str) -> dict[str, Any]:
        """布局快照：器件总数 / 在板框外的 / 在底层的 / 未定位的。"""
        b = Board.parse(board_path)
        return {"ok": True, "tool": "placement_report", "data": dc.placement_report(b)}

    # ---- 工具七：嘉立创制造前预检 ----

    def fab_precheck(self, board_path: str, rules: dict | None = None) -> dict[str, Any]:
        """制造前预检：由板子推出工艺下限，与 rule set 比对给出 pass/warn/fail。

        ⚠️ 默认阈值为**本仓保守预设**，不是嘉立创官方规格抓取（返回体的
        ``ruleset.source`` 会原样说明）。要对接真实工艺，传 ``rules`` 注入当期货期参数。
        """
        b = Board.parse(board_path)
        rs = fab.RuleSet.from_dict(rules) if rules else None
        res = fab.precheck(b, rs)
        return {"ok": True, "tool": "fab_precheck", "data": res.as_dict()}

    # ---- 工具八：下单摘要 ----

    def fabrication_summary(self, board_path: str) -> dict[str, Any]:
        """下单摘要（尺寸/层数/板厚/最小线宽/最小孔径/器件数/未布线网络）。"""
        b = Board.parse(board_path)
        return {"ok": True, "tool": "fabrication_summary",
                "data": fab.fabrication_summary(b)}

    # ---- 工具九：上游能力地图 ----

    def upstream_capabilities(self, query: str = "", category: str = "") -> dict[str, Any]:
        """上游 `KiCAD-MCP-Server` 的能力地图（17 类别 / 184 已索引工具，MIT）。

        - 给 ``query`` ⇒ 复刻上游 ``searchTools`` 的检索（含「整类命中」与 20 条上限）；
        - 给 ``category`` ⇒ 列该类别全部工具；
        - 都不给 ⇒ 返回统计与出处。
        """
        cmap = cap.default_map()
        out: dict[str, Any] = {"stats": cmap.stats()}
        if category:
            tools = cmap.tools_of(category)
            out["category"] = category
            out["tools"] = tools
            if not tools:
                out["note"] = f"未知类别；可用：{', '.join(cmap.category_names())}"
        if query:
            results = cmap.search(query)
            out["query"] = query
            out["result_count"] = len(results)
            out["results"] = [r.as_dict() for r in results]
            out["limit_note"] = f"上游语义上限 {cap.SEARCH_LIMIT} 条（已保持一致）"
        return {"ok": True, "tool": "upstream_capabilities", "data": out}

    # ---- 工具十：自述 ----

    def doctor(self) -> dict[str, Any]:
        """能力/边界自述（**不需要**任何外部依赖即可回答）。

        「不能做什么」和「能做什么」一样重要 —— 这里把边界写在返回体里，
        避免上层以为本模块能跑 Gerber/DRC（那些要装 KiCAD）。
        """
        return {
            "ok": True,
            "tool": "doctor",
            "module": "mcpserver.kicad_mcp",
            "external_deps": [],
            "requires_kicad": False,
            "can": [
                "读 .kicad_pcb / .kicad_sch（KiCAD 6+ 的 mm 口径）",
                "板子结构统计（层栈/板框/元件/焊盘/网络/走线/过孔）",
                "原理图↔PCB 器件对账（引用号/值/封装）",
                "嘉立创制造前预检（线宽/孔径/环宽/层数/尺寸/板厚）",
                "上游能力地图检索（17 类别 / 184 已索引工具）",
            ],
            "cannot": [
                "**写**回 .kicad_pcb/.kicad_sch（需要 UUID/实例路径完整语义，属上游工具链）",
                "生成 Gerber/钻孔/坐标文件（需要 KiCAD 的 kicad-cli，本机未装）",
                "跑真实 DRC/ERC（同上）",
                "自动布线（上游走 Freerouting，需 Java/Docker）",
            ],
            "notes": [
                "本模块是**离线读取核**，与上游 KiCAD-MCP-Server 是互补关系："
                "上游要 KiCAD 运行时，本模块零依赖但只读。",
                "序列化（sexpr.dumps）是**结构等价**，不保证与 KiCAD 自己的排版逐字节一致。",
            ],
        }

    # ---- 白名单自述 ----

    _TOOLS: dict[str, str] = {
        "board_summary": "board_summary",
        "routing_stats": "routing_stats",
        "unrouted_nets": "unrouted_nets",
        "schematic_summary": "schematic_summary",
        "cross_check": "cross_check",
        "placement_report": "placement_report",
        "fab_precheck": "fab_precheck",
        "fabrication_summary": "fabrication_summary",
        "upstream_capabilities": "upstream_capabilities",
        "doctor": "doctor",
        # ⚠️ list_tools 必须在此表内，否则 handle_handoff 会把它当未知工具
        # （该漏登记由 test_manifest_matches_dispatch_table 盯着）。
        "list_tools": "list_tools",
    }

    def list_tools(self) -> dict[str, Any]:
        """自述白名单（只暴露本 PoC 的工具，避免 LM 工具选择混乱）。"""
        cmap = cap.default_map()
        return {
            "ok": True,
            "tool": "list_tools",
            "count": len(self._TOOLS),
            "tools": sorted(self._TOOLS),
            "upstream_map": cmap.stats(),
            "upstream_gap_note": (
                "上游有 184 个**已索引**工具（含写板/导出/自动布线）；本模块只提供其中的"
                "**离线只读**子集，其余需要 KiCAD 运行时，故意不做（见 doctor.cannot）。"
            ),
        }

    # ---- handoff ----

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 契约入口：``task -> JSON 字符串``（形态对齐 ToolknitBridge）。"""
        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps(
                {"status": "error",
                 "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                 "data": {}}, ensure_ascii=False)

        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_")
                         and k not in ("tool_name", "agentType", "service_name")}

        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[kicad_mcp] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """命令行入口（与 ToolknitBridge 的 CLI 同形，便于人工排障）。"""
    ap = argparse.ArgumentParser(prog="kicad_mcp", description="KiCAD 离线读取核（工单245）")
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("board-summary", help="板子概览")
    p.add_argument("board")
    p = sub.add_parser("routing", help="布线统计")
    p.add_argument("board")
    p = sub.add_parser("unrouted", help="未布线网络")
    p.add_argument("board")
    p = sub.add_parser("sch-summary", help="原理图概览")
    p.add_argument("sch")
    p = sub.add_parser("cross-check", help="原理图↔PCB 对账")
    p.add_argument("sch")
    p.add_argument("board")
    p = sub.add_parser("placement", help="布局快照")
    p.add_argument("board")
    p = sub.add_parser("fab-precheck", help="嘉立创制造前预检")
    p.add_argument("board")
    p = sub.add_parser("fab-summary", help="下单摘要")
    p.add_argument("board")
    p = sub.add_parser("capabilities", help="上游能力地图")
    p.add_argument("--query", default="")
    p.add_argument("--category", default="")
    sub.add_parser("doctor", help="能力/边界自述")
    sub.add_parser("list-tools", help="白名单")
    return ap


def main(argv: list[str] | None = None) -> int:
    """跑一个 CLI 子命令并打印 JSON。"""
    args = build_parser().parse_args(argv)
    bridge = KicadBridge()
    c = args.command
    if c == "board-summary":
        out = bridge.board_summary(args.board)
    elif c == "routing":
        out = bridge.routing_stats(args.board)
    elif c == "unrouted":
        out = bridge.unrouted_nets(args.board)
    elif c == "sch-summary":
        out = bridge.schematic_summary(args.sch)
    elif c == "cross-check":
        out = bridge.cross_check(args.sch, args.board)
    elif c == "placement":
        out = bridge.placement_report(args.board)
    elif c == "fab-precheck":
        out = bridge.fab_precheck(args.board)
    elif c == "fab-summary":
        out = bridge.fabrication_summary(args.board)
    elif c == "capabilities":
        out = bridge.upstream_capabilities(args.query, args.category)
    elif c == "doctor":
        out = bridge.doctor()
    else:
        out = bridge.list_tools()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["KicadBridge", "build_parser", "main"]


def _fixture_dir() -> Path:
    """夹具目录（供外部工具定位沙箱样本）。"""
    return Path(__file__).resolve().parent / "tests" / "fixtures"
