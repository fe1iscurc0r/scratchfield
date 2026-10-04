"""gen_capability_pairs.py — 为存量 manifest 补 `capability_pairs` 标注（卷189-A2）。

背景：卷189-A2 引入 (动词, 宾语域) 能力索引（mcpserver/tool_registry/capability_index.py），
但 54 个存量 manifest 里没有任何二元组声明。本脚本按规则一次性补齐，可重复运行（幂等）。

设计：
- 域（domain）：以「服务」为粒度给默认域（DOMAIN_BY_SERVICE），个别命令覆盖
  （COMMAND_DOMAIN_OVERRIDE）——例如 material_science 同时覆盖材料/文献/相图。
- 动词（verb）：按命令名关键词匹配（VERB_RULES，先匹配者胜）。
- 缺省兜底：域退化为服务默认域，动词退化为 "invoke"（并在报告里列出，便于人工复核）。

用法：
    python tools/gen_capability_pairs.py --preview      # 只打印，不落盘
    python tools/gen_capability_pairs.py --write        # 写入 manifest
    python tools/gen_capability_pairs.py --check        # 校验覆盖（CI 用，缺标注报警）

幂等：已含非空 capability_pairs 的 manifest 默认跳过（--force 可强制重算）。
纯 Python 标准库，零新依赖。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- 服务 → 默认宾语域 ----
DOMAIN_BY_SERVICE: dict[str, str] = {
    "academic": "academic",
    "agent_reach": "agent_reach",
    "chemmcp": "chem_molecule",
    "code_review_graph": "code",
    "context7": "docs",
    "graphify": "code",
    "hamlog_adapter": "hamlog",
    "headroom": "context",
    "llm4decompile": "binary",
    "markitdown": "document",
    "memclaw": "memory",
    "paper_miner": "papers",
    "pdf2md_adapter": "document",
    "rsba1_ic705": "radio",
    "semantic_web": "semantic",
    "vulnclaw": "security",
    "agent_animation": "animation",
    "agent_browser": "browser",
    "cli_anything": "cli",
    "agent_decompile": "binary",
    "agent_frida": "security",
    "game_guide": "game",
    "agent_nuclei": "security",
    "app_launcher": "app",
    "agent_osint": "osint",
    "agent_pentest": "security",
    "agent_runtime": "runtime",
    "agent_sbom": "sbom",
    "screen_vision": "screen",
    "agent_signing": "signing",
    "agent_strix": "security",
    "agent_trivy": "security",
    "agent_waf": "security",
    "weather_time": "weather",
    "antenna_sim": "antenna",
    "bofire": "optimization",
    "chembl": "chem_compound",
    "code_workspace": "code",
    "fault_inject": "fault",
    "firecrawl_adapter": "web",
    "graph_memory_adapter": "memory",
    "material_science": "material",
    "memory_maas": "memory",
    "ptz_service": "antenna",
    "retrosynthesis": "retrosynthesis",
    "rf_brain": "rf_signal",
    "scikit_fingerprints": "chem_molecule",
    "sentinel_intel": "intel",
    "trace_audit": "audit",
    "tts_api": "speech",
    "voice_mcp_bidi": "speech",
    "voice_mcp_minimax": "speech",
    "workflow": "workflow",
    "zotpilot": "papers",
}

# ---- 命令关键词 → 动词（顺序即优先级，先匹配者胜）----
VERB_RULES: list[tuple[tuple[str, ...], str]] = [
    (("search", "query", "find"), "search"),
    (("similar", "compare", "diff"), "compare"),
    (("recommend", "suggest"), "recommend"),
    (("analyze", "analysis", "detect"), "analyze"),
    (("check", "validate", "verify"), "check"),
    (("calc", "compute", "props", "property", "sweep", "solve", "gen_", "generate"),
     "compute"),
    (("convert", "parse", "canonical", "format", "to_md", "to_markdown", "smiles2",
      "compress", "scrape", "enrich"), "convert"),
    (("decompile",), "decode"),
    (("decode",), "decode"),
    (("encode",), "encode"),
    (("fingerprint", "transform", "scaffold"), "compute"),
    (("extract",), "extract"),
    (("ingest", "remember", "capture", "_add", "import", "store"), "ingest"),
    (("write", "save", "update", "annotate", "tell"), "write"),
    (("create", "define", "new_"), "create"),
    (("list", "ls_"), "list"),
    (("status", "health", "stats"), "status"),
    (("build", "index"), "build"),
    (("speak", "say", "tts", "synthesize", "emit", "fuse", "merge"), "emit"),
    (("listen", "record", "look_"), "capture"),
    (("ask", "guide", "explain", "question"), "query"),
    (("move", "set", "start", "stop", "home", "scan", "ptt", "estop",
      "navigate", "click", "type", "launch", "close", "drag", "claim", "done",
      "blocked", "hook"), "control"),
    (("run", "exec", "invoke", "call", "inject", "evaluate"), "exec"),
    (("export",), "export"),
    (("batch",), "batch"),
    (("target", "activity", "structure", "compound", "crystal", "phase",
      "lineage", "timeline", "records", "weather", "forecast", "time",
      "info", "detail", "get_", "read_", "_content"), "lookup"),
    # 中文命令（app_launcher 等）
    (("获取", "列表"), "list"),
    (("启动", "关闭", "切换"), "control"),
    (("查询", "搜索"), "search"),
    (("计算", "仿真"), "compute"),
]

# ---- 命令级「动词+域」精确覆盖（规则猜不准的，在此钉死）----
COMMAND_PAIR_OVERRIDE: dict[str, tuple[str, str]] = {
    # chembl
    "chembl_target": ("lookup", "chem_target"),
    "chembl_activity": ("lookup", "chem_activity"),
    "chembl_structure": ("lookup", "chem_structure"),
    "chembl_similarity": ("compare", "chem_structure"),
    "chembl_batch": ("batch", "chem_compound"),
    "chembl_search_compound": ("search", "chem_compound"),
    # material_science
    "literature_search": ("search", "literature"),
    "formula_query": ("search", "chem_formula"),
    "property_calc": ("compute", "material_property"),
    "phase_diagram": ("compute", "phase_diagram"),
    "crystal_info": ("lookup", "crystal"),
    "thermal_analysis": ("analyze", "thermal"),
    "structure_search": ("search", "material_structure"),
    "synthesis_route": ("search", "synthesis"),
    "compare_materials": ("compare", "material"),
    "recommend_material": ("recommend", "material"),
    # rf_brain
    "analyze_signal": ("analyze", "rf_signal"),
    "generate_and_analyze": ("compute", "rf_signal"),
    "sentinel_ingest": ("ingest", "sentinel"),
    "sentinel_status": ("status", "sentinel"),
    "sentinel_query": ("search", "sentinel"),
    # academic
    "academic_levels": ("list", "academic"),
    "academic_interfaces": ("list", "academic"),
    "coolprop_props": ("compute", "thermophysical"),
    "coolprop_constant": ("lookup", "thermophysical"),
    "chem_parse": ("convert", "chem_formula"),
    "chem_formula": ("convert", "chem_formula"),
    "tespy_check": ("check", "thermal_network"),
    "tespy_solve": ("compute", "thermal_network"),
    "slices_query": ("lookup", "crystal"),
    # graphify
    "graphify_build": ("build", "code"),
    "graphify_import": ("ingest", "code"),
    "graphify_query": ("search", "code"),
    "graphify_path": ("compute", "code"),
    "graphify_explain": ("query", "code"),
    "graphify_status": ("status", "code"),
    # headroom
    "headroom_compress_text": ("convert", "context"),
    "headroom_stats": ("status", "context"),
    # llm4decompile
    "decompile_binary": ("decode", "binary"),
    "pe_metadata": ("lookup", "binary"),
    "decompile_status": ("status", "binary"),
    # firecrawl
    "firecrawl_scrape_to_md": ("convert", "web"),
    "firecrawl_enrich_rss": ("convert", "web"),
    "firecrawl_health": ("status", "web"),
    # workflow
    "board_create": ("create", "workflow_task"),
    "board_claim": ("control", "workflow_task"),
    "board_status": ("status", "workflow_task"),
    "board_list": ("list", "workflow_task"),
    "board_done": ("control", "workflow_task"),
    "board_blocked": ("control", "workflow_task"),
    # memory_maas
    "memory_search": ("search", "memory"),
    "memory_lineage": ("lookup", "memory"),
    "memory_write": ("write", "memory"),
    "memory_status": ("status", "memory"),
    "memory_capture_observation": ("capture", "memory"),
    "memory_add_typed": ("ingest", "memory"),
    # graph_memory_adapter
    "graph_memory_remember": ("ingest", "memory"),
    "graph_memory_recall": ("lookup", "memory"),
    "graph_memory_hook": ("control", "memory"),
    "graph_memory_export": ("export", "memory"),
    "graph_memory_stats": ("status", "memory"),
    # sentinel_intel
    "intel_ingest": ("ingest", "intel"),
    "intel_query": ("search", "intel"),
    "intel_timeline": ("lookup", "intel"),
    # trace_audit
    "audit_records": ("list", "audit"),
    "audit_file": ("lookup", "audit"),
    "run_gate": ("exec", "audit"),
    "list_checklist": ("list", "audit"),
    # antenna_sim
    "gen_model": ("compute", "antenna"),
    "sweep_params": ("compute", "antenna"),
    "sim_run": ("exec", "antenna"),
    "job_status": ("status", "antenna"),
    "analyze_result": ("analyze", "antenna"),
    # ptz_service
    "ptz_move_to": ("control", "antenna_control"),
    "ptz_scan": ("control", "antenna_control"),
    "ptz_home": ("control", "antenna_control"),
    "ptz_status": ("status", "antenna_control"),
    "ptz_stop": ("control", "antenna_control"),
    "ptz_estop": ("control", "antenna_control"),
    # bofire
    "bofire_define_domain": ("create", "optimization"),
    "bofire_ask_candidates": ("query", "optimization"),
    "bofire_tell_results": ("write", "optimization"),
    # code_workspace
    "code_exec": ("exec", "code"),
    "file_read": ("lookup", "code"),
    "file_write": ("write", "code"),
    "file_edit": ("write", "code"),
    "shell_exec": ("exec", "code"),
    "test_run": ("exec", "code"),
    # weather_time
    "today_weather": ("lookup", "weather"),
    "forecast_weather": ("lookup", "weather"),
    "time": ("lookup", "weather"),
    # app_launcher（中文命令）
    "获取应用列表": ("list", "app"),
    "启动应用": ("control", "app"),
    "启动NEKO": ("control", "app"),
    "启动HamLog": ("control", "app"),
    "关闭NEKO": ("control", "app"),
    "关闭HamLog": ("control", "app"),
    # memclaw / voice / tts
    "memclaw_write": ("write", "memory"),
    "memclaw_recall": ("lookup", "memory"),
    "memclaw_list": ("list", "memory"),
    "memclaw_stats": ("status", "memory"),
    "memclaw_status": ("status", "memory"),
    "tts_speak": ("emit", "speech"),
    "tts_list_voices": ("list", "speech"),
    "tts_health": ("status", "speech"),
    "voice_speak": ("emit", "speech"),
    "voice_listen": ("capture", "speech"),
    "voice_status": ("status", "speech"),
    "look_screen": ("capture", "screen"),
    # retrosynthesis
    "route_search": ("search", "retrosynthesis"),
    "stock_check": ("check", "retrosynthesis"),
    "template_lookup": ("lookup", "retrosynthesis"),
    # scikit_fingerprints
    "skfp_fingerprint": ("compute", "chem_molecule"),
    "skfp_similarity_matrix": ("compare", "chem_molecule"),
    "skfp_transform": ("compute", "chem_molecule"),
    "skfp_scaffold": ("compute", "chem_molecule"),
    # chemmcp
    "chemmcp_canonicalize_smiles": ("convert", "chem_molecule"),
    "chemmcp_smiles2formula": ("convert", "chem_formula"),
    "chemmcp_check_molecule": ("check", "chem_molecule"),
    "chemmcp_smiles2cas": ("convert", "chem_molecule"),
    # hamlog
    "hamlog_qso_search": ("search", "hamlog"),
    "hamlog_qsl_debts": ("lookup", "hamlog"),
    "hamlog_qso_add": ("ingest", "hamlog"),
    "hamlog_qsl_update": ("write", "hamlog"),
    "hamlog_card_content": ("lookup", "hamlog"),
    # markitdown / pdf2md
    "convert_to_markdown": ("convert", "document"),
    "pipeline_status": ("status", "document"),
    "pdf2md_convert": ("convert", "document"),
    "pdf2md_batch": ("batch", "document"),
    "pdf2md_status": ("status", "document"),
    # code_review_graph
    "code_review_build_index": ("build", "code"),
    "code_review_detect_changes": ("analyze", "code"),
    "code_review_get_impact_radius": ("lookup", "code"),
    "code_review_query_graph": ("search", "code"),
    "code_review_get_architecture": ("lookup", "code"),
    # paper_miner / zotpilot
    "extract_paper": ("extract", "papers"),
    "query_experiments": ("search", "papers"),
    "paper_miner_status": ("status", "papers"),
    "zotpilot_search": ("search", "papers"),
    "zotpilot_import": ("ingest", "papers"),
    "zotpilot_annotate": ("write", "papers"),
    "zotpilot_status": ("status", "papers"),
    # agent_browser
    "navigate": ("control", "browser"),
    "get_page_state": ("lookup", "browser"),
    "click_element": ("control", "browser"),
    "type_text": ("control", "browser"),
    "extract_content": ("extract", "browser"),
    "execute_task": ("exec", "browser"),
    # cli_anything
    "list_cli_tools": ("list", "cli"),
    "search_capabilities": ("search", "cli"),
    # game_guide
    "ask_guide": ("query", "game"),
    "ask_guide_with_screenshot": ("query", "game"),
    "calculate_damage": ("compute", "game"),
    "get_team_recommendation": ("recommend", "game"),
    # fault_inject / vulnclaw / semantic_web / context7
    "inject": ("exec", "fault"),
    "run_robustness": ("exec", "fault"),
    "list_scenarios": ("list", "fault"),
    "check": ("check", "fault"),
    "vulnclaw_status": ("status", "security"),
    "vulnclaw_invoke": ("exec", "security"),
    "semantic_query": ("search", "semantic"),
    "context7_query_docs": ("search", "docs"),
    # rsba1
    "ic705_read_freq": ("lookup", "radio"),
    "ic705_read_mode": ("lookup", "radio"),
    "ic705_read_smeter": ("lookup", "radio"),
    "ic705_set_freq": ("control", "radio"),
    "ic705_ptt": ("control", "radio"),
    "ic705_get_status": ("status", "radio"),
    # agent_reach
    "agent_reach_status": ("status", "agent_reach"),
    # academic 内置 chembl 分子查询
    "chembl_molecule": ("search", "chem_compound"),
    # agent_animation / agent_browser
    "screenshot": ("capture", "browser"),
    # material_science
    "matchat_chat": ("query", "material"),
    "biopred_predict": ("compute", "material"),
    # memory_maas
    "memory_maintenance": ("manage", "memory"),
    # ptz_service
    "ptz_heartbeat": ("status", "antenna_control"),
    "ptz_memory": ("lookup", "antenna_control"),
    "ptz_track_source": ("control", "antenna_control"),
    "ptz_watchdog": ("monitor", "antenna_control"),
    "ptz_audit": ("list", "antenna_control"),
    "ptz_lora": ("status", "antenna_control"),
    "ptz_arbitration": ("control", "antenna_control"),
    "ptz_config": ("write", "antenna_control"),
    # rf_brain 事件子域
    "spectrum_events.current_interferers": ("lookup", "rf_signal"),
    "spectrum_events.recent_events": ("list", "rf_signal"),
    # workflow
    "event_log": ("list", "workflow"),
}

# ---- 标签型 manifest（capabilities 是字符串数组）后缀 → 动词 ----
LABEL_SUFFIX_VERB: dict[str, str] = {
    "listing": "list", "reading": "read", "detection": "detect",
    "monitoring": "monitor", "checking": "check", "validation": "check",
    "testing": "check", "explanation": "explain", "management": "manage",
    "injection": "inject", "hooking": "hook", "instrumentation": "instrument",
    "scanning": "scan", "analysis": "analyze", "extraction": "extract",
    "generation": "generate", "export": "export", "discovery": "search",
    "bruteforce": "brute", "force": "brute",
}

# ---- capabilities 为 null 的服务：按服务定位给最小能力对（报告标注为「定位推断」）----
NULL_CAPABILITY_FALLBACK: dict[str, list[list[str]]] = {
    "agent_nuclei": [["scan", "vulnerability"]],
    "agent_sbom": [["generate", "sbom"]],
    "agent_decompile": [["decode", "binary"]],
    "agent_osint": [["search", "osint"]],
    "agent_signing": [["sign", "artifact"]],
    "agent_trivy": [["scan", "vulnerability"]],
}

# ---- 命令级域覆盖（服务默认域不够用时）----
COMMAND_DOMAIN_OVERRIDE: dict[str, str] = {
    # material_science 跨多个子域
    "literature_search": "literature",
    "formula_query": "chem_formula",
    "phase_diagram": "phase_diagram",
    "crystal_info": "crystal",
    "thermal_analysis": "thermal",
    "property_calc": "material_property",
    # rf_brain
    "analyze_signal": "rf_signal",
    "generate_and_analyze": "rf_signal",
    "sentinel_ingest": "sentinel",
    "sentinel_status": "sentinel",
    "sentinel_query": "sentinel",
    # chembl
    "chembl_target": "chem_target",
    "chembl_activity": "chem_activity",
    "chembl_structure": "chem_structure",
    "chembl_similarity": "chem_structure",
    "chembl_search_compound": "chem_compound",
    # academic
    "chem_parse": "chem_formula",
    "chem_formula": "chem_formula",
    "crystal_string": "crystal",
    "slices_query": "crystal",
    "tespy_check": "thermal_network",
    "coolprop_props": "thermophysical",
    "coolprop_constant": "thermophysical",
    # workflow
    "board_create": "workflow_task",
    "board_claim": "workflow_task",
    "board_status": "workflow_task",
    "board_list": "workflow_task",
    "board_done": "workflow_task",
    "board_blocked": "workflow_task",
    # ptz_service
    "ptz_move_to": "antenna_control",
    "ptz_scan": "antenna_control",
    "ptz_home": "antenna_control",
    "ptz_stop": "antenna_control",
    "ptz_estop": "antenna_control",
    "ptz_status": "antenna_control",
    # tts / voice
    "tts_speak": "speech",
    "tts_list_voices": "speech",
    "tts_health": "speech",
    "voice_speak": "speech",
    "voice_listen": "speech",
    "voice_status": "speech",
    # screen
    "look_screen": "screen",
}


def guess_verb(command: str) -> str:
    """按关键词表猜动词；无匹配返回 'invoke'（兜底，报告里会列出）。"""
    c = command.lower()
    for keys, verb in VERB_RULES:
        if any(k in c for k in keys):
            return verb
    return "invoke"


def guess_domain(command: str, default_domain: str) -> str:
    return COMMAND_DOMAIN_OVERRIDE.get(command, default_domain)


def label_to_pair(label: str) -> tuple[str, str] | None:
    """标签型能力（如 "process_listing"）→ (动词, 域)：按后缀判动词，其余作域。"""
    parts = str(label).strip().lower().split("_")
    if len(parts) < 2:
        return None
    verb = LABEL_SUFFIX_VERB.get(parts[-1])
    if not verb:
        return None
    domain = "_".join(parts[:-1]) or parts[0]
    return verb, domain


def pairs_for(service: str, manifest: dict) -> list[list[str]]:
    """为单个 manifest 生成去重后的 capability_pairs。"""
    default_domain = DOMAIN_BY_SERVICE.get(service)
    caps = manifest.get("capabilities")

    # ① 标准调用契约：逐命令取 pair（精确覆盖 > 规则推断）
    commands: list[str] = []
    if isinstance(caps, dict):
        for c in caps.get("invocationCommands", []) or []:
            if isinstance(c, dict) and c.get("command"):
                commands.append(str(c["command"]))
    if commands:
        seen: set[tuple[str, str]] = set()
        pairs: list[list[str]] = []
        for cmd in commands:
            pair = COMMAND_PAIR_OVERRIDE.get(cmd)
            if pair is None:
                if default_domain is None:
                    continue
                pair = (guess_verb(cmd), guess_domain(cmd, default_domain))
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append([pair[0], pair[1]])
        if pairs:
            return sorted(pairs)

    # ② 标签型能力数组：从标签后缀推导
    if isinstance(caps, list):
        seen2: set[tuple[str, str]] = set()
        pairs2: list[list[str]] = []
        for label in caps:
            if not isinstance(label, str):
                continue
            pair = label_to_pair(label)
            if pair and pair not in seen2:
                seen2.add(pair)
                pairs2.append([pair[0], pair[1]])
        if pairs2:
            return sorted(pairs2)

    # ③ 无能力自述：按服务定位给最小对（报告标注来源为推断）
    fb = NULL_CAPABILITY_FALLBACK.get(service)
    if fb:
        return [list(p) for p in fb]
    return []


def detect_indent(text: str, default: int = 2) -> int:
    """从 manifest 文本探测缩进宽度（顶层键前的空格数）。"""
    m = re.search(r'\n( +)"', text)
    return len(m.group(1)) if m else default


def insert_field(text: str, pairs: list[list[str]], indent: int) -> str | None:
    """把 capability_pairs 以文本级插入顶层（最小 diff，不重排原文件）。

    定位最后一个行首 `}`（顶层闭合），在其前插入 `,\n<indent>"capability_pairs": [...]`。
    失败（非法结构）返回 None。
    """
    idx = text.rfind("\n}")
    if idx == -1:
        m = list(re.finditer(r"\n\s*\}", text))
        if not m:
            return None
        idx = m[-1].start()
    payload = json.dumps(pairs, ensure_ascii=False)
    return text[:idx] + ",\n" + " " * indent + '"capability_pairs": ' + payload + text[idx:]


def iter_manifests() -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(ROOT.glob("mcpserver/**/agent-manifest.json")):
        out.append((p, json.loads(p.read_text(encoding="utf-8"))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="为 manifest 补 capability_pairs 标注")
    ap.add_argument("--preview", action="store_true", help="只打印，不落盘")
    ap.add_argument("--write", action="store_true", help="写回 manifest")
    ap.add_argument("--check", action="store_true",
                    help="校验覆盖，缺标注则退出码 1")
    ap.add_argument("--force", action="store_true", help="已有标注也重算")
    args = ap.parse_args()

    written, skipped, unannotatable, fallback = 0, 0, [], []
    for path, manifest in iter_manifests():
        service = manifest.get("name") or path.parent.name
        if service not in DOMAIN_BY_SERVICE:
            unannotatable.append(service)
            continue
        if manifest.get("capability_pairs") and not args.force:
            skipped += 1
            if args.preview:
                print(f"[keep] {service:24s} {manifest['capability_pairs']}")
            continue
        pairs = pairs_for(service, manifest)
        if not pairs:
            unannotatable.append(service)
            continue
        if any(v == "invoke" for v, _ in pairs):
            fallback.append(service)
        if args.preview or (not args.write and not args.check):
            print(f"[gen ] {service:24s} {pairs}")
        if args.write:
            text = path.read_text(encoding="utf-8")
            new_text = insert_field(text, pairs, detect_indent(text))
            if new_text is None:
                print(f"[warn] {service}: 顶层结构定位失败，跳过")
                continue
            path.write_text(new_text, encoding="utf-8")
            written += 1

    print(f"\n{'=' * 60}")
    print(f"written={written} skipped={skipped} "
          f"unannotatable={len(unannotatable)} verb=invoke 兜底={len(fallback)}")
    if unannotatable:
        print("无可标注（无调用契约/未登记域）:", ", ".join(unannotatable))
    if fallback:
        print("动词兜底为 invoke（建议人工复核）:", ", ".join(fallback))

    if args.check:
        missing = []
        for p, m in iter_manifests():
            svc = m.get("name") or p.parent.name
            if svc in DOMAIN_BY_SERVICE and not m.get("capability_pairs"):
                missing.append(svc)
        if missing:
            print("✗ 缺 capability_pairs 标注:", ", ".join(missing))
            return 1
        print("✓ 全部可标注 manifest 均有 capability_pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
