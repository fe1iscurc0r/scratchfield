#!/usr/bin/env python3
"""HW-06 Phase0: JLC-EDA (EasyEDA) 原理图读取脚本。

两种模式：
  live   —— 经 easyeda-agent daemon (127.0.0.1:60832) 读当前打开的文档。
            前提: EasyEDA Pro 已打开 + easyeda-agent-connector 已装。
  file   —— 离线解析 .esch/.epro/导出 JSON，无需任何客户端。
            .epro 是 zip（内含 project.json + 各页 .esch）；.esch/.json
            是 EasyEDA 惯例的行式/数组式 JSON。

用法:
  python read_schematic.py live
  python read_schematic.py file <path.epro|.esch|.json> [-o out.json]

输出统一为 {"source": ..., "ok": ..., ...} 结构化 JSON。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

EASYEDA_EXE = Path(r"D:\tools\easyeda-agent\easyeda_windows_amd64.exe")
DESIGNATOR_RE = re.compile(r"^[A-Z]{1,4}[0-9]+$")


def read_live(window: str | None = None, project: str | None = None) -> dict:
    """daemon CLI → project info + doc context。NO_CONNECTOR/多窗口时优雅降级。"""
    target = []
    if project:
        target += ["--project", project]
    elif window:
        target += ["--window", window]

    def run(args: list[str]) -> dict | None:
        try:
            out = subprocess.run(
                [str(EASYEDA_EXE), *args, *target], capture_output=True, text=True,
                timeout=20, creationflags=0x08000000,
            )
            return json.loads(out.stdout) if out.stdout.strip().startswith("{") else {"raw": out.stdout[:2000]}
        except Exception as e:  # noqa: BLE001 — 诊断脚本，全部异常都要进报告
            return {"error": str(e)}

    info = run(["project", "info"])
    doc = run(["project", "doc"])
    ok = bool(doc and doc.get("ok"))
    return {
        "source": "easyeda-agent@60832",
        "ok": ok,
        "project": info,
        "document": doc,
        "note": (
            "官方 API 无 eda.editor.getDocument()；实际文档读取动作是 "
            "eda.dmt_SelectControl.getCurrentDocumentInfo()，由 `project doc` 封装。"
            if ok else "daemon 未连接 EasyEDA 窗口：装 EasyEDA Pro + easyeda-agent-connector.eext 后重试。",
        ),
    }


def _iter_shape_items(doc) -> list:
    """兼容三种顶层: dict{shape:[...]}, list[tuple...], 行式 JSON 文本。"""
    if isinstance(doc, dict) and isinstance(doc.get("shape"), list):
        return doc["shape"]
    if isinstance(doc, list):
        return doc
    return []


def _extract_from_items(items: list) -> dict:
    inv = {"wires": 0, "symbols": [], "nets": set(), "pins": 0, "other_tokens": {}}
    for it in items:
        if not isinstance(it, (list, tuple)) or not it:
            continue
        kind = str(it[0]).lower()
        if kind == "wire":
            inv["wires"] += 1
        elif kind in ("sym", "lib"):
            toks = [str(x) for x in it[1:] if isinstance(x, str)]
            desig = next((t for t in toks if DESIGNATOR_RE.match(t)), None)
            inv["symbols"].append({"raw_token_count": len(it), "designator": desig})
        elif kind == "pin":
            inv["pins"] += 1
        elif kind in ("netflag", "netport", "net"):
            # 惯例: [kind, name, x, y, id, ...] — 名字在第 2 位，id 形如 nf_g1 不入 nets
            name = str(it[1]) if len(it) > 1 and isinstance(it[1], str) else None
            if name and re.match(r"^[A-Za-z0-9_+\-]+$", name) and not re.match(r"^[a-z]+_", name):
                inv["nets"].add(name)
        inv["other_tokens"][kind] = inv["other_tokens"].get(kind, 0) + 1
    inv["nets"] = sorted(inv["nets"])
    return inv


def read_file(path: Path) -> dict:
    """解析 .epro(zip) / .esch / .json。对行式 JSON 逐行尝试解析。"""
    result: dict = {"source": str(path), "ok": False, "pages": []}
    docs: list[tuple[str, object]] = []
    if path.suffix.lower() == ".epro":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith((".esch", ".json")):
                    text = z.read(name).decode("utf-8", "replace")
                    docs.append((name, _loads_lenient(text)))
    else:
        docs.append((path.name, _loads_lenient(path.read_text("utf-8", "replace"))))
    for name, doc in docs:
        if doc is None:
            result["pages"].append({"page": name, "parse": "failed"})
            continue
        result["pages"].append({"page": name, "inventory": _extract_from_items(_iter_shape_items(doc))})
    result["ok"] = bool(result["pages"]) and any(p.get("inventory") for p in result["pages"])
    return result


def _loads_lenient(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        parsed = []
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in "[]{}":
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                # EasyEDA std 的 Lib 行是嵌套 JSON 字符串，剥掉首尾引号再试
                try:
                    parsed.append(json.loads(json.loads(f'"{line}"')))
                except Exception:  # noqa: BLE001
                    parsed.append(line[:120])
        return parsed or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["live", "file"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--window", help="多 EasyEDA 窗口时指定 windowId（live 模式）")
    ap.add_argument("--project", help="多工程时按工程名路由（live 模式，优先于 --window）")
    args = ap.parse_args()
    if args.mode == "file" and not args.path:
        ap.error("file 模式需要 <path>")
    result = read_live(window=args.window, project=args.project) if args.mode == "live" else read_file(Path(args.path))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, "utf-8")
        print(f"written: {args.out}")
    print(text)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
