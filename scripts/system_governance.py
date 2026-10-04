#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
system_governance.py — scratchpad 系统自治理层 v1（SPEC-10 骨架）
系统工程学第3章(结构模型) + 第7章(网络计划) 落地：
  --model   系统结构快照：模块/依赖/耦合度/孤岛/环检测 → JSON
  --cpm     关键路径分析：SPEC-01~10 + 工单 → 网络图 → 关键路径
  --pulse   系统脉搏：model + cpm 摘要一行输出（供 cron/早报复用）
用法:
  python3 system_governance.py --model
  python3 system_governance.py --cpm
  python3 system_governance.py --pulse
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SP = Path(__file__).resolve().parents[1]  # 仓库根（scripts/ 上一级），跨平台可运行
SKIP_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', '.venv', 'dist', 'build', 'vault', 'repos', 'vendor'}
TOP_MODS = ['apiserver', 'NEKO', 'mcpserver', 'summer_memory', 'rag', 'tools', 'scripts',
            'coupled', 'agentserver', 'guide_engine', 'system', 'voice', 'research']
OUT_DIR = SP / "data" / "system_pulse"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 孤岛豁免清单（卷175-A）：判「该豁免」而非「该连」——数据产地/边界外插件
# 不强行接总线。--model 输出孤岛时对豁免项标注「(豁免:xxx)」而非裸报。
ISLAND_EXEMPT = {
    'research': '数据产地，CLI 工具集，勿接总线',
}


def scan_modules():
    """扫描模块依赖，区分「模块级硬依赖(真边)」与「函数内延迟导入(假边)」。

    旧实现用 `^\\s*(from|import)` 统计，`\\s*` 会匹配行首缩进，把函数体内的
    `    from system.config import ...` 也算成依赖边 → 凑出若干「假环」。
    这里拆成两类：
      deps      = 行首无缩进的模块级 import（导入即执行，真实依赖，环检测依据）
      lazy_deps = 带缩进的函数内/守卫 import（运行期才触发，静态扫描的假边）
    """
    mods = {}
    for name in TOP_MODS:
        full = SP / name
        if not full.is_dir():
            continue
        py_count, total_lines = 0, 0
        hard_deps, lazy_deps = set(), set()
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if not f.endswith('.py'):
                    continue
                py_count += 1
                p = Path(root) / f
                try:
                    txt = p.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                total_lines += txt.count('\n') + 1
                # 测试文件（test_*.py / *_test.py / conftest.py）为做集成测试会跨层
                # import 多个顶层模块，属测试脚手架而非生产耦合，不计入依赖图，
                # 否则会凑出 mcpserver→tools→scripts→mcpserver 这类假环
                # （与旧实现把函数内延迟导入误判为硬边同类问题）。
                is_test_file = (f.startswith('test_') or f.endswith('_test.py')
                                or f == 'conftest.py')
                if is_test_file:
                    continue
                for m in TOP_MODS:
                    if m == name:
                        continue
                    if re.search(rf'^(from|import)\s+{m}\b', txt, re.M):
                        hard_deps.add(m)          # 模块级硬依赖（行首无缩进）
                    elif re.search(rf'^[ \t]+(from|import)\s+{m}\b', txt, re.M):
                        lazy_deps.add(m)          # 函数内延迟导入（带缩进）
        mods[name] = {
            'py': py_count,
            'lines': total_lines,
            'deps': sorted(hard_deps),            # 真实模块级依赖（环检测用）
            'lazy_deps': sorted(lazy_deps),       # 延迟导入（仅信息，不算环）
        }
    return mods


def _find_cycles(names, dep_graph, limit=5):
    """强连通环检测：只报 ≥3 节点循环（2 节点互引是正常双向依赖，不算病理）。

    遍历按字典序排序，保证输出可复现（否则 set 迭代顺序随进程 hash 种子变化，
    快照/基线对比会对不上）。
    """
    cycles = []

    def dfs(start, path, visited):
        for nxt in sorted(dep_graph.get(path[-1], set())):
            if nxt == start and len(path) >= 3:
                cycles.append(path + [nxt])
                return
            if nxt not in visited:
                visited.add(nxt)
                dfs(start, path + [nxt], visited)

    for n in sorted(names):
        dfs(n, [n], {n})
    seen, uniq = set(), []
    for c in cycles:
        key = tuple(sorted(c[:-1]))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    uniq.sort()  # 稳定排序，保证快照/基线对比可复现（set 迭代顺序随进程变化）
    return uniq[:limit]


def analyze(mods):
    """结构模型：耦合度(出边+入边)、孤岛(无依赖)、环检测(强连通)。

    环检测只看「模块级硬依赖(deps)」；「函数内延迟导入(lazy_deps)」另算
    lazy_cycles 供参考，不计入治理口径的病理环。
    """
    names = list(mods.keys())
    dep_of = {n: set(mods[n]['deps']) for n in names}          # 出边（模块级硬依赖）
    lazy_dep_of = {n: set(mods[n].get('lazy_deps', [])) for n in names}  # 出边（延迟导入）
    dep_by = {n: set() for n in names}                          # 入边
    for n, deps in dep_of.items():
        for d in deps:
            if d in dep_by:
                dep_by[d].add(n)
    islands = [n for n in names if not dep_of[n] and not dep_by[n]]
    leaves = [n for n in names if not dep_of[n] and dep_by[n]]
    roots = [n for n in names if dep_of[n] and not dep_by[n]]
    cycles = _find_cycles(names, dep_of)              # 真实模块级环（治理口径）
    lazy_cycles = _find_cycles(names, lazy_dep_of)    # 延迟导入假环（仅参考）
    return {
        'total_py': sum(m['py'] for m in mods.values()),
        'total_lines': sum(m['lines'] for m in mods.values()),
        'islands': islands,
        'leaves': leaves,
        'roots': roots,
        'cycles': cycles,
        'lazy_cycles': lazy_cycles,
        'modules': mods,
    }


def model():
    mods = scan_modules()
    r = analyze(mods)
    ts = time.strftime('%Y-%m-%d_%H-%M-%S')
    out = OUT_DIR / f"model-{ts}.json"
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(f"[model] 快照已存 {out}")
    print(f"  模块数 {len(mods)} | 总py {r['total_py']} | 总行数 {r['total_lines']:,}")
    islands_disp = [f"{n}(豁免:{ISLAND_EXEMPT[n]})" if n in ISLAND_EXEMPT else n
                    for n in r['islands']]
    print(f"  孤岛: {islands_disp or '无'}")
    print(f"  根(只出): {r['roots'] or '无'} | 叶(只入): {r['leaves'] or '无'}")
    print(f"  环: {r['cycles'] or '无'}")
    print(f"  假环(延迟导入): {r['lazy_cycles'] or '无'}")
    return r


# ---- 第7章 网络计划：关键路径 ----
# SPEC 与工单的手工依赖表（真实状态，可从 BATCH-WORKORDERS 自动扩展）
# 每项: id: (名称, 工期估计天, [前置], 状态)
#   状态: done=已合入main / doing=进行中 / todo=待施工 / blocked=搁置
#   关键路径只统计非 done 项的工期 → 反映"剩余欠账"的最长链
WORK_ITEMS = {
    'S04': ('集成地狱2.0总纲', 3, [], 'done'),
    'S05': ('五维记忆融合', 5, ['S04'], 'done'),
    'S08': ('三线收口', 4, ['S04'], 'done'),
    'S09': ('威胁情报记忆层', 4, ['S04'], 'done'),
    'S10': ('三线收口解冻', 3, ['S08'], 'done'),
    'K':   ('情报图谱化', 3, ['S09'], 'done'),
    'L':   ('情报生命周期', 3, ['S09'], 'done'),
    'M':   ('OSINT采集器', 2, ['S09'], 'done'),
    'H':   ('同步层生产化', 3, ['S08'], 'done'),
    'I':   ('Lumo MCP封装', 2, ['S08'], 'done'),
    'J':   ('寄生Windows', 5, ['S08'], 'done'),
    'F':   ('记忆模块六件套', 4, ['S05'], 'done'),
    'G':   ('射频三报告', 2, [], 'done'),
    'D':   ('多agent编排报告', 2, [], 'done'),
    'E':   ('Lumo科研库', 3, ['S05'], 'done'),
    'N':   ('哨兵网格固件', 4, ['S10'], 'done'),          # SPEC-12 第七批
    'O':   ('lumo gateway QQ/微信', 3, ['S10'], 'done'), # SPEC-11 第七批
    'Q':   ('Channel2World', 3, ['S10'], 'done'),        # SPEC-12 第七批
    'P':   ('dcp LoRa帧协议', 3, ['N'], 'done'),         # SPEC-13 第八批
    'R':   ('NEKO语音管线', 3, ['S10'], 'done'),         # SPEC-13 第八批
    'S':   ('Lumo工具注册中心', 3, ['S10'], 'done'),     # SPEC-13 第八批
    'T':   ('冥王峡谷知识底座', 5, ['P', 'R', 'S'], 'doing'),  # SPEC-15 T线；06-01/06-02 OpenArc勘察+SPEC已落盘(main 5014465a/27625d6f)，canyon-kb独立仓
    'U':   ('lumo身份层设计系统', 2, ['S10'], 'doing'),  # U线 天选7前端
    'P2':  ('ESP32固件真机联调', 2, ['P'], 'todo'),      # P-02 未编译/未上真机
    'A07': ('apiserver依赖环拆解', 1, ['S10'], 'done'),  # 07线 治理拆环：5假环核实+扫描器硬/延迟依赖分离
    # ── 卷173 清账补录（2026-09-29，卷174-C）——只录有 git/PR 证据的项 ──
    'V161': ('dependabot死锁修复', 2, [], 'done'),       # PR #88 websockets/authlib 上限
    'V166': ('发布管线+打包收刀', 4, [], 'done'),        # PR #104~#110 build/release 线首航
    'V167': ('总线分类体系与装配', 3, [], 'done'),       # PR #121~#123 分类/深检/装配策略/requires
    'V173': ('CI分层测试矩阵+pre-push钩子', 2, [], 'done'),   # 本卷（scripts/install_hooks.py 等）
    'V174': ('governance工具补全', 2, [], 'done'),       # 卷174-A/B/D已落main(d081cd82)：--evaluate/--forecast/--decide
    'V175': ('孤岛治理research+coupled', 2, [], 'done'),  # 卷175-B勘察报告+维持现状裁定(4969c621)
    'V172': ('dependabot清账二期', 3, ['V161'], 'doing'),  # 2026-10-02第一波：PR#131-133合+根uv.lock13包升级(06968322)；余NEKO上游债+litellm卷193迁移+chromadb无补丁挂账
    'V168': ('授粉轮25 MOF多孔', 3, [], 'done'),          # main归档c2c1bf43
    'V169': ('授粉轮26 逆合成对接', 3, [], 'done'),       # main归档0a987a45
    'V170': ('授粉轮27 PSE-TEA', 3, [], 'done'),          # main归档ac04e42e
    'V171': ('授粉轮28 无人机绕障', 2, [], 'done'),       # main归档4d3510d4
    'L1':  ('法学管线人肉验收(外部)', 2, [], 'todo'),     # LAW_WORKORDER_CONTRIB_L1
    'L2':  ('法学管线二期扩展(外部)', 3, [], 'todo'),     # LAW_WORKORDER_CONTRIB_L2
}


def cpm():
    nodes, edges = {}, []
    for wid, (name, dur, preds, status) in WORK_ITEMS.items():
        nodes[wid] = {'name': name, 'dur': dur if status != 'done' else 0, 'status': status}
        for p in preds:
            edges.append((p, wid))
    # 拓扑排序 + 最早开始
    indeg = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for p, c in edges:
        adj[p].append(c)
        indeg[c] += 1
    queue = [n for n, d in indeg.items() if d == 0]
    order, es, ef = [], {}, {}
    for n in nodes:
        es[n] = ef[n] = 0
    while queue:
        n = queue.pop(0)
        order.append(n)
        for c in adj[n]:
            indeg[c] -= 1
            es[c] = max(es[c], ef[n])
            if indeg[c] == 0:
                queue.append(c)
        ef[n] = es[n] + nodes[n]['dur']
    if len(order) != len(nodes):
        print("[cpm] 存在环，无法计算关键路径")
        return None
    total = max(ef.values())
    # 逆推最迟
    ls = {n: total for n in nodes}
    for n in reversed(order):
        for c in adj[n]:
            ls[n] = min(ls[n], ls[c] - nodes[c]['dur'])
    critical = [n for n in nodes if es[n] == ls[n]]
    # 卷174-C 校准：关键路径链 = 从 ef==total 的终点沿「严格关键边」反推到 es==0 的起点。
    # 严格关键边定义：es[p] + dur[p] == es[cur]（p 顶满 cur 的最早开始时刻）。
    # 修复点：①不再 `cand = preds` 瞎兜底（旧逻辑会挑非关键前置 → 链断裂）；
    #         ②done 桥接项（dur=0）只要顶满时刻就能进链——修掉旧口径
    #           「done 项被 es==ls 踢出 critical 集 → 链断」的缺陷；
    #         ③链无关键前置时显式警告（不静默给出假链）。
    ends = [n for n in nodes if ef[n] == total]
    path = []
    if ends:
        cur = ends[0]
        chain = [cur]
        while True:
            # 关键前置：顶满 cur 最早开始时刻的父节点（含 dur=0 的 done 桥接项——
            # 它们是链的真实组成，穿过它们直到真正的图起点）
            key_preds = [p for p, c in edges if c == cur and es[p] + nodes[p]['dur'] == es[cur]]
            if not key_preds:
                if edges and any(c == cur for _, c in edges):
                    print(f"[cpm] 警告：节点 {cur} 有前置但无关键前置（链断裂），关键路径不完整")
                break  # 无任何前置 = 图起点，链完整
            cur = key_preds[0]
            chain.append(cur)
        path = list(reversed(chain))
        if not path:
            path = [n for n in order if n in critical]
    print(f"[cpm] 剩余工期 {total} 天 | 关键路径({len(path)}节点): {' → '.join(path)}")
    for n in path:
        st = nodes[n]['status']
        mark = '' if st == 'done' else f" [{st}]"
        print(f"      {n} [{nodes[n]['name']}]{mark} {es[n]}~{ef[n]}d")
    backlog = [f"{wid}({nodes[wid]['name']})" for wid, d in nodes.items() if d['status'] in ('todo', 'doing')]
    if backlog:
        print(f"[欠账] {' / '.join(backlog)}")
    return {'critical': path, 'total': total,
            'items': {k: {'es': es[k], 'ef': ef[k], 'ls': ls[k], 'status': nodes[k]['status']} for k in nodes},
            'backlog': backlog}


def pulse():
    m = model()
    c = cpm()
    if c:
        line = (f"PULSE {time.strftime('%m-%d %H:%M')} | py={m['total_py']} 行={m['total_lines']:,} "
                f"| 孤岛={m['islands'] or '无'} 环={len(m['cycles'])} "
                f"| 剩余工期={c['total']}d 关键路径={' → '.join(c['critical'])}")
        if c.get('backlog'):
            line += " | 欠账=" + ','.join(c['backlog'])
        # 卷174-B：--pulse 追加 forecast 摘要（--no-forecast 可关，防 cron 场景变慢）
        if '--no-forecast' not in sys.argv:
            fc = forecast(quiet=True)
            if fc:
                parts = []
                if 'commits_per_week_next4' in fc:
                    parts.append(f"commit/周→{fc['commits_per_week_next4']}")
                if 'total_py_next' in fc:
                    parts.append(f"py→{fc['total_py_next']}")
                if parts:
                    line += " | forecast=" + ','.join(parts)
    else:
        line = "PULSE 计算失败"
    print(line)
    (OUT_DIR / 'pulse-latest.txt').write_text(line + '\n')


# ---- 卷174-A：授粉落地率矩阵 ----
#
# 判定规则（写死，防后续口径漂移）：
#   paper   = 项目只出现在 docs/*授粉报告*.md 的候选表（粗体首列表行），无任何落地/派单证据
#   claimed = 项目名（repo 短名，大小写不敏感）出现在仓库根 TRAE_WORKORDER_PROMPT_AGENT_*.md
#             —— 已派单未验
#   landed  = ①mcpserver 下存在同名能力目录（或 agent-manifest.json 的 name 字段匹配），或
#             ②`git log --all --oneline` 全文中命中 repo 短名（合并/施工记录）
#   优先级 landed > claimed > paper；同项目多报告出现时保留最高优先级（P0>P1>P2>''）
#   与报告来源、全部命中证据一起写进 JSON 快照，供人工抽查回溯。

_EVAL_PRIORITY_ORDER = {'P0': 0, 'P1': 1, 'P2': 2, '': 3}


_REPO_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]*/?[A-Za-z][A-Za-z0-9_.-]*$')
_REPO_FRAG = re.compile(r'([A-Za-z][A-Za-z0-9_.-]+/[A-Za-z][A-Za-z0-9_.-]+)')


def _collect_pollination_candidates(root: Path | None = None):
    """纸面侧采集：docs/*授粉报告*.md → 结构化候选列表（卷174-A）。

    root 参数供测试注入临时目录；缺省扫 SP/docs。

    已知报告形态（三模式，命中即收）：
      ① 表格粗体首列整格为 owner/repo 形态：| **PMEAL/porespy** | ...
      ② 标题行尾缀 owner/repo：      ### 4. lmfit ★1237（…）· lmfit/lmfit-py
      ③ 标题行单名：                 ### 4. lmfit ★1237
    过滤规则（写死防口径漂移）：
      - 候选整体必须匹配 owner/repo 或单词名形态（中文描述句、普通词组如
        "merge/keep" 被形态过滤排除——表格粗体格不做碎片搜索）
      - 排除源码/配置文件名后缀；repo 短名 ≥3 字符
      - 同项目多报告出现保留最高优先级（P0 > P1 > P2 > 无）
    """
    docs_dir = root if root is not None else (SP / 'docs')
    items = {}

    def add(name: str, prio: str, rep_name: str):
        name = name.strip().strip('*').strip()
        if not _REPO_NAME.match(name):
            return
        if name.lower().endswith(('.py', '.json', '.md', '.yml', '.yaml', '.toml')):
            return
        repo = name.split('/')[-1].lower()
        if len(repo) < 3:
            return
        cur = items.get(repo)
        if cur is None:
            items[repo] = {'project': name, 'repo': repo, 'priority': prio,
                           'reports': [rep_name]}
        else:
            # 报告来源始终合并；优先级只升不降（P0 > P1 > P2 > 无）
            if rep_name not in cur['reports']:
                cur['reports'].append(rep_name)
            if _EVAL_PRIORITY_ORDER[prio] < _EVAL_PRIORITY_ORDER[cur['priority']]:
                cur['priority'] = prio

    for rep in sorted(docs_dir.glob('*授粉报告*.md')):
        try:
            text = rep.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for line in text.splitlines():
            pm = re.search(r'\b(P[012])\b', line)
            prio = pm.group(1) if pm else ''
            # ① 表格粗体首列——整格必须是 owner/repo 形态才收（FRAG 碎片搜索会把
            #    "归并阶段用 LLM 做 merge/keep 决策"里的普通词组当项目名，误收）
            m = re.match(r'^\|\s*\*\*(.+?)\*\*\s*\|', line)
            if m:
                cell = m.group(1).strip()
                if '/' in cell and _REPO_NAME.match(cell):
                    add(cell, prio, rep.name)
                continue
            # ② 标题行 `· owner/repo` 尾缀
            m = re.match(r'^#{2,4}\s+.*?·\s*([A-Za-z][\w.-]+/[\w.-]+)', line)
            if m:
                add(m.group(1), prio, rep.name)
                continue
            # ③ 标题行 `### N. 单名 ★`
            m = re.match(r'^#{2,4}\s+\d*\.\s*([A-Za-z][\w.-]+)\s*★', line)
            if m:
                add(m.group(1), prio, rep.name)
    return list(items.values())


def _decide_state(repo: str, mcp_names: set, wo_text: str, git_log_text: str) -> tuple[str, str]:
    """三态判定（纯函数，卷174-A 验收核心）。

    优先级 landed > claimed > paper：
      landed  = repo 在 mcpserver 能力名集合，或命中 git log 全文
      claimed = repo 在 TRAE 工单文本
      paper   = 无任何证据
    """
    if not repo:
        return 'paper', ''
    if repo in mcp_names:
        return 'landed', 'mcpserver 能力目录匹配'
    if repo in git_log_text:
        return 'landed', 'git log 命中'
    if repo in wo_text:
        return 'claimed', 'TRAE 工单已派单'
    return 'paper', ''


def evaluate():
    """--evaluate：纸面授粉 vs 代码落地对照矩阵（卷174-A）。"""
    candidates = _collect_pollination_candidates()

    # 落地侧证据 ①：mcpserver 能力目录名 + manifest name
    mcp_names = set()
    for mf in (SP / 'mcpserver').glob('*/agent-manifest.json'):
        mcp_names.add(mf.parent.name.lower())
        try:
            nm = json.loads(mf.read_text(encoding='utf-8')).get('name')
            if isinstance(nm, str):
                mcp_names.add(nm.lower())
        except (json.JSONDecodeError, OSError):
            continue

    # 落地侧证据 ②：派单记录（TRAE 工单——根目录 168+ 新单、docs/workorders/prompts
    # 的 W 系单、docs/workorders/batch 的批次台账）
    wo_text = ''
    wo_files = list(SP.glob('TRAE_WORKORDER_PROMPT_AGENT_*.md'))
    wo_files += list((SP / 'docs' / 'workorders' / 'prompts').glob('*.md'))
    wo_files += list((SP / 'docs' / 'workorders' / 'batch').glob('*.md'))
    for f in wo_files:
        try:
            wo_text += f.read_text(encoding='utf-8', errors='ignore').lower()
        except OSError:
            continue

    # 落地侧证据 ③：git log --all --oneline 全文（一次调用，内存匹配）
    try:
        gl = subprocess.run(['git', '-c', 'core.quotepath=false', 'log', '--all', '--oneline'],
                            capture_output=True, text=True, encoding='utf-8', errors='ignore',
                            cwd=SP, check=True, timeout=60).stdout.lower()
    except (subprocess.SubprocessError, OSError):
        gl = ''

    rows = []
    for it in candidates:
        state, evidence = _decide_state(it['repo'], mcp_names, wo_text, gl)
        rows.append({**it, 'state': state, 'evidence': evidence})

    order = {'landed': 0, 'claimed': 1, 'paper': 2}
    rows.sort(key=lambda r: (order[r['state']], _EVAL_PRIORITY_ORDER[r['priority']]))

    counts = {'landed': 0, 'claimed': 0, 'paper': 0}
    for r in rows:
        counts[r['state']] += 1
    total = len(rows)
    print(f"[evaluate] 授粉候选 {total} 项 | landed {counts['landed']} / "
          f"claimed {counts['claimed']} / paper {counts['paper']} "
          f"| 落地率 {counts['landed']}/{total} = {counts['landed'] * 100 // total if total else 0}%")
    for r in rows[:20]:
        mark = {'landed': '✅', 'claimed': '🟡', 'paper': '⬜'}.get(r['state'], '?')
        print(f"  {mark} [{r['state']:7s}] {r['project']:36s} {r['priority']:2s} {r['evidence']}")

    # JSON 快照
    ts = time.strftime('%Y-%m-%d')
    snap = {'date': ts, 'total': total, 'counts': counts, 'items': rows}
    out = OUT_DIR / f"evaluate-{ts}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    (OUT_DIR / 'pollination-inventory.json').write_text(
        json.dumps(candidates, ensure_ascii=False, indent=1))
    print(f"[evaluate] 快照已存 {out}")

    # 报告骨架（top10 纸面沉淀项：立项最久的 paper 项排前——按报告文件名日期升序近似）
    report = SP / 'docs' / f"governance-授粉落地率-{ts}.md"
    if not report.exists():
        paper_rows = [r for r in rows if r['state'] == 'paper'][:10]
        lines = [
            f"# 授粉落地率报告 · {ts} · 卷174-A 骨架",
            "",
            f"- 候选 {total} 项：landed {counts['landed']} / claimed {counts['claimed']} / "
            f"paper {counts['paper']}（落地率 {counts['landed'] * 100 // total if total else 0}%）",
            "- 数据快照：data/system_pulse/evaluate-{}.json（判定规则见 system_governance.py --evaluate docstring）",
            "",
            "## top10 纸面沉淀项（paper 态，待人工给处置意见：继续/降级/归档）",
            "",
            "| 项目 | 优先级 | 报告来源 |",
            "|---|---|---|",
        ]
        for r in paper_rows:
            lines.append(f"| {r['project']} | {r['priority'] or '—'} | {r['reports'][0]} |")
        lines += ["", "> 待实验田维护者人工补处置意见。", ""]
        report.write_text('\n'.join(lines), encoding='utf-8')
        print(f"[evaluate] 报告骨架已落 {report}")
    return {'counts': counts, 'total': total}


# ---- 卷174-B：趋势外推 ----

def _least_squares(xs, ys):
    """单变量最小二乘 y = a*x + b（纯 Python，数据点 ~26 个，性能无要求）。"""
    n = len(xs)
    if n < 2:
        return None
    sx, sy = sum(xs), sum(ys)
    sxx, sxy = sum(x * x for x in xs), sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return a, b


def forecast(quiet: bool = False):
    """--forecast：commit 周量 + 代码规模趋势，最小二乘外推未来 4 周（卷174-B）。

    数据源：
      1. git log --since=6.months --pretty=format:%ad 按周聚合 commit 数
      2. data/system_pulse/model-*.json 历史快照的 total_py / total_lines 序列
    样本不足（<3 点）时输出「样本不足」，不硬算。
    """
    ts = time.strftime('%Y-%m-%d')
    result = {}

    # ① commit 周量
    try:
        gl = subprocess.run(
            ['git', 'log', '--since=6.months', '--pretty=format:%ad', '--date=format:%G-W%V'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            cwd=SP, check=True, timeout=60).stdout.splitlines()
    except (subprocess.SubprocessError, OSError):
        gl = []
    weeks = {}
    for wk in gl:
        wk = wk.strip()
        if wk:
            weeks[wk] = weeks.get(wk, 0) + 1
    keys = sorted(weeks)
    if len(keys) >= 3:
        xs = list(range(len(keys)))
        ys = [weeks[k] for k in keys]
        fit = _least_squares(xs, ys)
        if fit:
            a, b = fit
            nxt = [max(0, round(a * (len(xs) + i) + b)) for i in range(1, 5)]
            result['commits_per_week_next4'] = nxt
            result['commits_sample_weeks'] = len(keys)
            if not quiet:
                print(f"[forecast] commit 周量：近 {len(keys)} 周，未来 4 周外推 {nxt} "
                      f"（斜率 {a:+.2f}/周）")
    elif not quiet:
        print("[forecast] commit 周量：样本不足（<3 周），跳过外推")

    # ② 快照序列（total_py / total_lines）
    snaps = sorted(OUT_DIR.glob('model-*.json'))
    pys, lns = [], []
    for f in snaps:
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            pys.append(d.get('total_py'))
            lns.append(d.get('total_lines'))
        except (json.JSONDecodeError, OSError):
            continue
    for label, series in (('total_py', pys), ('total_lines', lns)):
        pts = [(i, v) for i, v in enumerate(series) if isinstance(v, (int, float))]
        if len(pts) >= 3:
            fit = _least_squares([p[0] for p in pts], [p[1] for p in pts])
            if fit:
                a, b = fit
                nxt = round(a * len(series) + b)
                result[label + '_next'] = nxt
                result[label + '_samples'] = len(pts)
                if not quiet:
                    print(f"[forecast] {label}：{len(pts)} 份快照，下一快照外推 ≈{nxt:,}（斜率 {a:+.1f}）")
        elif not quiet:
            print(f"[forecast] {label}：样本不足（<3 份快照），跳过外推")

    if result:
        out = OUT_DIR / f"forecast-{ts}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1))
        if not quiet:
            print(f"[forecast] 快照已存 {out}")
    return result or None


# ---- 卷174-D：--decide 占位 ----

def decide():
    """--decide：占位骨架（卷174-D 只立入口，防 KeyError）。

    待建：输入=环/孤岛/落地率（--model + --evaluate 输出），输出=优先级建议。
    """
    print("[decide] --decide 待建：输入=环/孤岛/落地率，输出=优先级建议")
    return None


if __name__ == '__main__':
    raw = [a for a in sys.argv[1:] if a != '--no-forecast']
    cmd = raw[0].lstrip('-') if raw else 'pulse'
    {'model': model, 'cpm': cpm, 'pulse': pulse,
     'evaluate': evaluate, 'forecast': forecast, 'decide': decide}.get(cmd, pulse)()
