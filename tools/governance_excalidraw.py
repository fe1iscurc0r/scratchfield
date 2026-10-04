"""治理快照 → Excalidraw 架构图生成器（W99-03 · excalidraw-architect-mcp 接入配套）。

把 `scripts/system_governance.py --model` 产出的模块/依赖快照 JSON 转成
Excalidraw 格式（矩形节点 = 模块，箭头 = 硬依赖边），产物可直接导入
excalidraw.com / Excalidraw 插件打开。

用法：
    python tools/governance_excalidraw.py [model.json] [out.excalidraw]
默认取 data/system_pulse 最新 model-*.json，输出 docs/governance-架构图.excalidraw。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _node_id(name: str) -> str:
    return f"mod-{name}"


def _edge_id(src: str, dst: str) -> str:
    return f"edge-{src}-{dst}"


def build(model: dict) -> dict:
    """模型快照 → Excalidraw 文档 dict。"""
    modules = model.get("modules", {})
    names = sorted(modules)
    cols = 4
    cell_w, cell_h = 260, 110
    margin = 60
    pos = {}
    elements = []

    for i, name in enumerate(names):
        col, row = i % cols, i // cols
        x = margin + col * (cell_w + margin)
        y = margin + row * (cell_h + margin)
        pos[name] = (x, y)
        info = modules[name]
        elements.append({
            "id": _node_id(name), "type": "rectangle", "x": x, "y": y,
            "width": cell_w, "height": cell_h, "angle": 0,
            "strokeColor": "#1e1e1e", "backgroundColor": "#d0e7ff",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100, "roundness": {"type": 3},
            "locked": False,
        })
        elements.append({
            "id": f"text-{name}", "type": "text", "x": x + 10, "y": y + 10,
            "width": cell_w - 20, "height": 40, "angle": 0,
            "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100,
            "text": name, "fontSize": 20, "fontFamily": 3, "textAlign": "left",
            "verticalAlign": "top", "containerId": _node_id(name),
        })
        elements.append({
            "id": f"stat-{name}", "type": "text", "x": x + 10, "y": y + 55,
            "width": cell_w - 20, "height": 40, "angle": 0,
            "strokeColor": "#555", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100,
            "text": f"py {info.get('py', 0)} · {info.get('lines', 0)} 行",
            "fontSize": 14, "fontFamily": 3, "textAlign": "left",
            "verticalAlign": "top", "containerId": _node_id(name),
        })

    # 硬依赖边：源节点右缘中点 → 目标节点左缘中点
    for name in names:
        info = modules.get(name, {})
        for dep in info.get("deps", []):
            if dep not in pos:
                continue
            x0, y0 = pos[name]
            x1, y1 = pos[dep]
            elements.append({
                "id": _edge_id(name, dep), "type": "arrow",
                "x": x0 + cell_w, "y": y0 + cell_h // 2,
                "width": max(abs(x1 - (x0 + cell_w)), 40),
                "height": max(abs(y1 + cell_h // 2 - (y0 + cell_h // 2)), 40),
                "angle": 0,
                "points": [
                    [0, 0],
                    [x1 - (x0 + cell_w), y1 + cell_h // 2 - (y0 + cell_h // 2)],
                ],
                "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
                "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
                "roughness": 1, "opacity": 100, "startBinding": None,
                "endBinding": None,
            })

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "scratchpad system_governance → excalidraw (tools/governance_excalidraw.py)",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def main() -> None:
    argv = sys.argv[1:]
    if argv:
        model_path = Path(argv[0])
    else:
        pulse = Path("data/system_pulse")
        model_path = sorted(pulse.glob("model-*.json"))[-1] if pulse.exists() else None
    if model_path is None or not model_path.exists():
        raise SystemExit("未找到模型快照：请先运行 scripts/system_governance.py --model")
    out = Path(argv[1]) if len(argv) > 1 else Path("docs/governance-架构图.excalidraw")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    doc = build(model)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {out}（{len(doc['elements'])} 元素，{len(model.get('modules', {}))} 模块）")


if __name__ == "__main__":
    main()
