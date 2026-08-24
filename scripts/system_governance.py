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
import os, re, json, sys, time
from pathlib import Path

SP = Path("/home/ubuntu/scratchpad")
SKIP_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', '.venv', 'dist', 'build', 'vault', 'repos', 'vendor'}
TOP_MODS = ['apiserver', 'NEKO', 'mcpserver', 'summer_memory', 'rag', 'tools', 'scripts',
            'coupled', 'agentserver', 'guide_engine', 'system', 'voice', 'kb_sync', 'research']
OUT_DIR = Path("/home/ubuntu/scratchpad/data/system_pulse")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def scan_modules():
    mods = {}
    for name in TOP_MODS:
        full = SP / name
        if not full.is_dir():
            continue
        py_count, total_lines, imports = 0, 0, set()
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
                for m in TOP_MODS:
                    if m == name:
                        continue
                    if re.search(rf'^\s*(from|import)\s+{m}\b', txt, re.M):
                        imports.add(m)
        mods[name] = {'py': py_count, 'lines': total_lines, 'deps': sorted(imports)}
    return mods


def analyze(mods):
    """结构模型：耦合度(出边+入边)、孤岛(无依赖)、环检测(强连通)"""
    names = list(mods.keys())
    dep_of = {n: set(mods[n]['deps']) for n in names}          # 出边
    dep_by = {n: set() for n in names}                          # 入边
    for n, deps in dep_of.items():
        for d in deps:
            if d in dep_by:
                dep_by[d].add(n)
    islands = [n for n in names if not dep_of[n] and not dep_by[n]]
    leaves = [n for n in names if not dep_of[n] and dep_by[n]]
    roots = [n for n in names if dep_of[n] and not dep_by[n]]
    # 环检测：只报 ≥3 节点的循环依赖（2 节点互引是正常双向依赖，不算病理）
    cycles = []

    def dfs(start, path, visited):
        for nxt in dep_of.get(path[-1], set()):
            if nxt == start and len(path) >= 3:
                cycles.append(path + [nxt])
                return
            if nxt not in visited:
                visited.add(nxt)
                dfs(start, path + [nxt], visited)

    for n in names:
        dfs(n, [n], {n})
    seen = set()
    uniq_cycles = []
    for c in cycles:
        key = tuple(sorted(c[:-1]))
        if key not in seen:
            seen.add(key)
            uniq_cycles.append(c)
    cycles = uniq_cycles[:5]
    return {
        'total_py': sum(m['py'] for m in mods.values()),
        'total_lines': sum(m['lines'] for m in mods.values()),
        'islands': islands,
        'leaves': leaves,
        'roots': roots,
        'cycles': cycles,
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
    print(f"  孤岛: {r['islands'] or '无'}")
    print(f"  根(只出): {r['roots'] or '无'} | 叶(只入): {r['leaves'] or '无'}")
    print(f"  环: {r['cycles'] or '无'}")
    return r


# ---- 第7章 网络计划：关键路径 ----
# SPEC 与工单的手工依赖表（真实状态，可从 BATCH-WORKORDERS 自动扩展）
WORK_ITEMS = {
    # id: (名称, 工期估计天, [前置])
    'S04': ('集成地狱2.0总纲', 3, []),
    'S05': ('五维记忆融合', 5, ['S04']),
    'S08': ('三线收口', 4, ['S04']),
    'S09': ('威胁情报记忆层', 4, ['S04']),
    'K':   ('情报图谱化', 3, ['S09']),
    'L':   ('情报生命周期', 3, ['S09']),
    'M':   ('OSINT采集器', 2, ['S09']),
    'H':   ('同步层生产化', 3, ['S08']),
    'I':   ('Lumo MCP封装', 2, ['S08']),
    'J':   ('寄生Windows', 5, ['S08']),
    'F':   ('记忆模块六件套', 4, ['S05']),
    'G':   ('射频三报告', 2, []),
    'D':   ('多agent编排报告', 2, []),
    'E':   ('Lumo科研库', 3, ['S05']),
}


def cpm():
    nodes, edges = {}, []
    for wid, (name, dur, preds) in WORK_ITEMS.items():
        nodes[wid] = {'name': name, 'dur': dur}
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
    # 关键路径 = 从起点(es=0)到终点(ef=total)的 critical 链
    starts = [n for n in nodes if es[n] == 0]
    ends = [n for n in nodes if ef[n] == total]
    path = []
    if starts and ends:
        # 沿 critical 节点从最早起点向后走
        frontier = [s for s in starts if s in critical]
        seen = set()
        while frontier:
            n = frontier.pop(0)
            if n in seen:
                continue
            seen.add(n)
            path.append(n)
            nxt = [c for c in adj[n] if c in critical and c not in seen]
            frontier = nxt + frontier
    if not path:
        path = [n for n in order if n in critical]
    print(f"[cpm] 总工期 {total} 天 | 关键路径({len(path)}节点): {' → '.join(path)}")
    for n in path:
        print(f"      {n} [{nodes[n]['name']}] {es[n]}~{ef[n]}d")
    return {'critical': path, 'total': total, 'items': {k: {'es': es[k], 'ef': ef[k], 'ls': ls[k]} for k in nodes}}


def pulse():
    m = model()
    c = cpm()
    line = (f"PULSE {time.strftime('%m-%d %H:%M')} | py={m['total_py']} 行={m['total_lines']:,} "
            f"| 孤岛={m['islands'] or '无'} 环={len(m['cycles'])} "
            f"| 关键路径总工期={c['total']}d" if c else "PULSE 计算失败")
    print(line)
    (OUT_DIR / 'pulse-latest.txt').write_text(line + '\n')


if __name__ == '__main__':
    cmd = sys.argv[1].lstrip('-') if len(sys.argv) > 1 else 'pulse'
    {'model': model, 'cpm': cpm, 'pulse': pulse}[cmd]()
