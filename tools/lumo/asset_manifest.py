"""资产 manifest 工具（handcrafted 蒸馏批 W100-03 轻落地 · 原创实现）。

设计参考：handcrafted-persona-engine 的 InstallManifest/AssetCatalog/双快照原子发布
（无 LICENSE，仅蒸馏不融合）——本实现按蒸馏文档 docs/handcrafted-system-skeleton-distill-2026-09-10.md
第 1 节的设计思想从零编写，只做「JSON manifest + sha256 校验 + 缺失检测」最小集，
不含断点下载（评估报告已注明）。

manifest 格式（JSON）：
{
  "assets": [
    {"id": "kokoro.onnx", "path": "models/kokoro.onnx", "sha256": "…",
     "size_bytes": 123, "tier": "tts", "url": "https://…（可选）"}
  ]
}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """文件 sha256（分块读，大文件安全）。"""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: str | Path) -> dict:
    """读取 manifest JSON（结构非法明确报错）。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"manifest 不存在: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
        raise ValueError(f"manifest 结构非法（缺 assets 列表）: {p}")
    return data


def check_manifest(manifest: dict, base_dir: str | Path) -> dict:
    """校验清单：缺失 / sha256 不匹配 / 大小不符，返回逐项报告。"""
    base = Path(base_dir)
    report: dict[str, Any] = {"ok": True, "items": []}
    for item in manifest.get("assets", []):
        entry = {"id": item.get("id", "?"), "status": "ok"}
        rel = item.get("path")
        if not rel:
            entry["status"] = "invalid"
            entry["reason"] = "缺 path 字段"
            report["ok"] = False
            report["items"].append(entry)
            continue
        fp = base / rel
        if not fp.is_file():
            entry["status"] = "missing"
            report["ok"] = False
        else:
            if "sha256" in item:
                actual = sha256_file(fp)
                if actual != item["sha256"]:
                    entry["status"] = "hash_mismatch"
                    entry["expected"] = item["sha256"][:12] + "…"
                    entry["actual"] = actual[:12] + "…"
                    report["ok"] = False
            if "size_bytes" in item and fp.stat().st_size != item["size_bytes"]:
                entry["status"] = "size_mismatch"
                entry["expected_size"] = item["size_bytes"]
                entry["actual_size"] = fp.stat().st_size
                report["ok"] = False
        report["items"].append(entry)
    return report


def missing_assets(manifest: dict, base_dir: str | Path) -> list[str]:
    """只返回缺失/损坏的资产 id 列表（供下载器用）。"""
    report = check_manifest(manifest, base_dir)
    return [i["id"] for i in report["items"] if i["status"] != "ok"]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="资产 manifest 校验")
    ap.add_argument("manifest")
    ap.add_argument("--base", default=".")
    args = ap.parse_args(argv)
    report = check_manifest(load_manifest(args.manifest), args.base)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
