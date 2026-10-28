"""`mcpserver.agentic_inventory` 的 MCP 入口（工单249）。

对外是**只读盘存**：把本仓的 agent 资产变成一张带**置信度 / 证据 / 风险姿态 / 指纹**的表，
并在两份快照之间做 diff（签名变了就报）。契约形态与前几单一致：
``handle_handoff(task) -> JSON 字符串``。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from . import inventory as inv
from . import posture

logger = logging.getLogger(__name__)

#: 默认仓根（本文件在 <repo>/mcpserver/agentic_inventory/ 下）
DEFAULT_ROOT = Path(__file__).resolve().parents[2]


class AgenticInventoryBridge:
    """agent 资产盘存的 MCP 入口。"""

    # ---- 工具一：完整盘存 ----
    def inventory(self, repo_root: str = "", type_filter: str = "") -> dict[str, Any]:
        """跑一次盘存，返回行 + 汇总。`type_filter` 只保留某类行（照上游的约束下推思路）。

        ⚠️ **只读**：不看被盘对象的 import 副作用、不执行任何二进制、不建立任何连接。
        """
        root = Path(repo_root) if repo_root else DEFAULT_ROOT
        data = inv.build_inventory(root)
        if type_filter:
            data["rows"] = [r for r in data["rows"] if r["type"] == type_filter]
            data["summary"]["filtered_by"] = type_filter
            data["summary"]["total_rows"] = len(data["rows"])
        data["repo_root"] = str(root)
        return {"ok": True, "tool": "inventory", "data": data}

    # ---- 工具二：注册表对账缺口 ----
    def registry_gaps(self, repo_root: str = "") -> dict[str, Any]:
        """只出**注册表对账缺口**：entryPoint 静态不可解析 / 声明与派发表不一致。

        这两类缺口分别是 244h（`mod/` 里指向不存在模块的死 manifest）与 244 的教训
        （只把方法写在类上、不登记进 `_TOOLS` ⇒ LM 调不到）的可跑版本。
        """
        root = Path(repo_root) if repo_root else DEFAULT_ROOT
        rows = inv.reconcile(inv.scan_agents(root))
        return {"ok": True, "tool": "registry_gaps",
                "data": {"count": len(rows), "rows": [r.as_dict() for r in rows]}}

    # ---- 工具三：风险报告 ----
    def risk_report(self, repo_root: str = "") -> dict[str, Any]:
        """只出**带风险标记**的行，并附令牌的解释（每条风险都能说清判据）。

        ⚠️ `plaintext_secret` **只报变量名**，绝不把值写进结果 —— 审计工具不能自己成为泄漏源。
        """
        root = Path(repo_root) if repo_root else DEFAULT_ROOT
        data = inv.build_inventory(root)
        rows = [r for r in data["rows"] if r["risk_flags"]]
        flags: dict[str, int] = {}
        for r in rows:
            for f in r["risk_flags"].split(","):
                if f:
                    flags[f] = flags.get(f, 0) + 1
        return {"ok": True, "tool": "risk_report", "data": {
            "flagged_row_count": len(rows),
            "flag_counts": dict(sorted(flags.items())),
            "tokens": {k: posture.RISK_TOKENS.get(k, "(未登记的令牌)") for k in sorted(flags)},
            "rows": [{k: r[k] for k in ("type", "name", "path", "risk_flags")} for r in rows],
        }}

    # ---- 工具四：快照 ----
    def snapshot(self, repo_root: str = "") -> dict[str, Any]:
        """生成可 diff 的快照（名字 → 指纹/置信度/标记）。把输出存下来就能跨时间比对。"""
        root = Path(repo_root) if repo_root else DEFAULT_ROOT
        snap = inv.snapshot(inv.build_inventory(root))
        return {"ok": True, "tool": "snapshot",
                "data": {"repo_root": str(root), "count": len(snap), "snapshot": snap}}

    # ---- 工具五：快照 diff ----
    def diff(self, before: str, after: str) -> dict[str, Any]:
        """两份快照相减：新增 / 消失 / 指纹变化 / **启动向量变化**（rug-pull 候选）。

        `before` / `after` 传 snapshot 工具的 `snapshot` 字段（JSON 字符串）。
        **也收 snapshot 工具的整份输出**（含 `ok`/`tool`/`data`）—— 见 `unwrap_snapshot`。
        """
        b, a = unwrap_snapshot(json.loads(before)), unwrap_snapshot(json.loads(after))
        return {"ok": True, "tool": "diff", "data": inv.diff_snapshots(b, a)}

    # ---- 工具六：表结构自述 ----
    def column_spec(self) -> dict[str, Any]:
        """表结构自述 + **与上游的差异说明**（我们少了 running/pid/port，为什么）。"""
        return {"ok": True, "tool": "column_spec", "data": {
            "columns": list(inv.COLUMNS),
            "types": ["mcp_agent", "instruction_file", "registry_gap"],
            "bands": {
                "catalog": "100 —— manifest + entryPoint 可解析 + 契约齐备",
                "high": "70-99 —— 多信号",
                "medium": "40-69 —— 强形状但契约不完备",
                "low": f"{posture.MIN_EMITTED}-39 —— 边缘（仍出行）",
                "not_emitted": f"<{posture.MIN_EMITTED} —— **不出行**",
            },
            "signal_weights": dict(sorted(posture.SIGNAL_WEIGHTS.items())),
            "diff_from_upstream": {
                "upstream_table": "karmine05/agentic-detector 的 ai_tools（Go，osquery 扩展）",
                "we_dropped": ["running", "pid", "port"],
                "why": ("上游是**主机级**扫描（进程快照 + 监听端口）；本模块是**仓内资产级**扫描 —— "
                        "不碰主机进程、不枚举用户家目录（隐私与纪律），因此这三列对我们没有可信来源。"
                        "宁可不给列，也不给一个靠猜的 running。"),
                "we_added": ["registry_gap 行类型", "quality_flags（工程标记与安全风险分开）"],
                "why_added": ("注册表对账是本仓特有的需求（244g/244h 人工做过）；"
                              "把工程标记与安全风险混在一列会让两者都失去意义。"),
            },
        }}

    # ---- 工具七：自述 ----
    def doctor(self) -> dict[str, Any]:
        """能力与**边界**自述。"""
        return {"ok": True, "tool": "doctor", "module": "mcpserver.agentic_inventory",
                "can": [
                    "盘存仓内 agent 资产（manifest 静态契约信号 → 置信度 + evidence 令牌）",
                    "风险姿态（remote_fetch_exec / unpinned_dependency / cleartext_endpoint / plaintext_secret / injection_markers / hidden_unicode）",
                    "**注册表对账**（entryPoint 能否静态落地、声明与派发表是否一致）",
                    "快照与 diff（sha256 + launch_hash ⇒ 签名变化 / **启动向量变化**）",
                ],
                "cannot": [
                    "**不做主机级扫描**（没有 running/pid/port）—— 那需要进程快照并会碰用户家目录，"
                    "本模块只盘**仓内**资产",
                    "不 import 被盘对象（用 AST 静态读，避免依赖与副作用）",
                    "不执行任何发现的二进制、不连接任何 MCP server 去枚举工具（照上游的 detection-only 纪律）",
                    "**不报密钥的值**（plaintext_secret 只给变量名）",
                ],
                "notes": [
                    "与 244g 守卫的边界：那个是**CI 闸门**（静态、无依赖、只守 manifest 可解析）；"
                    "本模块是**可反复跑的盘存**（任意目录、带置信度/风险/指纹、可跨时间 diff）。",
                    "方法借自 karmine05/agentic-detector（MIT，13★）的 ai_tools 表设计。",
                ]}

    # ---- 白名单 ----
    _TOOLS: dict[str, str] = {
        "inventory": "inventory",
        "registry_gaps": "registry_gaps",
        "risk_report": "risk_report",
        "snapshot": "snapshot",
        "diff": "diff",
        "column_spec": "column_spec",
        "doctor": "doctor",
        # ⚠️ list_tools 必须在此表内（由 test_manifest_commands_match_dispatch_table 盯着）
        "list_tools": "list_tools",
    }

    def list_tools(self) -> dict[str, Any]:
        """自述白名单。"""
        return {"ok": True, "tool": "list_tools", "count": len(self._TOOLS),
                "tools": sorted(self._TOOLS), "types": ["mcp_agent", "instruction_file", "registry_gap"]}

    # ---- handoff ----
    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 契约入口：``task -> JSON 字符串``。"""
        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps({"status": "error",
                               "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                               "data": {}}, ensure_ascii=False)
        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_") and k not in ("tool_name", "agentType", "service_name")}
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[agentic_inventory] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """命令行入口。"""
    ap = argparse.ArgumentParser(prog="agentic_inventory", description="agent 资产盘存（工单249）")
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("inventory", help="完整盘存")
    p.add_argument("--root", default="")
    p.add_argument("--type", default="", help="只保留某类行")
    p = sub.add_parser("gaps", help="注册表对账缺口")
    p.add_argument("--root", default="")
    p = sub.add_parser("risks", help="风险报告")
    p.add_argument("--root", default="")
    p = sub.add_parser("snapshot", help="可 diff 快照")
    p.add_argument("--root", default="")
    p = sub.add_parser("diff", help="两份快照 diff（传 JSON 文本，或 `@文件路径`）")
    p.add_argument("before", help="before 快照 JSON 文本，或 @文件路径")
    p.add_argument("after", help="after 快照 JSON 文本，或 @文件路径")
    sub.add_parser("columns", help="表结构自述")
    sub.add_parser("doctor", help="能力/边界自述")
    return ap


def unwrap_snapshot(obj: dict[str, Any]) -> dict[str, Any]:
    """接受两种形状：snapshot 工具的**整份输出**，或它里面的 `data.snapshot`。

    ⚠️ 为什么不能只收后者：`snapshot` 子命令**写出来的就是整份输出**
    （`{"ok":…,"tool":"snapshot","data":{"snapshot":{…}}}`），而 `diff` 只收内层
    ⇒ 用户必须自己写一行拆壳代码才能把两者接起来（README 旧版就是这么绕的）。
    接不上就会让人**绕开工具**，那比多这 6 行更糟。
    """
    data = obj.get("data") if isinstance(obj, dict) else None
    if isinstance(data, dict) and isinstance(data.get("snapshot"), dict):
        return data["snapshot"]
    return obj


def load_snapshot_arg(raw: str) -> str:
    """`diff` 的入参解析：`@路径` ⇒ 读文件；否则**原样**当 JSON 文本。

    为什么需要这条：真实快照有 24 KB（65 行），Windows 命令行上限约 32 KB
    ⇒ `diff "$(cat a.json)" "$(cat b.json)"` 这类写法**跑不起来**，
    证据就没法在 Windows 上复跑。`@` 前缀是给这个平台的出路（POSIX 上两种写法都能用）。
    """
    if raw.startswith("@"):
        return Path(raw[1:]).read_text(encoding="utf-8")
    return raw


def main(argv: list[str] | None = None) -> int:
    """跑一个 CLI 子命令并打印 JSON。"""
    args = build_parser().parse_args(argv)
    br = AgenticInventoryBridge()
    c = args.command
    if c == "inventory":
        out = br.inventory(args.root, args.type)
    elif c == "gaps":
        out = br.registry_gaps(args.root)
    elif c == "risks":
        out = br.risk_report(args.root)
    elif c == "snapshot":
        out = br.snapshot(args.root)
    elif c == "diff":
        out = br.diff(load_snapshot_arg(args.before), load_snapshot_arg(args.after))
    elif c == "columns":
        out = br.column_spec()
    elif c == "doctor":
        out = br.doctor()
    else:
        out = br.list_tools()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["AgenticInventoryBridge", "build_parser", "main"]
