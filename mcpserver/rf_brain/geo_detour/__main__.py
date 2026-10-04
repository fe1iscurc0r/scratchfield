"""CLI 演示：python -m mcpserver.rf_brain.geo_detour --demo [--out x.svg]

输出绕障路径图。SVG 为**手写字符串生成（零依赖）**——任何环境可跑；
--png 时尝试 matplotlib（Agg），缺 matplotlib 则回退 SVG 并提示。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .detour import plan_detour
from .no_fly import Polygon, circle_to_polygon, path_length


def _demo_scenario():
    """演示空域：两个矩形禁飞区 + 一个圆形禁飞区，起终点直线穿越其中。"""
    start, end = (0.0, 0.0), (100.0, 40.0)
    zones = [
        Polygon(((20.0, -10.0), (45.0, -10.0), (45.0, 25.0), (20.0, 25.0))),
        Polygon(((60.0, 10.0), (85.0, 10.0), (85.0, 60.0), (60.0, 60.0))),
        circle_to_polygon((52.0, 5.0), radius_meters=800.0, segments=24),
    ]
    return start, end, zones


def _to_svg(start, end, zones, path, width=900, height=520, pad=40) -> str:
    xs = [start[0], end[0]] + [v[0] for z in zones for v in z.vertices]
    ys = [start[1], end[1]] + [v[1] for z in zones for v in z.vertices]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    def sx(x):
        return pad + (x - minx) / (maxx - minx or 1) * (width - 2 * pad)

    def sy(y):
        return height - pad - (y - miny) / (maxy - miny or 1) * (height - 2 * pad)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#fdfdfb"/>']
    for i, z in enumerate(zones):
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in z.vertices)
        out.append(f'<polygon points="{pts}" fill="#e8a2a2" fill-opacity="0.45" '
                   f'stroke="#b33" stroke-width="1.5"/>')
        cx, cy = z.center()
        out.append(f'<text x="{sx(cx):.1f}" y="{sy(cy):.1f}" font-size="12" fill="#833" '
                   f'text-anchor="middle">NFZ-{i + 1}</text>')
    d = " ".join(("M" if i == 0 else "L") + f"{sx(x):.1f},{sy(y):.1f}"
                 for i, (x, y) in enumerate(path))
    out.append(f'<path d="{d}" fill="none" stroke="#16847a" stroke-width="2.6"/>')
    for label, pt, color in (("START", start, "#1a7f37"), ("END", end, "#a15c00")):
        out.append(f'<circle cx="{sx(pt[0]):.1f}" cy="{sy(pt[1]):.1f}" r="5" fill="{color}"/>'
                   f'<text x="{sx(pt[0]) + 9:.1f}" y="{sy(pt[1]) - 8:.1f}" font-size="12" '
                   f'fill="{color}">{label}</text>')
    for x, y in path[1:-1]:
        out.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3" fill="#16847a"/>')
    out.append('</svg>')
    return "\n".join(out)


def _render_png(start, end, zones, path, out_path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for z in zones:
        xs = [v[0] for v in z.vertices] + [z.vertices[0][0]]
        ys = [v[1] for v in z.vertices] + [z.vertices[0][1]]
        ax.fill(xs, ys, color="#e8a2a2", alpha=0.45, edgecolor="#b33")
    px = [p[0] for p in path]
    py = [p[1] for p in path]
    ax.plot(px, py, "-o", color="#16847a", lw=2.2, ms=4)
    ax.plot(*start, "o", color="#1a7f37", ms=8)
    ax.plot(*end, "o", color="#a15c00", ms=8)
    ax.annotate("START", start, textcoords="offset points", xytext=(8, 6))
    ax.annotate("END", end, textcoords="offset points", xytext=(8, 6))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.25)
    ax.set_title("geo_detour demo — no-fly zones & detour path")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="geo_detour 绕障演示")
    ap.add_argument("--demo", action="store_true", help="运行内置演示场景")
    ap.add_argument("--out", default="", help="输出文件（.svg 或 .png）")
    ap.add_argument("--png", action="store_true", help="优先渲染 PNG（需 matplotlib）")
    args = ap.parse_args(argv)

    start, end, zones = _demo_scenario()
    result = plan_detour(start, end, zones)
    if not result.path:
        print("!! 演示场景不可达（不应发生）", file=sys.stderr)
        return 1

    print(f"[geo_detour] 直线距离 {result.direct_distance:.1f} | "
          f"绕行距离 {result.detoured_distance:.1f} | "
          f"代价比 {result.overhead_ratio:.2f} | 航点数 {len(result.path)}")
    for i in range(len(result.path) - 1):
        seg = (result.path[i], result.path[i + 1])
        assert path_length(seg) >= 0
    if not args.demo and not args.out:
        return 0

    out = Path(args.out) if args.out else Path("geo_detour_demo.svg")
    if args.png or out.suffix.lower() == ".png":
        png = out.with_suffix(".png")
        if _render_png(start, end, zones, result.path, png):
            print(f"[geo_detour] PNG 已输出 {png}")
            return 0
        print("[geo_detour] matplotlib 不可用 → 回退 SVG")
        out = out.with_suffix(".svg")
    out.write_text(_to_svg(start, end, zones, result.path), encoding="utf-8")
    print(f"[geo_detour] SVG 已输出 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
