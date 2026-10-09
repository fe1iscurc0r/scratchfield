"""工单209 任务二 · renderer.ts 拆分 阶段二：layout / quadtree。

- layout.ts：Sector 类型 + layoutRadius + buildSectors + typeSectorTarget
  （buildSectors 原本重赋值 sectors → 改为返回新数组；typeSectorTarget 追加 sectors 参数）
- quadtree.ts：QuadNode 类型 + BH 常量 + 7 个四叉树函数 → 收进**工厂闭包** createQuadTree(nodes, cfg)，
  内部函数**零改动**（自然闭包 factory 参数），暴露 { build, repel }

行号基于阶段一之后的文件（renderer.ts 现 1466 行）。

用法：cd "D:/my git/scratchpad/frontend" && ../.venv/Scripts/python.exe ../tools/_w209_split_renderer_p2.py
"""
from __future__ import annotations

from pathlib import Path

SRC = Path("src/views/mind/renderer.ts")
BAK = Path("C:/Users/ASUS/AppData/Local/Temp/w222/renderer.p1.bak")
RENDER_DIR = Path("src/views/mind/render")

text = SRC.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
assert text.count("\r\n") == 0, "源文件应为 LF"
assert "function buildSectors()" in text, "阶段一未完成或已跑过阶段二"


def seg(a: int, b: int) -> str:
    return "".join(lines[a - 1:b])


def func_end(start: int) -> int:
    for i in range(start, len(lines)):
        if lines[i].rstrip("\n") == "  }":
            return i + 1
    raise AssertionError(f"未找到函数结尾: L{start}")


# ── 定位（阶段一之后的行号）──
i_sector = next(i for i, l in enumerate(lines) if l.startswith("  interface Sector {")) + 1
i_layout_radius = next(i for i, l in enumerate(lines) if l.startswith("  function layoutRadius(")) + 1
i_sectors_decl = next(i for i, l in enumerate(lines) if l.startswith("  let sectors: Sector[]")) + 1
i_build_sectors = next(i for i, l in enumerate(lines) if l.startswith("  function buildSectors(")) + 1
i_type_target = next(i for i, l in enumerate(lines) if l.startswith("  function typeSectorTarget(")) + 1
i_quad_comment = next(i for i, l in enumerate(lines) if "Barnes-Hut 四叉树" in l) + 1
i_quad_repel = next(i for i, l in enumerate(lines) if l.startswith("  function quadRepel(")) + 1

e_layout_radius = func_end(i_layout_radius)
e_type_target = func_end(i_type_target)
e_quad_repel = func_end(i_quad_repel)

print(f"定位: Sector@{i_sector} layoutRadius@{i_layout_radius}-{e_layout_radius} "
      f"sectorsDecl@{i_sectors_decl} buildSectors@{i_build_sectors} "
      f"typeSectorTarget@{i_type_target}-{e_type_target} "
      f"quadBlock@{i_quad_comment}-{e_quad_repel}")

block_layout_a = seg(i_sector, e_layout_radius)        # Sector + 注释 + layoutRadius
block_layout_b = seg(i_build_sectors, e_type_target)   # buildSectors + typeSectorTarget
block_quad = seg(i_quad_comment, e_quad_repel)         # 注释 + QuadNode + 常量 + 7 函数
assert "interface Sector {" in block_layout_a and "function layoutRadius(" in block_layout_a
assert "function buildSectors(" in block_layout_b and "function typeSectorTarget(" in block_layout_b
assert "interface QuadNode {" in block_quad and "function quadBuild(" in block_quad

# ── layout.ts ──
la = block_layout_a
la = la.replace("  function layoutRadius(): number {",
                "export function layoutRadius(nodes: SeaNode[]): number {", 1)
la = la.replace("  interface Sector {", "export interface Sector {", 1)
lb = block_layout_b
lb = lb.replace("  function buildSectors() {",
                "export function buildSectors(nodes: SeaNode[]): Sector[] {", 1)
lb = lb.replace("    sectors = []", "    const sectors: Sector[] = []", 1)
assert "const R = layoutRadius()" in lb
lb = lb.replace("const R = layoutRadius()", "const R = layoutRadius(nodes)", 1)
# buildSectors 结尾插 return
lb_lines = lb.splitlines(keepends=True)
end_i = next(i for i in range(len(lb_lines) - 1, -1, -1) if lb_lines[i].rstrip("\n") == "  }")
lb_lines.insert(end_i, "    return sectors\n")
lb = "".join(lb_lines)
lb = lb.replace("  function typeSectorTarget(n: SeaNode, ordinal: number) {",
                "export function typeSectorTarget(n: SeaNode, ordinal: number, sectors: Sector[]) {", 1)
# 两条 assert：签名都换了
assert "export function buildSectors(nodes: SeaNode[]): Sector[] {" in lb
assert "export function typeSectorTarget(n: SeaNode, ordinal: number, sectors: Sector[]) {" in lb
assert "return sectors" in lb

(RENDER_DIR / "layout.ts").write_text(
    "/**\n"
    " * mind 视图 · 分区布局（扇区划分 / 圆盘半径 / 簇内目标点）。\n"
    " * 自 views/mind/renderer.ts 拆出（工单209 任务二）。\n"
    " *\n"
    " * **纯移动**：函数体逐字节搬运，仅把闭包变量改为显式参数 ——\n"
    " * `nodes` 传参；`buildSectors` 原本重赋值闭包里的 `sectors`，这里改为**返回新数组**；\n"
    " * `typeSectorTarget` 需要的 `sectors` 由调用方传入（renderer 仍是状态所有者）。\n"
    " */\n"
    "import type { SeaNode } from './types'\n\n"
    + la.rstrip("\n") + "\n\n" + lb.rstrip("\n") + "\n",
    encoding="utf-8",
)

# ── quadtree.ts（工厂闭包：内部函数零改动）──
qb = block_quad
quad_iface = seg(next(i for i, l in enumerate(lines) if l.startswith("  interface QuadNode {")) + 1,
                 func_end_count := (next(i for i, l in enumerate(lines)
                                         if l.startswith("  interface QuadNode {")) + 13))
# 上面 13 行是 QuadNode 的固定长度（12 字段 + 1 闭合）；下面用断言兜底
assert quad_iface.count("QuadNode | null") >= 4 or "nw: QuadNode | null" in quad_iface, \
    f"QuadNode 抽取可疑: {quad_iface[:80]!r}"

qb_inner = block_quad.replace(quad_iface, "")          # 函数体内不含 QuadNode 声明
assert "interface QuadNode {" not in qb_inner

(RENDER_DIR / "quadtree.ts").write_text(
    "/**\n"
    " * mind 视图 · Barnes-Hut 四叉树（n>150 自动切换，O(n²) → O(n log n)）。\n"
    " * 自 views/mind/renderer.ts 拆出（工单209 任务二）。\n"
    " *\n"
    " * **纯移动**：7 个内部函数逐字节搬运、**零改动** —— 它们原本就闭包在 createMindRenderer 内，\n"
    " * 这里改为闭包在 `createQuadTree(nodes, cfg)` 工厂内（同样的闭包语义，同样的调用序）。\n"
    " * 唯一新增的是工厂壳与 `QuadNode` 提到模块作用域（供返回类型引用）。\n"
    " */\n"
    "import type { SeaNode } from './types'\n\n"
    "export interface QuadtreeCfg {\n  /** 本模块只读取 cfg.spread */\n  spread: number\n}\n\n"
    + quad_iface.rstrip("\n") + "\n\n"
    "export interface QuadTreeApi {\n"
    "  build: () => QuadNode | null\n"
    "  repel: (root: QuadNode | null, i: number, alpha: number) => void\n"
    "}\n\n"
    "export function createQuadTree(nodes: SeaNode[], cfg: QuadtreeCfg): QuadTreeApi {\n"
    + qb_inner.rstrip("\n") + "\n\n"
    "  return { build: quadBuild, repel: quadRepel }\n"
    "}\n",
    encoding="utf-8",
)

# ── 改 renderer.ts ──
new = text
for blk, label in ((block_quad, "quadtree 块"),
                   (block_layout_b, "buildSectors+typeSectorTarget"),
                   (block_layout_a, "Sector+layoutRadius")):
    assert blk in new, f"待删块未命中: {label}"
    new = new.replace(blk, "", 1)
    print(f"  删除 {label}（{blk.count(chr(10))} 行）")

imp = "import { buildSectors, typeSectorTarget, type Sector } from './render/layout'\nimport { createQuadTree } from './render/quadtree'\n"
imp_lines = new.splitlines(keepends=True)
last_imp = max(i for i, l in enumerate(imp_lines) if l.startswith("import "))
imp_lines.insert(last_imp + 1, imp)
new = "".join(imp_lines)

# 调用点
reps = [
    ("    buildSectors()", "    sectors = buildSectors(nodes)"),
    ("typeSectorTarget(n, k)", "typeSectorTarget(n, k, sectors)"),
]
for old, rep in reps:
    n = new.count(old)
    assert n >= 1, f"调用点未命中: {old!r}"
    new = new.replace(old, rep)
    print(f"  调用点 {old.strip()} → {rep.strip()}（{n} 处）")

old_sim = """    if (bh) {
      const root = quadBuild()
      if (root) {
        for (let i = 0; i < nodes.length; i++)
          quadRepel(root, i, alpha)
      }
    }"""
new_sim = """    if (bh) {
      const qt = createQuadTree(nodes, cfg)
      const root = qt.build()
      if (root) {
        for (let i = 0; i < nodes.length; i++)
          qt.repel(root, i, alpha)
      }
    }"""
assert old_sim in new, "simulate 的 quadtree 用法锚点未命中"
new = new.replace(old_sim, new_sim, 1)
print("  simulate() 用法已切到工厂 API")

BAK.write_bytes(text.encode("utf-8"))
SRC.write_bytes(new.replace("\r\n", "\n").encode("utf-8"))
print(f"\nrenderer.ts: {len(lines)} → {new.count(chr(10)) + 1} 行（-{len(lines) - (new.count(chr(10)) + 1)}）")
print("备份:", BAK)
