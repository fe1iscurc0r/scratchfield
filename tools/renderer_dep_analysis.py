"""工单209 任务二 · renderer.ts 依赖分析（正则级：每个内部函数引用哪些闭包变量）。

用法：cd "D:/my git/scratchpad/frontend" && ../.venv/Scripts/python.exe <本文件>
"""
import re
import sys
from pathlib import Path

F = Path("src/views/mind/renderer.ts")
src = F.read_text(encoding="utf-8")
lines = src.splitlines()

# 闭包级变量（在 createMindRenderer 顶层声明）
closure_decl = re.compile(r"^  (?:const|let|var)\s+([A-Za-z_$][\w$]*)")
closure_vars: list[str] = []
for i, ln in enumerate(lines[141:], start=142):  # 从 L142 起
    m = closure_decl.match(ln)
    if m:
        closure_vars.append(m.group(1))
# 也把顶层 import 的符号当成"外部"，不算闭包变量
imported = set()
for ln in lines[:141]:
    m = re.match(r"^import\s+(?:type\s+)?\{([^}]*)\}", ln)
    if m:
        for p in m.group(1).split(","):
            imported.add(p.strip().split(" as ")[-1].strip())
    m2 = re.match(r"^import\s+([A-Za-z_$][\w$]*)", ln)
    if m2:
        imported.add(m2.group(1))
closure_vars = [v for v in closure_vars if v not in imported]

# 内部函数块（按行号切）
fn_re = re.compile(r"^  (?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
fns: list[tuple[str, int, int]] = []
starts = [(i, fn_re.match(ln).group(1)) for i, ln in enumerate(lines) if fn_re.match(ln)]
for idx, (i, name) in enumerate(starts):
    end = starts[idx + 1][0] - 1 if idx + 1 < len(starts) else len(lines)
    fns.append((name, i + 1, end))

print(f"闭包变量 {len(closure_vars)} 个 | 内部函数 {len(fns)} 个\n")

rows = []
for name, a, b in fns:
    body = "\n".join(lines[a - 1:b])
    used = []
    for v in closure_vars:
        if re.search(rf"(?<![.\w$]){re.escape(v)}(?![\w$])", body):
            used.append(v)
    rows.append((name, a, b, b - a + 1, used))

# 只关心"想搬走的"三个簇
CLUSTERS = {
    "effects(粒子/光柱/流/浮游)": ["initParticles", "simParticles", "drawParticles",
                                    "initRays", "drawRays", "initFlow", "simFlow", "drawFlow",
                                    "spawnPlankton", "initPlankton", "simPlankton", "drawPlankton"],
    "layout(扇区/半径)": ["layoutRadius", "buildSectors", "typeSectorTarget"],
    "quadtree(Barnes-Hut)": ["quadCreate", "quadSubdivide", "quadChildOf", "quadInsert",
                             "quadAccumulate", "quadBuild", "quadRepel"],
}
for cname, members in CLUSTERS.items():
    print("=" * 76)
    print(f"{cname}")
    allused: set[str] = set()
    total = 0
    for name, a, b, n, used in rows:
        if name in members:
            total += n
            allused.update(used)
            print(f"  {name:<18} L{a}-{b} ({n}行)  用了: {','.join(sorted(used))[:150]}")
    print(f"  → 合计 {total} 行 | 需要的闭包变量（{len(allused)}）: {','.join(sorted(allused))}")

print("=" * 76)
print("全部内部函数（行数降序，供整体切分参考）")
for name, a, b, n, used in sorted(rows, key=lambda r: -r[3])[:22]:
    print(f"  {name:<28} L{a}-{b}  {n}行  依赖 {len(used)} 个闭包变量")
