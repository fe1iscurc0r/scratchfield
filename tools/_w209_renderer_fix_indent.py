"""工单209 任务二 · 修复：重新生成 render/*.ts（正确缩进 + export + 返回式初始化）。

背景（两个 bug）：
  1. 搬运块整体多缩进一级（闭包内 2 空格 → 模块顶层应为 0），eslint style/indent 大面积报错；
  2. types.ts 的接口未加 `export` → 各模块 import 会失败。

数据源：
  · 原文件      C:/.../w222/renderer.ts.bak   （types 56-92 / 93-141，effects 242-565）
  · 阶段一产物  C:/.../w222/renderer.p1.bak   （layout 170-183 / 187-233，quadtree 235-372）

用法：cd "D:/my git/scratchpad/frontend" && ../.venv/Scripts/python.exe ../tools/_w209_renderer_fix_indent.py
"""
from __future__ import annotations

from pathlib import Path

ORIG = Path("C:/Users/ASUS/AppData/Local/Temp/w222/renderer.ts.bak")
P1 = Path("C:/Users/ASUS/AppData/Local/Temp/w222/renderer.p1.bak")
D = Path("src/views/mind/render")


def load(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines(keepends=True)


def seg(lines: list[str], a: int, b: int) -> str:
    return "".join(lines[a - 1:b])


def dedent2(block: str) -> str:
    out = []
    for ln in block.splitlines(keepends=True):
        if ln.startswith("  "):
            out.append(ln[2:])
        else:
            out.append(ln)
    return "".join(out)


def export_ifaces(block: str) -> str:
    return "\n".join(("export " + ln if ln.startswith("interface ") else ln)
                     for ln in block.splitlines())


o = load(ORIG)
p1 = load(P1)

# ── types.ts ──
types_raw = seg(o, 56, 92) + "\n" + seg(o, 93, 141)
n_ifaces = types_raw.count("\ninterface ") + (1 if types_raw.startswith("interface ") else 0)
types_out = (
    "/**\n"
    " * mind 渲染器 · 内部类型（自 views/mind/renderer.ts 拆出，工单209 任务二）。\n"
    " * **纯移动**：接口定义逐字节搬运，仅补 `export`（模块化必需）与去掉一级缩进。\n"
    " */\n\n"
    + export_ifaces(types_raw.rstrip("\n")) + "\n"
)
(D / "types.ts").write_text(types_out, encoding="utf-8")
print(f"types.ts: {n_ifaces} 个接口已 export")

# ── effects.ts ──
body = dedent2(seg(o, 242, 565))
sig_map = [
    ("function initParticles() {", "export function initParticles(): Particle[] {"),
    ("function simParticles() {", "export function simParticles(particles: Particle[], cfg: EffectsCfg): void {"),
    ("function drawParticles() {",
     "export function drawParticles(cx: CanvasRenderingContext2D | null, particles: Particle[]): void {"),
    ("function initRays() {", "export function initRays(): Ray[] {"),
    ("function drawRays() {",
     "export function drawRays(cx: CanvasRenderingContext2D | null, rays: Ray[], cfg: EffectsCfg, t0: number): void {"),
    ("function initFlow() {", "export function initFlow(links: SeaLink[]): FlowDot[] {"),
    ("function simFlow() {", "export function simFlow(flowParts: FlowDot[]): void {"),
    ("function drawFlow() {",
     "export function drawFlow(cx: CanvasRenderingContext2D | null, flowParts: FlowDot[], t0: number): void {"),
    ("function spawnPlankton(): Plankton {", "export function spawnPlankton(): Plankton {"),
    ("function initPlankton() {", "export function initPlankton(): Plankton[] {"),
    ("function simPlankton() {",
     "export function simPlankton(plankton: Plankton[], cfg: EffectsCfg, t0: number): void {"),
    ("function drawPlankton() {",
     "export function drawPlankton(cx: CanvasRenderingContext2D | null, plankton: Plankton[]): void {"),
]
for old, new in sig_map:
    assert old in body, f"effects 签名锚点未命中: {old!r}"
    body = body.replace(old, new, 1)

b_lines = body.splitlines(keepends=True)
for fname, var, typ in (("initParticles", "particles", "Particle[]"),
                        ("initRays", "rays", "Ray[]"),
                        ("initFlow", "flowParts", "FlowDot[]"),
                        ("initPlankton", "plankton", "Plankton[]")):
    sig_i = next(i for i, l in enumerate(b_lines) if f"export function {fname}(" in l)
    end_i = next(i for i in range(sig_i, len(b_lines)) if b_lines[i].rstrip("\n") == "}")
    b_lines.insert(end_i, f"  return {var}\n")
    for i in range(sig_i, end_i + 1):
        if b_lines[i].rstrip("\n") == f"  {var} = []":
            b_lines[i] = f"  const {var}: {typ} = []\n"
            break
    else:
        raise AssertionError(f"{fname}: 未找到 `{var} = []`")
body = "".join(b_lines)
(D / "effects.ts").write_text(
    "/**\n"
    " * mind 视图 · 环境特效层（粒子 / 光柱 / 流动粒子 / 浮游）。\n"
    " * 自 views/mind/renderer.ts 拆出（工单209 任务二）。\n"
    " *\n"
    " * **纯移动**：函数体逐字节搬运，仅把原闭包变量改为显式参数 ——\n"
    " * 读取型（cx/rays/cfg/t0/links）→ 同名参数；初始化型（particles/rays/flowParts/plankton）\n"
    " * 原本**重新赋值**闭包变量，这里改为**返回新数组**，由调用方接住赋值，语义等价。\n"
    " */\n"
    "import type { FlowDot, Particle, Plankton, Ray, SeaLink } from './types'\n"
    "import { FLOOR_Y, SURFACE_H } from './constants'\n\n"
    "/** 本模块只读取 cfg.hScale */\n"
    "export interface EffectsCfg {\n  hScale: number\n}\n\n"
    + body.rstrip("\n") + "\n", encoding="utf-8")
print("effects.ts 重新生成（dedent + 返回式初始化 + export）")

# ── layout.ts ──
la = dedent2(seg(p1, 170, 183))
la = la.replace("interface Sector {", "export interface Sector {", 1)
la = la.replace("function layoutRadius(): number {",
                "export function layoutRadius(nodes: SeaNode[]): number {", 1)
assert "export interface Sector {" in la and "export function layoutRadius(nodes: SeaNode[])" in la

lb = dedent2(seg(p1, 187, 233))
lb = lb.replace("function buildSectors() {",
                "export function buildSectors(nodes: SeaNode[]): Sector[] {", 1)
lb = lb.replace("  sectors = []", "  const sectors: Sector[] = []", 1)
lb = lb.replace("const R = layoutRadius()", "const R = layoutRadius(nodes)", 1)
lb_l = lb.splitlines(keepends=True)
end_i = next(i for i in range(len(lb_l) - 1, -1, -1) if lb_l[i].rstrip("\n") == "}")
lb_l.insert(end_i, "  return sectors\n")
lb = "".join(lb_l)
lb = lb.replace("function typeSectorTarget(n: SeaNode, ordinal: number) {",
                "export function typeSectorTarget(n: SeaNode, ordinal: number, sectors: Sector[]) {", 1)
assert "export function buildSectors(nodes: SeaNode[]): Sector[] {" in lb
assert "export function typeSectorTarget(n: SeaNode, ordinal: number, sectors: Sector[]) {" in lb
assert "return sectors" in lb
(D / "layout.ts").write_text(
    "/**\n"
    " * mind 视图 · 分区布局（扇区划分 / 圆盘半径 / 簇内目标点）。\n"
    " * 自 views/mind/renderer.ts 拆出（工单209 任务二）。\n"
    " *\n"
    " * **纯移动**：`nodes` 传参；`buildSectors` 原本重赋值闭包的 `sectors` → 改为返回新数组；\n"
    " * `typeSectorTarget` 需要的 `sectors` 由调用方传入（renderer 仍是状态所有者）。\n"
    " */\n"
    "import type { SeaNode } from './types'\n\n"
    + la.rstrip("\n") + "\n\n" + lb.rstrip("\n") + "\n", encoding="utf-8")
print("layout.ts 重新生成")

# ── quadtree.ts ──
i_qn = next(i for i, l in enumerate(p1) if l.startswith("  interface QuadNode {")) + 1
quad_iface = dedent2(seg(p1, i_qn, i_qn + 12)).replace("interface QuadNode {",
                                                       "export interface QuadNode {", 1)
assert "export interface QuadNode {" in quad_iface and "se: QuadNode | null" in quad_iface
raw_block = seg(p1, 235, 372)
raw_block = raw_block.replace(seg(p1, i_qn, i_qn + 12), "")   # 先去掉块内 QuadNode（原文缩进）
assert "interface QuadNode {" not in raw_block
inner = dedent2(raw_block)                                     # 再整体 dedent
(D / "quadtree.ts").write_text(
    "/**\n"
    " * mind 视图 · Barnes-Hut 四叉树（n>150 自动切换，O(n²) → O(n log n)）。\n"
    " * 自 views/mind/renderer.ts 拆出（工单209 任务二）。\n"
    " *\n"
    " * **纯移动**：7 个内部函数逐字节搬运、**零改动** —— 原本闭包在 createMindRenderer 内，\n"
    " * 这里改为闭包在 `createQuadTree(nodes, cfg)` 工厂内（同样的闭包语义与调用序）。\n"
    " */\n"
    "import type { SeaNode } from './types'\n\n"
    "export interface QuadtreeCfg {\n  /** 本模块只读取 cfg.spread */\n  spread: number\n}\n\n"
    + quad_iface.rstrip("\n") + "\n\n"
    "export interface QuadTreeApi {\n"
    "  build: () => QuadNode | null\n"
    "  repel: (root: QuadNode | null, i: number, alpha: number) => void\n"
    "}\n\n"
    "export function createQuadTree(nodes: SeaNode[], cfg: QuadtreeCfg): QuadTreeApi {\n"
    + inner.rstrip("\n") + "\n\n"
    "  return { build: quadBuild, repel: quadRepel }\n"
    "}\n", encoding="utf-8")
print("quadtree.ts 重新生成")
print("\n完成。下一步：npx vue-tsc -b（注意 tsconfig.json 是 solution 型，--noEmit 什么都不检查）")
