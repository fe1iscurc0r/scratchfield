"""工单209 任务二 · 修复2：补跨模块依赖（proj / tc / Quintuple）+ 修 buildSectors 的 return 位置。

来源：`npx vue-tsc -b` 的真实报错（tsconfig 是 solution 型，必须用 -b）。
"""
from __future__ import annotations

from pathlib import Path

D = Path("src/views/mind/render")
R = Path("src/views/mind/renderer.ts")

# ── 1) types.ts 增补 ProjFn ──
t = D.joinpath("types.ts").read_text(encoding="utf-8")
if "ProjFn" not in t:
    t = t.rstrip("\n") + (
        "\n\n/** 投影函数（renderer 内的 proj，绘制类函数按需接收） */\n"
        "export interface ProjResult {\n"
        "  sx: number\n  sy: number\n  s: number\n  d: number\n"
        "}\n\n"
        "export type ProjFn = (x: number, y: number, z: number) => ProjResult\n"
    )
    D.joinpath("types.ts").write_text(t + "\n", encoding="utf-8")
    print("types.ts: +ProjFn/ProjResult")

# ── 2) effects.ts：4 个绘制函数追加 proj 参数 ──
e = D.joinpath("effects.ts").read_text(encoding="utf-8")
e = e.replace("import type { FlowDot, Particle, Plankton, Ray, SeaLink } from './types'",
              "import type { FlowDot, Particle, Plankton, ProjFn, Ray, SeaLink } from './types'", 1)
sig = [
    ("export function drawParticles(cx: CanvasRenderingContext2D | null, particles: Particle[]): void {",
     "export function drawParticles(\n"
     "  cx: CanvasRenderingContext2D | null, particles: Particle[], proj: ProjFn,\n"
     "): void {"),
    ("export function drawRays(cx: CanvasRenderingContext2D | null, rays: Ray[], cfg: EffectsCfg, t0: number): void {",
     "export function drawRays(\n"
     "  cx: CanvasRenderingContext2D | null, rays: Ray[], cfg: EffectsCfg, t0: number, proj: ProjFn,\n"
     "): void {"),
    ("export function drawFlow(cx: CanvasRenderingContext2D | null, flowParts: FlowDot[], t0: number): void {",
     "export function drawFlow(\n"
     "  cx: CanvasRenderingContext2D | null, flowParts: FlowDot[], t0: number, proj: ProjFn,\n"
     "): void {"),
    ("export function drawPlankton(cx: CanvasRenderingContext2D | null, plankton: Plankton[]): void {",
     "export function drawPlankton(\n"
     "  cx: CanvasRenderingContext2D | null, plankton: Plankton[], proj: ProjFn,\n"
     "): void {"),
]
for old, new in sig:
    assert old in e, f"effects 签名未命中: {old[:60]}"
    e = e.replace(old, new, 1)
D.joinpath("effects.ts").write_text(e, encoding="utf-8")
print("effects.ts: 4 个绘制函数 +proj")

# ── 3) layout.ts：buildSectors 加 tc 参数 + 修 return 位置 ──
la = D.joinpath("layout.ts").read_text(encoding="utf-8")
la = la.replace("export function buildSectors(nodes: SeaNode[]): Sector[] {",
                "export function buildSectors(nodes: SeaNode[], tc: (t: string) => string): Sector[] {", 1)
# 错的 return 位置（插到了 typeSectorTarget 末尾）
la = la.replace("  return sectors\n", "", 1) if la.count("  return sectors") == 1 else la
la_lines = la.splitlines(keepends=True)
sig_i = next(i for i, l in enumerate(la_lines) if l.startswith("export function buildSectors("))
end_i = next(i for i in range(sig_i + 1, len(la_lines)) if la_lines[i].rstrip("\n") == "}")
la_lines.insert(end_i, "  return sectors\n")
la = "".join(la_lines)
assert la.count("return sectors") == 1, "return sectors 数量异常"
D.joinpath("layout.ts").write_text(la, encoding="utf-8")
print("layout.ts: buildSectors +tc 且 return 归位")

# ── 4) renderer.ts：补 import Quintuple + 传参 ──
r = R.read_text(encoding="utf-8")
r = r.replace("import type { FlowDot, Particle, Plankton, Ray, SeaNode, SeaLink } from './render/types'",
              "import type { FlowDot, Particle, Plankton, Quintuple, Ray, SeaNode, SeaLink } from './render/types'", 1)
reps = [
    ("drawParticles(cx, particles)", "drawParticles(cx, particles, proj)"),
    ("drawRays(cx, rays, cfg, t0)", "drawRays(cx, rays, cfg, t0, proj)"),
    ("drawFlow(cx, flowParts, t0)", "drawFlow(cx, flowParts, t0, proj)"),
    ("drawPlankton(cx, plankton)", "drawPlankton(cx, plankton, proj)"),
    ("sectors = buildSectors(nodes)", "sectors = buildSectors(nodes, tc)"),
]
for old, new in reps:
    n = r.count(old)
    assert n >= 1, f"renderer 调用点未命中: {old!r}"
    r = r.replace(old, new)
    print(f"  renderer: {old} → {new}（{n} 处）")
R.write_bytes(r.replace("\r\n", "\n").encode("utf-8"))
print("\n完成 → 再跑 npx vue-tsc -b")
