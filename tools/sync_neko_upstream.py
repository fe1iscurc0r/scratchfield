"""sync_neko_upstream.py — 从上游 `Project-N-E-K-O/N.E.K.O` 增量同步到本仓 `NEKO/N.E.K.O/`。

背景（工单203 任务四）：
    `git fetch` 在本机被代理拦（`fetch-pack: invalid index-pack output`），
    故走 **REST Git Data API 逐 blob**（流程沿用 `docs/neko-上游同步-2026-09-30.md`
    已验证的方法：上次 295/300 文件一次通过）。

关键设计：
    - **逐提交累积 Δ**：`/compare` 的 `files` 有 300 条上限（本次已截断），
      但 `commits` 数组不受限 → 拿全部提交再逐提交取 `files`，合并为最终态；
    - **字节级同步**：blob 内容 base64 解码后**原样写盘**（不做行尾/编码转换）；
    - **本地无变化则跳过**：用 `git hash-object` 对比 blob sha，省 API 调用；
    - **删除**：上游 removed 的文件在本仓同步删除（保持与上游一致），
      但只在本地确实存在时删，并记入报告。

用法：
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base 8086151 --check
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base 8086151 --write
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base <sha> --tip <sha> --write
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "Project-N-E-K-O/N.E.K.O"
UP_API = f"https://api.github.com/repos/{UPSTREAM}"
#: 上游仓库根 → 本仓子树（上游路径直接挂在这一层下）
LOCAL_ROOT = ROOT / "NEKO" / "N.E.K.O"


def _token() -> str:
    tok = os.environ.get("GTOK") or os.environ.get("GITHUB_TOKEN") or ""
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["git", "credential-manager", "get"], capture_output=True, text=True,
            input="protocol=https\nhost=github.com\n\n")
        for line in out.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:  # noqa: BLE001
        pass
    return ""


TOKEN = _token()
HEADERS = {"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json"}


def api(path: str, *, retries: int = 3) -> dict:
    url = path if path.startswith("http") else UP_API + path
    last: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001 - 网络抖动人肉重试
            last = exc
    raise RuntimeError(f"API 失败 {path}: {last}")


def resolve(sha: str) -> str:
    return api(f"/commits/{sha}")["sha"]


def collect_changes(base: str, tip: str, *, verbose: bool = True) -> dict[str, dict]:
    """逐提交累积 → {path: {status, sha, previous_filename}}（后出现的覆盖先出现的）。"""
    cmp = api(f"/compare/{base}...{tip}")
    commits = cmp.get("commits") or []
    if verbose:
        print(f"提交数 {len(commits)} | compare.files 上限命中: {len(cmp.get('files') or []) >= 300}")
    changes: dict[str, dict] = {}
    for i, c in enumerate(commits, 1):
        info = api(f"/commits/{c['sha']}")
        for f in info.get("files") or []:
            changes[f["filename"]] = {
                "status": f["status"],
                "sha": f.get("sha"),
                "previous_filename": f.get("previous_filename"),
            }
        if verbose and i % 20 == 0:
            print(f"  已处理 {i}/{len(commits)} 提交，累计 {len(changes)} 文件")
    return changes


def local_blob_sha(path: Path) -> str | None:
    """本地文件的 git blob sha（不存在返回 None）。用 --path 让过滤器生效（与入库态一致）。"""
    if not path.exists():
        return None
    rel = path.relative_to(ROOT).as_posix()
    out = subprocess.run(["git", "-C", str(ROOT), "hash-object", "--path", rel, str(path)],
                         capture_output=True, text=True)
    return out.stdout.strip() or None


def blob_bytes(sha: str) -> bytes:
    d = api(f"/git/blobs/{sha}")
    return base64.b64decode(d["content"])


def sync(changes: dict[str, dict], *, write: bool) -> dict:
    stats = {"added": 0, "modified": 0, "removed": 0, "skipped": 0, "failed": 0}
    failures: list[str] = []
    for path, meta in sorted(changes.items()):
        target = LOCAL_ROOT / path
        if meta["status"] == "removed":
            if target.exists():
                if write:
                    target.unlink()
                stats["removed"] += 1
            continue
        cur = local_blob_sha(target)
        if cur == meta["sha"]:
            stats["skipped"] += 1
            continue
        if not write:
            stats["added" if cur is None else "modified"] += 1
            continue
        try:
            data = blob_bytes(meta["sha"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)                      # 字节级原样写盘
            got = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            if got != meta["sha"]:
                failures.append(f"{path}: sha 不符 {got[:10]} != {meta['sha'][:10]}")
                stats["failed"] += 1
                continue
            stats["added" if cur is None else "modified"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path}: {type(exc).__name__} {exc}")
            stats["failed"] += 1
    return {**stats, "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="本仓最后一次同步的上游提交（可短 sha）")
    ap.add_argument("--tip", default=None, help="上游目标提交（默认上游 main）")
    ap.add_argument("--write", action="store_true", help="实际写盘（默认只报告）")
    ap.add_argument("--check", action="store_true", help="只报告 Δ（默认行为）")
    args = ap.parse_args()

    base = resolve(args.base)
    tip = resolve(args.tip) if args.tip else api("/git/refs/heads/main")["object"]["sha"]
    print(f"上游 {UPSTREAM}\n  base={base[:12]}  tip={tip[:12]}\n  落盘根={LOCAL_ROOT.relative_to(ROOT)}")

    changes = collect_changes(base, tip)
    from collections import Counter
    cnt = Counter(m["status"] for m in changes.values())
    print(f"最终态 Δ: {len(changes)} 文件 | {dict(cnt)}")

    result = sync(changes, write=args.write)
    print(f"\n{'已写入' if args.write else '待写入'}: "
          f"新增 {result['added']} / 修改 {result['modified']} / 删除 {result['removed']} / "
          f"跳过(本地已一致) {result['skipped']} / 失败 {result['failed']}")
    if result["failures"]:
        print("失败清单（前 10）:")
        for f in result["failures"][:10]:
            print("  ", f)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
