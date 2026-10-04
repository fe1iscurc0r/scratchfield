"""split_extensions.py — 把 apiserver/routes/extensions.py 按域拆到 extensions_parts/（卷190-A1）。

纯搬移：块内容逐字节搬运，不改逻辑/签名/文案。

块边界用 AST 精确计算（`ast.parse` → 顶层节点 lineno/end_lineno）——
**不能用"行首无缩进"判断**：文件里有多行字符串（如技能 frontmatter 模板）含行首无缩进的文本，
会被误判为顶层定义。

归属策略：以「路径前缀」为准（/openclaw → openclaw.py，/mcp → mcp.py …），
helper 按其服务对象归属；公共件（路径常量、`_run_command`、遥测）入 common.py。

用法：
    .venv/Scripts/python.exe tools/split_extensions.py --check    # 只报告块→模块映射
    .venv/Scripts/python.exe tools/split_extensions.py --write    # 生成 extensions_parts/ + 薄壳
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "apiserver" / "routes" / "extensions.py"
OUT_DIR = ROOT / "apiserver" / "routes" / "extensions_parts"

# ---- 块名 → 目标模块 ----
MODULE_OF: dict[str, str] = {}

# common：公共常量 + 公共 helper
for n in [
    "logger",
    "OPENCLAW_STATE_DIR", "OPENCLAW_SKILLS_DIR", "OPENCLAW_CONFIG_PATH",
    "NAGA_DATA_DIR", "NAGA_SKILLS_DIR", "NAGA_PUBLIC_SKILLS_DIR", "NAGA_CACHE_SKILLS_DIR",
    "NAGA_AGENTS_DIR", "NAGA_AGENTS_MANIFEST_PATH", "SKILLS_TEMPLATE_DIR",
    "MCPORTER_DIR", "MCPORTER_CONFIG_PATH", "LEGACY_MCPORTER_DIR", "LEGACY_MCPORTER_CONFIG_PATH",
    "SKILL_FRONTMATTER_PATTERN", "MAX_SKILL_NAME_LENGTH",
    "_run_command", "_download_text", "_telemetry_config_keys", "_emit_extensions_telemetry",
    "_init_dirs",
]:
    MODULE_OF[n] = "common"

# openclaw：/openclaw/* + agent_browser 运行时 + 市场清单常量
for n in [
    "MARKET_ITEMS",
    "_agent_browser_bin_name", "_resolve_packaged_openclaw_runtime_dir",
    "_resolve_prebundled_agent_browser_cmd", "_agent_browser_browser_cache_dirs",
    "_has_agent_browser_native_bundle", "_has_agent_browser_browser_cache",
    "_remove_agent_browser_browser_cache", "_install_agent_browser",
    "list_openclaw_market_items", "openclaw_gateway_status_proxy",
    "openclaw_gateway_start_proxy", "openclaw_gateway_stop_proxy",
    "install_openclaw_market_item", "api_openclaw_list_tasks", "api_openclaw_get_task",
]:
    MODULE_OF[n] = "openclaw"

# mcp：/mcp/* + mcporter 存储 + 清单/装配
for n in [
    "_update_mcporter_firecrawl_config", "_ensure_mcporter_storage",
    "_load_mcporter_config", "_normalize_mcp_scope", "_resolve_agent_name",
    "_attach_mcp_meta", "_list_public_enabled_external_mcp_names",
    "_refresh_mcp_runtime_state", "_check_agent_available",
    "_config_json_path", "_iter_builtin_manifests", "_is_builtin_agent_name",
    "_ASSEMBLY_VOCABULARY",
    "get_mcp_assembly", "update_mcp_assembly", "get_mcp_status_offline",
    "get_mcp_tasks_offline", "get_mcp_services", "McpImportRequest",
    "import_mcp_config", "update_mcp_service", "delete_mcp_service",
]:
    MODULE_OF[n] = "mcp"

# skills：/skills/* + 技能文件读写/目录解析/目录清单
for n in [
    "_write_skill_file", "_normalize_skill_name", "_resolve_child_dir",
    "_resolve_skill_dir", "_resolve_agent_skills_dir", "_write_skill_file_to_dir",
    "_load_agents_manifest", "_get_agent_record", "_parse_skill_summary",
    "_list_skill_dir", "_copy_template_dir",
    "SkillImportRequest", "SkillCloneRequest",
    "_render_skill_file_content", "_write_skill_to_scope", "_delete_skill_from_scope",
    "_read_skill_content_from_scope", "_build_skill_catalog",
    "list_skill_catalog", "import_custom_skill", "clone_skill", "delete_skill",
]:
    MODULE_OF[n] = "skills"

# market：/hub/*（安装）+ hub/mcpso/clawhub 解析与安装实现 + 市场项构造
for n in [
    "HubInstallRequest", "_hub_base_url", "_build_hub_url",
    "_resolve_skillhub_cli", "_resolve_skillhub_python", "_resolve_clawhub_runtime",
    "_normalize_mcpso_name", "_resolve_mcpso_url",
    "_extract_json_code_blocks_from_html", "_strip_json_line_comments",
    "_parse_mcp_install_payload", "_install_mcp_via_mcpso",
    "_install_skill_via_tencent_skillhub", "_install_skill_via_clawhub",
    "_fetch_hub_payload", "_parse_hub_skill_payload", "_parse_hub_mcp_payload",
    "_build_market_item", "_get_market_items_status",
    "install_skill_from_hub", "install_mcp_from_hub",
]:
    MODULE_OF[n] = "market"

# upload / travel / memory / search
for n in ["upload_document", "upload_parse"]:
    MODULE_OF[n] = "upload"
for n in [
    "_create_travel_session_and_dispatch", "_cancel_travel_session",
    "create_travel_session", "list_travel_sessions", "get_travel_session",
    "get_travel_session_report", "get_travel_session_history", "stop_travel_session",
    "update_travel_browser_settings", "send_travel_instruction",
    "travel_start", "travel_status", "travel_stop", "travel_history", "travel_history_detail",
]:
    MODULE_OF[n] = "travel"
for n in [
    "_normalize_memory_quintuple_item", "get_memory_stats", "_quintuple_degree",
    "_apply_quintuple_filters", "_fetch_all_quintuples", "get_quintuples",
    "graph_summary", "search_quintuples",
]:
    MODULE_OF[n] = "memory"
MODULE_OF["proxy_search"] = "search"

MODULE_TITLES = {
    "common": "公共件（路径常量 / 子进程 / 遥测）",
    "openclaw": "OpenClaw 网关、任务与 agent_browser 运行时",
    "mcp": "MCP 服务清单、装配策略与 mcporter 存储",
    "skills": "技能目录、导入、克隆与删除",
    "market": "Hub / mcporter.so / clawhub 安装与市场项",
    "upload": "文件上传与解析",
    "travel": "旅行会话（/travel 全家桶）",
    "memory": "记忆五元组与图谱",
    "search": "搜索代理",
}


def _is_docstring(node) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def parse_blocks(src: str):
    """返回 (header_text, [(name, text, start, end)]) —— 后向归属（注释归下一块）。

    - header = 模块 docstring + 连续的 import 区（到第一个真正的定义/语句为止）
    - 顶层 `for` 循环按位置命名 `_init_dirs`（用于目录初始化）
    """
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    body = list(tree.body)

    def _skip(n) -> bool:
        return isinstance(n, (ast.Import, ast.ImportFrom)) or _is_docstring(n)

    first_real = next((n for n in body if not _skip(n)), None)
    header_end = (first_real.lineno - 1) if first_real else len(lines)
    header = "".join(lines[:header_end])

    blocks = []
    prev_end = header_end
    for node in body:
        if _skip(node):
            continue  # docstring / import 已在 header
        name = getattr(node, "name", None)
        if name is None:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
            elif isinstance(node, ast.For):
                name = "_init_dirs"
            else:
                name = f"<{type(node).__name__}@{node.lineno}>"
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(d.lineno for d in node.decorator_list)
        end = node.end_lineno
        text = "".join(lines[prev_end:end])
        blocks.append((name, text, start, end))
        prev_end = end
    return header, blocks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    src = SRC.read_text(encoding="utf-8")
    header, blocks = parse_blocks(src)

    # 保护：源文件必须是"巨石"形态。若已被拆成薄壳（块数极少），继续跑会把包清空。
    if len(blocks) < 50:
        print(f"✗ 源文件只有 {len(blocks)} 个顶层块（预期 >50）——"
              f"很可能 extensions.py 已是薄壳。请先 `git checkout HEAD -- {SRC.relative_to(ROOT)}`",
              file=sys.stderr)
        return 2

    groups: dict[str, list] = {}
    unmapped = []
    for name, text, s, e in blocks:
        if name == "router":
            continue                     # 各模块自建 router
        mod = MODULE_OF.get(name)
        if mod is None:
            unmapped.append((name, s, e))
            continue
        groups.setdefault(mod, []).append((name, text, s, e))

    print(f"源文件 {len(src.splitlines())} 行 | 顶层块 {len(blocks)} | 已映射 {sum(len(v) for v in groups.values())}")
    for mod in sorted(groups):
        names = [n for n, _, _, _ in groups[mod]]
        lines = sum(t.count("\n") for _, t, _, _ in groups[mod])
        print(f"  {mod:9s} {len(names):3d} 块 / ~{lines:5d} 行")
    if unmapped:
        print("\n⚠️ 未映射（需补 MODULE_OF）：")
        for n, s, e in unmapped:
            print(f"  L{s}-{e}  {n}")
        return 1
    if args.check or not args.write:
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for mod, items in groups.items():
        parts = [
            f'"""{MODULE_TITLES.get(mod, mod)}（卷190-A1：从 extensions.py 纯搬移）。"""\n',
            header.rstrip("\n") + "\n\n",
        ]
        if mod != "common":
            # 注意顺序：必须先 import common 的名字、**再**建本模块 router。
            # 反过来的话 `from .common import *` 会把 common 的 router 覆盖掉本模块的
            # router（实测：9 个子模块共享同一 router 对象 → 路由被重复注册 9 次）。
            parts.append("from .common import *  # noqa: F401,F403\n")
        if mod != "common":
            parts.append("\nrouter = APIRouter()\n")
        for name, text, s, e in items:
            parts.append("\n" + text.rstrip("\n") + "\n")
        (OUT_DIR / f"{mod}.py").write_text("".join(parts), encoding="utf-8")
        print(f"  ✓ {mod}.py")

    # __init__：聚合 router（common 无路由，不参与聚合）
    order = ["openclaw", "mcp", "skills", "market", "upload", "travel", "memory", "search"]
    init = ['"""extensions_parts —— 原 extensions.py 按域拆分后的聚合入口（卷190-A1）。\n\n',
            "路由路径逐字不变：各子 router 自持完整路径，此处只做 include_router 聚合。\n",
            '"""\n\nfrom fastapi import APIRouter\n\n',
            "from . import common  # noqa: E402\n"]
    for m in order:
        if m in groups and m != "common":
            init.append(f"from . import {m}  # noqa: E402\n")
    init.append("\nrouter = APIRouter()\n")
    for m in order:
        if m in groups and m != "common":
            init.append(f"router.include_router({m}.router)\n")
    (OUT_DIR / "__init__.py").write_text("".join(init), encoding="utf-8")
    print("  ✓ __init__.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
