#!/usr/bin/env python3
"""EasyEDA Pro 已装扩展静态审计：从 IndexedDB blob 提取扩展代码，扫外联/危险模式。"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BLOB_ROOT = Path.home() / "AppData/Local/LCEDA-Pro/cache.x64.3/IndexedDB/https_client_0.indexeddb.blob/1"

EXT_IDS = [
    "eext-balance-copper", "eext-update-components-attributes", "eext-timing-diagram-tool",
    "eext-qrcode-generator", "eext-pad-fanout", "eext-export-hyperlynx", "easyeda-agent-connector",
    "eext-knowledge-base", "eext-simulation-with-ngspice", "eext-mcad-integration-with-solidworks",
    "eext-mcad-integration-with-fusion360", "eext-mcad-integration-with-freecad",
    "eext-kipida-integration", "eext-gerber-viewer", "eext-ai-device-standardization",
    "eext-interactive-html-bom", "eext-schematic-pdf-interaction", "eext-kap1bala",
    "eext-filter-designer", "eext-datasheet-helper", "eext-export-pcb-to-svg",
    "eext-export-design-report", "eext-device-attribute-editor", "eext-simul", "eext-gerber-v",
]

URL_RE = re.compile(rb"https?://[A-Za-z0-9._\-]+|wss?://[A-Za-z0-9._\-]+")
DANGER = {
    "eval(": rb"eval\s*\(",
    "new Function": rb"new\s+Function\s*\(",
    "document.write": rb"document\.write\s*\(",
    "child_process": rb"child_process",
    "require('fs')": rb"require\s*\(\s*['\"]fs['\"]\s*\)",
    "localStorage": rb"localStorage",
    "WebSocket": rb"WebSocket",
    "XMLHttpRequest": rb"XMLHttpRequest",
    "fetch(": rb"fetch\s*\(",
    "postMessage": rb"postMessage\s*\(",
    "atob(": rb"atob\s*\(",
    "encodeURIComponent+eval": rb"eval\s*\(\s*(decodeURIComponent|atob|unescape)",
}
# 内部可信域（编辑器自身/API），不算外联
TRUSTED = {
    "127.0.0.1", "localhost", "pro.lceda.cn", "pro.lceda.com", "lceda.cn", "lceda.com",
    "jlc.com", "jlcpcb.com", "lcsc.com", "easyeda.com", "prodocs.lceda.cn", "jlc-ext.com",
    "client.lceda.cn", "pro.easyeda.com", "sz lcsc", "static.lceda.cn", "assets.lceda.cn",
}

def audit() -> dict:
    report: dict[str, dict] = defaultdict(lambda: {"blobs": 0, "bytes": 0, "urls": set(), "danger": defaultdict(list), "versions": set()})
    unmatched = 0
    for f in BLOB_ROOT.rglob("*"):
        if not f.is_file() or f.stat().st_size < 200:
            continue
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if b"function" not in data and b"=>" not in data and b"eda." not in data and b"extension" not in data.lower():
            continue
        owner = next((e for e in EXT_IDS if e.encode() in data), None)
        if not owner:
            unmatched += 1
            continue
        r = report[owner]
        r["blobs"] += 1
        r["bytes"] += len(data)
        for m in re.findall(rb'"version"\s*:\s*"([^"]{1,20})"', data)[:3] + re.findall(rb"'([^v][0-9]+\.[0-9]+\.[0-9]+[^']{0,10})'", data)[:2]:
            r["versions"].add(m[:20].decode("ascii", "replace"))
        for u in URL_RE.findall(data):
            host = re.sub(rb"^https?://|^wss?://", b"", u).decode("ascii", "replace").lower()
            if not any(host == t or host.endswith("." + t) for t in TRUSTED):
                r["urls"].add(host)
        for name, pat in DANGER.items():
            if re.search(pat, data):
                r["danger"][name].append(f.name)
    return {"report": report, "unmatched_js_blobs": unmatched}

def main() -> int:
    out = audit()
    print(json.dumps(
        {k: {"blobs": v["blobs"], "kb": v["bytes"] // 1024,
             "urls": sorted(v["urls"])[:12],
             "danger": {d: len(fs) for d, fs in v["danger"].items()}}
         for k, v in sorted(out["report"].items())},
        ensure_ascii=False, indent=1))
    print(f"\n[unmatched js blobs: {out['unmatched_js_blobs']}]")
    return 0

if __name__ == "__main__":
    sys.exit(main())
