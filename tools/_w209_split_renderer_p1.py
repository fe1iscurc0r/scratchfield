"""工单209 任务二 · renderer.ts 拆分 阶段一：types / constants / effects。

设计：**纯移动 + 显式参数**（不引入状态对象）——
  - 类型（Particle/Ray/FlowDot/Plankton/SeaNode/SeaLink/Quintuple）→ render/types.ts
  - 常量（FLOOR_Y/SURFACE_H）→ render/constants.ts
  - 12 个特效函数 → render/effects.ts；原闭包变量改为显式参数：
      · 读取型闭包变量 → 同名参数（函数体逐字节不变）
      · 初始化函数重新赋值数组（particles = [] 等）→ **改为返回新数组**，调用点接住赋值
        （若不这样，参数传引用会被重新赋值打断，状态与闭包脱钩）
  - 只在渲染器里改**调用点**（14 处），不改其余逻辑

用法：cd "D:/my git/scratchpad/frontend" && ../.venv/Scripts/python.exe ../tools/_w209_split_renderer_p1.py
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

SRC = Path("src/views/mind/renderer.ts")
BAK = Path("C:/Users/ASUS/AppData/Local/Temp/w222/renderer.ts.bak")
RENDER_DIR = Path("src/views/mind/render")

text = SRC.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
assert text.count("\r\n") == 0, "源文件应为 LF"


def seg(a: int, b: int) -> str:  # 1-based 闭区间
    return "".join(lines[a - 1:b])


def func_end(start_line: int) -> int:
    """从签名行往后找第一个「恰好 2 空格缩进的 }」= 该闭包内函数的结尾行号。"""
    for i in range(start_line, len(lines)):
        if lines[i] == "  }\n" or lines[i] == "  }":
            return i + 1
    raise AssertionError(f"未找到函数结尾: L{start_line}")


# ── 1) 抽出源码块 ──
types_block = seg(93, 141)          # Particle/Ray/FlowDot/Plankton
effects_block = seg(242, 565)       # 注释 + 12 个特效函数（到 drawPlankton 的 }）

assert "interface Particle {" in types_block and "interface Plankton {" in types_block
assert "function initParticles()" in effects_block and "function drawPlankton()" in effects_block
assert "function layoutRadius()" not in effects_block, "effects 块越界到 layout"

# 同时搬走 SeaNode/SeaLink/Quintuple（被 effects/layout/quadtree 依赖，避免循环 import）
head_types = seg(56, 92)            # Quintuple / SeaNode / SeaLink
assert "interface Quintuple {" in head_types and "interface SeaLink {" in head_types

RENDER_DIR.mkdir(parents=True, exist_ok=True)

# ── 2) 写 render/types.ts ──
types_out = (
    "/**\n"
    " * mind 渲染器 · 内部类型（自 views/mind/renderer.ts 拆出，工单209 任务二）。\n"
    " * **纯移动**：接口字段逐字节搬运，未改任何语义。\n"
    " */\n\n"
    + head_types.rstrip("\n") + "\n\n"
    + types_block.rstrip("\n") + "\n"
)
(RENDER_DIR / "types.ts").write_text(types_out, encoding="utf-8")

# ── 3) 写 render/constants.ts ──
(RENDER_DIR / "constants.ts").write_text(
    "/**\n"
    " * mind 渲染器 · 共享常量（自 views/mind/renderer.ts 拆出，工单209 任务二）。\n"
    " */\n\n"
    "export const FLOOR_Y = 0\n"
    "export const SURFACE_H = 200\n",
    encoding="utf-8",
)

# ── 4) 写 render/effects.ts（改签名 + 初始化函数返回数组）──
body = effects_block

sig_map = [
    ("  function initParticles() {",
     "export function initParticles(): Particle[] {"),
    ("  function simParticles() {",
     "export function simParticles(particles: Particle[], cfg: EffectsCfg): void {"),
    ("  function drawParticles() {",
     "export function drawParticles(cx: CanvasRenderingContext2D | null, particles: Particle[]): void {"),
    ("  function initRays() {",
     "export function initRays(): Ray[] {"),
    ("  function drawRays() {",
     "export function drawRays(cx: CanvasRenderingContext2D | null, rays: Ray[], cfg: EffectsCfg, t0: number): void {"),
    ("  function initFlow() {",
     "export function initFlow(links: SeaLink[]): FlowDot[] {"),
    ("  function simFlow() {",
     "export function simFlow(flowParts: FlowDot[]): void {"),
    ("  function drawFlow() {",
     "export function drawFlow(cx: CanvasRenderingContext2D | null, flowParts: FlowDot[], t0: number): void {"),
    ("  function spawnPlankton(): Plankton {",
     "export function spawnPlankton(): Plankton {"),
    ("  function initPlankton() {",
     "export function initPlankton(): Plankton[] {"),
    ("  function simPlankton() {",
     "export function simPlankton(plankton: Plankton[], cfg: EffectsCfg, t0: number): void {"),
    ("  function drawPlankton() {",
     "export function drawPlankton(cx: CanvasRenderingContext2D | null, plankton: Plankton[]): void {"),
]
for old, new in sig_map:
    assert old in body, f"签名锚点未命中: {old!r}"
    body = body.replace(old, new, 1)

# 初始化函数的「重新赋值」→ 局部声明 + return
init_ret = [
    ("initParticles", "particles", "Particle[]"),
    ("initRays", "rays", "Ray[]"),
    ("initFlow", "flowParts", "FlowDot[]"),
    ("initPlankton", "plankton", "Plankton[]"),
]
b_lines = body.splitlines(keepends=True)
for fname, var, typ in init_ret:
    # 找签名行 → 函数结尾 → 就地插入 return
    sig_i = next(i for i, l in enumerate(b_lines) if f"export function {fname}(" in l)
    end_i = next(i for i in range(sig_i, len(b_lines)) if b_lines[i].rstrip("\n") == "  }")
    b_lines.insert(end_i, f"    return {var}\n")
    # 重新赋值 → 局部声明
    for i in range(sig_i, end_i + 1):
        if b_lines[i].rstrip("\n") == f"    {var} = []":
            b_lines[i] = f"    const {var}: {typ} = []\n"
            break
    else:
        raise AssertionError(f"{fname}: 未找到 `{var} = []` 重赋值")
body = "".join(b_lines)

effects_out = (
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
    "/** 本模块只读取 cfg.hScale（其余字段不需要，故用窄结构类型） */\n"
    "export interface EffectsCfg {\n  hScale: number\n}\n\n"
    + body.rstrip("\n") + "\n"
)
(RENDER_DIR / "effects.ts").write_text(effects_out, encoding="utf-8")

# ── 5) 改 renderer.ts ──
new = text
# 5.1 删块（从后往前，避免行号漂移）
for a, b, label in ((242, 565, "effects"), (93, 141, "types"), (56, 92, "SeaNode/SeaLink/Quintuple")):
    seg_text = seg(a, b)
    assert seg_text in new, f"待删块未命中: {label}"
    new = new.replace(seg_text, "", 1)
    print(f"  删除 {label} L{a}-{b}（{b - a + 1} 行）")

# 5.2 删常量声明（改从 constants 导入）
for old, label in (("  const FLOOR_Y = 0\n  const SURFACE_H = 200\n", "FLOOR_Y/SURFACE_H 声明"),):
    assert old in new, f"常量锚点未命中: {label}"
    new = new.replace(old, "", 1)
    print(f"  删除 {label}")

# 5.3 加 import（放在最后一个 import 之后）
imports = (
    "import type { FlowDot, Particle, Plankton, Ray, SeaNode, SeaLink } from './render/types'\n"
    "import { FLOOR_Y, SURFACE_H } from './render/constants'\n"
    "import {\n"
    "  drawFlow,\n"
    "  drawParticles,\n"
    "  drawPlankton,\n"
    "  drawRays,\n"
    "  initFlow,\n"
    "  initParticles,\n"
    "  initPlankton,\n"
    "  initRays,\n"
    "  simFlow,\n"
    "  simParticles,\n"
    "  simPlankton,\n"
    "} from './render/effects'\n"
)
imp_lines = new.splitlines(keepends=True)
last_imp = max(i for i, l in enumerate(imp_lines) if l.startswith("import "))
imp_lines.insert(last_imp + 1, imports)
new = "".join(imp_lines)
print("  已插入 import")

# 5.4 改调用点
call_map = [
    ("    initParticles()", "    particles = initParticles()"),
    ("    initRays()", "    rays = initRays()"),
    ("    initFlow()", "    flowParts = initFlow(links)"),
    ("    initPlankton()", "    plankton = initPlankton()"),
    ("      simParticles()", "      simParticles(particles, cfg)"),
    ("      simFlow()", "      simFlow(flowParts)"),
    ("      simPlankton()", "      simPlankton(plankton, cfg, t0)"),
    ("      drawRays()", "      drawRays(cx, rays, cfg, t0)"),
    ("      drawParticles()", "      drawParticles(cx, particles)"),
    ("      drawPlankton()", "      drawPlankton(cx, plankton)"),
    ("      drawFlow()", "      drawFlow(cx, flowParts, t0)"),
]
for old, rep in call_map:
    n = new.count(old)
    assert n >= 1, f"调用点未命中: {old!r}"
    new = new.replace(old, rep)
    print(f"  调用点 {old.strip()} → {rep.strip()}（{n} 处）")

# 5.5 spawnPlankton 的调用点全在 simPlankton 体内（已随 effects.ts 搬走），
#     渲染器里本就不应再有引用 —— 反向校验：
assert "spawnPlankton" not in new, "渲染器仍引用 spawnPlankton（应随 effects.ts 搬走）"

# ── 6) 落盘（先备份）──
BAK.write_bytes(text.encode("utf-8"))
SRC.write_bytes(new.replace("\r\n", "\n").encode("utf-8"))
print(f"\nrenderer.ts: {len(lines)} → {new.count(chr(10)) + 1} 行（-{len(lines) - (new.count(chr(10)) + 1)}）")
print("备份:", BAK)
print("新增: render/types.ts / render/constants.ts / render/effects.ts")
